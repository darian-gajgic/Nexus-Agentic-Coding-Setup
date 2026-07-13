"""NEXUS Agent OS — Tools Hub module.

Scanners for the v2 overview layer: tools registry, skills, projects, and usage/cost.
All pure-stdlib. Each scanner runs live (no cached state); the usage scanner caches
its expensive transcript parse for 60s.

Spec: SPEC-V2.md requirements 11-14.
"""
import os
import re
import json
import glob
import time
import socket
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional

HOME = Path.home()
HERMES_DIR = HOME / ".hermes"
NEXUS_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path, limit: int = 4000) -> str:
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def _probe_port(host: str, port: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _run(cmd, timeout=4):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or ""), (r.stderr or "")
    except Exception as e:
        return -1, "", str(e)


def _file_age_days(path: Path) -> Optional[float]:
    try:
        return (time.time() - path.stat().st_mtime) / 86400.0
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 11. TOOLS REGISTRY
# ---------------------------------------------------------------------------

def _tool_hermes():
    """The host agent itself."""
    status, detail = "offline", "not running"
    platforms, skills_count, model = [], 0, "unknown"
    # health via API port 8642
    if _probe_port("127.0.0.1", 8642):
        status = "online"
        detail = "API server responding on :8642"
    # model + platforms from config.yaml
    cfg = _read_text(HERMES_DIR / "config.yaml", 8000)
    m = re.search(r"^model:\s*(\S+)", cfg, re.M)
    if m:
        model = m.group(1)
    pm = re.findall(r"^\s*-\s*(platform:\s*\w+|name:\s*\w+)", cfg, re.M)
    platforms = [p.split(":", 1)[1].strip() for p in pm[:8]]
    # skills count
    try:
        skills_count = sum(1 for _ in (HERMES_DIR / "skills").glob("*/*.md"))
    except Exception:
        pass
    return {
        "id": "hermes", "name": "Hermes Agent", "category": "Agent",
        "status": status, "detail": detail, "model": model,
        "platforms": platforms, "skills_count": skills_count,
        "config_path": str(HERMES_DIR / "config.yaml"),
        "icon": "◈", "accent": "var(--accent)",
    }


def _tool_claude():
    """Claude Code (Anthropic) — secondary coding path."""
    claude_dir = HOME / ".claude"
    transcripts = len(glob.glob(str(claude_dir / "projects/*/*.jsonl")))
    status = "online" if (claude_dir / "settings.json").exists() else "offline"
    return {
        "id": "claude", "name": "Claude Code", "category": "Coding",
        "status": status, "detail": f"{transcripts} sessions logged (secondary)",
        "model": "claude (anthropic)", "transcripts": transcripts, "primary": False,
        "config_path": str(claude_dir / "settings.json"),
        "icon": "✦", "accent": "var(--yellow)",
    }


def _tool_ollama():
    """Local models on GPU."""
    models = []
    online = _probe_port("127.0.0.1", 11434)
    if online:
        rc, out, _ = _run(["curl", "-s", "http://127.0.0.1:11434/api/tags"])
        if rc == 0:
            try:
                tags = json.loads(out).get("models", [])
                models = [{"name": t["name"], "size_gb": round(t.get("size", 0) / 1e9, 1)}
                          for t in tags]
            except Exception:
                pass
    return {
        "id": "ollama", "name": "Ollama (local GPU)", "category": "LLM",
        "status": "online" if online else "offline",
        "detail": f"{len(models)} models loaded" if online else "not running on :11434",
        "models": models[:12],
        "config_path": str(HOME / ".ollama"),
        "icon": "◍", "accent": "var(--green)",
    }


def _tool_paperclip():
    """Agent control plane for AI-agent companies."""
    install = HOME / "agent-orchestration/paperclip"
    installed = (install / "package.json").exists() or (install / "server").exists()
    running = _probe_port("127.0.0.1", 3100) or _probe_port("127.0.0.1", 3101)
    status = "online" if running else ("configured" if installed else "offline")
    return {
        "id": "paperclip", "name": "Paperclip", "category": "Infra",
        "status": status,
        "detail": "control plane (not running)" if installed and not running else
                  (f"running on :{'3100' if _probe_port('127.0.0.1',3100) else '3101'}" if running else "not installed"),
        "install_path": str(install) if installed else None,
        "config_path": str(install / "doc/SPEC-implementation.md") if installed else None,
        "icon": "📎", "accent": "var(--blue)",
    }


def _tool_wav2lip():
    """Neural talking-head avatar for JARVIS."""
    install = HOME / "Wav2Lip"
    checkpoint = install / "checkpoints"
    has_ckpt = checkpoint.exists() and any(checkpoint.iterdir())
    face_src = HOME / "jarvis/face.mp4"
    has_face = face_src.exists()
    # CUDA check
    rc, out, _ = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    gpu = out.strip().splitlines()[0] if rc == 0 and out.strip() else None
    status = "online" if (has_ckpt and has_face and gpu) else "partial"
    return {
        "id": "wav2lip", "name": "Wav2Lip Avatar", "category": "Voice",
        "status": status,
        "detail": f"checkpoint={'✓' if has_ckpt else '✗'} face.mp4={'✓' if has_face else '✗'} gpu={gpu or '✗'}",
        "gpu": gpu, "config_path": str(install),
        "icon": "🗣", "accent": "var(--pink)",
    }


def _tool_piper():
    """Local TTS."""
    model = NEXUS_DIR / "models/piper_voice.onnx"
    status = "online" if model.exists() else "offline"
    return {
        "id": "piper", "name": "Piper TTS", "category": "Voice",
        "status": status, "detail": "GPU voice synthesis" if status == "online" else "model missing",
        "config_path": str(model), "icon": "🔊", "accent": "var(--green)",
    }


def get_tools() -> list:
    """Live health-check all integrated tools."""
    scanners = [_tool_hermes, _tool_claude, _tool_ollama,
                _tool_paperclip, _tool_wav2lip, _tool_piper]
    tools = []
    for s in scanners:
        try:
            tools.append(s())
        except Exception as e:
            tools.append({"id": getattr(s, "__name__", "?"), "name": "?",
                          "status": "offline", "detail": f"scanner error: {e}",
                          "category": "?"})
    return tools


# ---------------------------------------------------------------------------
# 12. SKILLS SCANNER
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> tuple:
    """Parse YAML-ish frontmatter (between --- fences). Returns (fm, body)."""
    fm = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    body = text[m.end():] if m else text
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"^(\w+):\s*(.*)$", line)
            if mm:
                fm[mm.group(1).strip()] = mm.group(2).strip().strip('"').strip("'")
    return fm, body


def get_skills() -> list:
    """Scan ~/.hermes/skills/ for SKILL.md files, grouped by category."""
    skills_root = HERMES_DIR / "skills"
    if not skills_root.is_dir():
        return []  # fresh machine before install.sh — empty hub, not a 500
    # load usage stats
    usage = {}
    upath = HERMES_DIR / "skills/.usage.json"
    if upath.exists():
        try:
            usage = json.loads(upath.read_text())
        except Exception:
            pass
    categories = []
    for cat_dir in sorted([d for d in skills_root.iterdir() if d.is_dir()]):
        cat_skills = []
        # skills can be top-level <name>/SKILL.md or nested <category>/<name>/SKILL.md
        for md in sorted(cat_dir.rglob("SKILL.md")):
            text = _read_text(md, 3000)
            fm, body = _parse_frontmatter(text)
            name = md.parent.name
            u = usage.get(name, {})
            cat_skills.append({
                "name": name,
                "description": fm.get("description", _first_sentence(body) or "(no description)"),
                "path": str(md),
                "use_count": u.get("use_count") or 0,
                "view_count": u.get("view_count") or 0,
                "state": u.get("state", "active"),
                "category": cat_dir.name,
            })
        if cat_skills:
            total_uses = sum(s["use_count"] for s in cat_skills)
            categories.append({
                "name": cat_dir.name,
                "count": len(cat_skills),
                "total_uses": total_uses,
                "skills": cat_skills,
            })
    return categories


def _first_sentence(text: str) -> str:
    text = text.strip()
    # strip markdown headers
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 20:
            return line[:160]
    return ""


# ---------------------------------------------------------------------------
# 13. PROJECTS SCANNER
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = {
    ".cache", "node_modules", ".venv", "venv", "snap", ".snap", "Desktop",
    "Downloads", "Public", "Templates", "Music", "Videos", "Pictures",
    "Documents", ".local", ".config", ".npm", ".nv", ".ollama", ".ollama-wf",
    "__pycache__", ".git", "backups", "models", ".worktrees", ".dotfiles",
    ".cua-driver", ".cua-driver-rs", ".var", ".vscode", ".vscode-shared",
}

LANG_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".rs": "Rust", ".go": "Go", ".md": "Markdown", ".sh": "Shell", ".bash": "Shell",
    ".html": "HTML", ".css": "CSS", ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".java": "Java", ".cpp": "C++", ".c": "C", ".rb": "Ruby", ".php": "PHP", ".sql": "SQL",
}


def _detect_languages(path: Path, sample_size: int = 400) -> dict:
    counts = {}
    for f in path.rglob("*"):
        if not f.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        ext = f.suffix.lower()
        lang = LANG_MAP.get(ext)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
        if sum(counts.values()) >= sample_size:
            break
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:5])


def _dir_size(path: Path, cap: int = 5000) -> int:
    total = 0
    n = 0
    for f in path.rglob("*"):
        if n > cap:
            break
        if any(part in EXCLUDE_DIRS for part in f.parts):
            continue
        try:
            if f.is_file():
                total += f.stat().st_size
                n += 1
        except Exception:
            continue
    return total


def _git_info(path: Path) -> dict:
    info = {"branch": None, "dirty": None, "remote": None, "ahead": 0}
    if not (path / ".git").exists():
        return info
    rc, out, _ = _run(["git", "-C", str(path), "branch", "--show-current"], 2)
    if rc == 0:
        info["branch"] = out.strip() or "(detached)"
    rc, out, _ = _run(["git", "-C", str(path), "status", "--porcelain"], 3)
    if rc == 0:
        info["dirty"] = bool(out.strip())
    rc, out, _ = _run(["git", "-C", str(path), "config", "--get", "remote.origin.url"], 2)
    if rc == 0:
        info["remote"] = out.strip()
    return info


def _is_project(path: Path) -> bool:
    markers = [".git", "package.json", "pyproject.toml", "setup.py", "requirements.txt",
               "Cargo.toml", "go.mod", "pom.xml", "CLAUDE.md", "AGENTS.md", "SPEC.md",
               "README.md", "Makefile"]
    if any((path / m).exists() for m in markers):
        return True
    # or has code files at top level
    for f in path.iterdir():
        if f.is_file() and f.suffix in LANG_MAP:
            return True
    return False


CLIENT_PROJECTS_ROOT = HOME / "Client-Projects"
PERSONAL_PROJECTS_ROOT = HOME / "Projects"


def _project_entry(d, client=None):
    try:
        st = d.stat()
    except Exception:
        return None
    gi = _git_info(d)
    return {
        "name": d.name,
        "path": str(d),
        "client": client,
        "size_bytes": _dir_size(d),
        "languages": _detect_languages(d),
        "git_branch": gi["branch"],
        "git_dirty": gi["dirty"],
        "git_remote": gi["remote"],
        "is_repo": gi["branch"] is not None,
        "has_venv": (d / ".venv").is_dir(),
        "last_modified": st.st_mtime,
        "description": _read_first_readme_line(d),
    }


def get_projects() -> list:
    """Scan /home/<user>/ for project directories.
    Client work lives one level deeper: ~/Client-Projects/<client>/<project> —
    those entries carry their client name (memory scope + galaxy color align)."""
    projects = []
    scan_root = HOME
    for d in sorted(scan_root.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name in EXCLUDE_DIRS:
            continue
        if d in (CLIENT_PROJECTS_ROOT, PERSONAL_PROJECTS_ROOT):
            continue  # handled below (nested / personal)
        if not _is_project(d):
            continue
        e = _project_entry(d)
        if e:
            projects.append(e)
    if PERSONAL_PROJECTS_ROOT.is_dir():
        for d in sorted(PERSONAL_PROJECTS_ROOT.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            e = _project_entry(d)
            if e:
                e["personal"] = True
                projects.append(e)
    if CLIENT_PROJECTS_ROOT.is_dir():
        for cdir in sorted(CLIENT_PROJECTS_ROOT.iterdir()):
            if not cdir.is_dir() or cdir.name.startswith("."):
                continue
            for d in sorted(cdir.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                e = _project_entry(d, client=cdir.name)
                if e:
                    projects.append(e)
    projects.sort(key=lambda p: p["last_modified"], reverse=True)
    return projects


def _read_first_readme_line(d: Path) -> str:
    for name in ("README.md", "readme.md", "README.txt", "README"):
        p = d / name
        if p.exists():
            txt = _read_text(p, 500)
            for line in txt.splitlines():
                line = line.strip().lstrip("#").strip()
                if len(line) > 5:
                    return line[:140]
    return ""


# ---------------------------------------------------------------------------
# 14. USAGE / COST AGGREGATOR
# ---------------------------------------------------------------------------

# Price table: USD per 1M tokens (in, out). Configurable via settings.
PRICE_TABLE = {
    "glm-5.2": {"in": 0.5, "out": 0.5},
    "glm-4.6": {"in": 0.5, "out": 0.5},
    "claude-sonnet": {"in": 3.0, "out": 15.0},
    "claude-opus": {"in": 15.0, "out": 75.0},
    "claude-haiku": {"in": 0.25, "out": 1.25},
    "qwen": {"in": 0.0, "out": 0.0},
    "ollama": {"in": 0.0, "out": 0.0},
    "default": {"in": 1.0, "out": 3.0},
}

_USAGE_CACHE = {"ts": 0, "data": None}
_USAGE_TTL = 60  # seconds


def _classify_model(model: str) -> str:
    m = (model or "").lower()
    if "glm" in m:
        return "glm-5.2"
    if "opus" in m:
        return "claude-opus"
    if "sonnet" in m:
        return "claude-sonnet"
    if "haiku" in m:
        return "claude-haiku"
    if "qwen" in m:
        return "qwen"
    if "ollama" in m or "gemma" in m or "llama" in m:
        return "ollama"
    return "default"


def _parse_transcripts(base_dir: Path) -> dict:
    """Parse claude-code transcript jsonl files. Returns aggregated stats.

    Claude Code snapshots usage on every assistant message in a turn, so we
    DEDUPLICATE usage records by (in, out, cache_read, cache_creation, model)
    per file to avoid 3-5x overcounts. cache_read tokens are billed at ~10%
    of the input rate (prompt-cache discount); cache_creation at ~1.25x.
    """
    agg = {
        "sessions": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_creation_tokens": 0,
        "per_model": {}, "per_day": {}, "per_project": {},
    }
    files = glob.glob(str(base_dir / "projects/*/*.jsonl"))
    agg["sessions"] = len(files)
    for path in files:
        proj = Path(path).parent.name
        proj = re.sub(r"^-home-[^-]+-?", "", proj).replace("-", "/") or "home"
        proj_tokens = 0
        seen = set()  # dedupe usage snapshots within a file
        last_ts = None
        for line in open(path, errors="replace"):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get("timestamp")
            if ts:
                last_ts = ts
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            usage = msg.get("usage")
            model = msg.get("model", "unknown")
            if not usage:
                continue
            in_tok = usage.get("input_tokens") or usage.get("input") or 0
            out_tok = usage.get("output_tokens") or usage.get("output") or 0
            cache_read = usage.get("cache_read_input_tokens") or 0
            cache_creation = usage.get("cache_creation_input_tokens") or 0
            # dedupe — same snapshot repeated across assistant messages in a turn
            key = (in_tok, out_tok, cache_read, cache_creation, model)
            if key in seen:
                continue
            seen.add(key)
            if not (in_tok or out_tok or cache_read or cache_creation):
                continue
            agg["input_tokens"] += in_tok
            agg["output_tokens"] += out_tok
            agg["cache_read_tokens"] += cache_read
            agg["cache_creation_tokens"] += cache_creation
            proj_tokens += in_tok + out_tok + cache_read + cache_creation
            cls = _classify_model(model)
            mm = agg["per_model"].setdefault(cls, {
                "in": 0, "out": 0, "model": model, "count": 0,
                "cache_read": 0, "cache_creation": 0})
            mm["in"] += in_tok
            mm["out"] += out_tok
            mm["cache_read"] += cache_read
            mm["cache_creation"] += cache_creation
            mm["count"] += 1
            day = None
            if last_ts:
                tval = last_ts / 1000 if isinstance(last_ts, (int, float)) and last_ts > 1e12 else last_ts
                try:
                    day = time.strftime("%Y-%m-%d", time.localtime(tval))
                except Exception:
                    day = str(last_ts)[:10]
            if day:
                dd = agg["per_day"].setdefault(day, {})
                dd[cls] = dd.get(cls, 0) + in_tok + out_tok + cache_read + cache_creation
        if proj_tokens:
            agg["per_project"][proj] = agg["per_project"].get(proj, 0) + proj_tokens
    return agg


def _parse_hermes_db() -> dict:
    """Parse ~/.hermes/state.db for token usage by model.

    Source of truth is the SESSIONS table's real billing counters
    (input_tokens/output_tokens/cache_read/cache_write/api_call_count) —
    the per-message token_count column is NULL in practice, and the old
    message-based sum with a fabricated 70/30 in/out split reported ~zero
    for the whole Hermes provider."""
    agg = {
        "sessions": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_creation_tokens": 0,
        "per_model": {}, "per_day": {}, "per_project": {},
    }
    db_path = HERMES_DIR / "state.db"
    if not db_path.exists():
        return agg
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        for row in c.execute(
                "SELECT model, started_at, api_call_count, "
                "COALESCE(input_tokens,0) i, COALESCE(output_tokens,0) o, "
                "COALESCE(cache_read_tokens,0) cr, COALESCE(cache_write_tokens,0) cw "
                "FROM sessions"):
            agg["sessions"] += 1
            model = row["model"] or "unknown"
            cls = _classify_model(model)
            agg["input_tokens"] += row["i"]
            agg["output_tokens"] += row["o"]
            agg["cache_read_tokens"] += row["cr"]
            agg["cache_creation_tokens"] += row["cw"]
            mm = agg["per_model"].setdefault(
                cls, {"in": 0, "out": 0, "model": model, "count": 0,
                      "cache_read": 0, "cache_creation": 0})
            mm["in"] += row["i"]
            mm["out"] += row["o"]
            mm["cache_read"] += row["cr"]
            mm["cache_creation"] += row["cw"]
            mm["count"] += int(row["api_call_count"] or 0)
            ts = row["started_at"]
            if ts:
                try:
                    day = time.strftime("%Y-%m-%d", time.localtime(ts))
                    dd = agg["per_day"].setdefault(day, {})
                    # trend counts in+out (cache reads would dwarf the chart);
                    # a long session books to its start day.
                    dd["hermes"] = dd.get("hermes", 0) + row["i"] + row["o"]
                except Exception:
                    pass
        c.close()
    except Exception as e:
        agg["error"] = str(e)
    return agg


def _cost(in_tok: int, out_tok: int, model_cls: str,
          cache_read: int = 0, cache_creation: int = 0) -> float:
    """USD cost. Anthropic prompt-cache pricing: cache_read ~10% input, cache_creation ~1.25x input."""
    p = PRICE_TABLE.get(model_cls, PRICE_TABLE["default"])
    base = (in_tok / 1_000_000) * p["in"] + (out_tok / 1_000_000) * p["out"]
    cache_cost = (cache_read / 1_000_000) * (p["in"] * 0.1) + \
                 (cache_creation / 1_000_000) * (p["in"] * 1.25)
    return base + cache_cost


def get_usage(force: bool = False) -> dict:
    """Aggregate usage across GLM + Claude + Hermes. Cached 60s."""
    now = time.time()
    if not force and _USAGE_CACHE["data"] and (now - _USAGE_CACHE["ts"]) < _USAGE_TTL:
        return _USAGE_CACHE["data"]

    glm = _parse_transcripts(HOME / ".claude-glm")
    claude = _parse_transcripts(HOME / ".claude")
    hermes = _parse_hermes_db()

    providers = []
    for pid, agg, label in (("glm", glm, "GLM-5.2 (Z.AI)"),
                            ("claude", claude, "Claude Code"),
                            ("hermes", hermes, "Hermes Agent")):
        cache_read = agg.get("cache_read_tokens", 0)
        cache_creation = agg.get("cache_creation_tokens", 0)
        cost = 0.0
        for cls, mm in agg["per_model"].items():
            cost += _cost(mm["in"], mm["out"], cls,
                          mm.get("cache_read", 0), mm.get("cache_creation", 0))
        providers.append({
            "id": pid, "name": label,
            "sessions": agg["sessions"],
            "input_tokens": agg["input_tokens"],
            "output_tokens": agg["output_tokens"],
            "cache_read_tokens": cache_read,
            "cache_creation_tokens": cache_creation,
            "total_tokens": agg["input_tokens"] + agg["output_tokens"] + cache_read + cache_creation,
            "est_cost_usd": round(cost, 4),
            "per_model": agg["per_model"],
        })

    # merge timeseries
    per_day = {}
    for agg in (glm, claude):
        for day, buckets in agg["per_day"].items():
            per_day.setdefault(day, {})
            for cls, tok in buckets.items():
                per_day[day][cls] = per_day[day].get(cls, 0) + tok
    for day, buckets in hermes["per_day"].items():
        per_day.setdefault(day, {})
        per_day[day]["hermes"] = per_day[day].get("hermes", 0) + buckets.get("hermes", 0)

    # last 14 days sorted
    days_sorted = sorted(per_day.keys())[-14:]
    timeseries = [{"day": d, "models": per_day.get(d, {})} for d in days_sorted]

    # merged per-model across all providers
    all_models = {}
    for agg in (glm, claude, hermes):
        for cls, mm in agg["per_model"].items():
            cur = all_models.setdefault(cls, {"in": 0, "out": 0, "count": 0})
            cur["in"] += mm["in"]
            cur["out"] += mm["out"]
            cur["count"] += mm["count"]

    # merged per-project (only glm+claude have project data)
    all_projects = {}
    for agg in (glm, claude):
        for proj, tok in agg["per_project"].items():
            all_projects[proj] = all_projects.get(proj, 0) + tok
    top_projects = sorted(all_projects.items(), key=lambda x: -x[1])[:8]

    total_cost = sum(p["est_cost_usd"] for p in providers)
    total_in = sum(p["input_tokens"] for p in providers)
    total_out = sum(p["output_tokens"] for p in providers)

    # Quality loop (2026-07-13): the frontier judge/critic/escalation spend
    # from the C3 ledger, as its own line — it bills the Claude subscription
    # invisibly (it hid inside the Claude-Code transcript aggregate), yet it
    # was 75%+ of frontier spend. Kinds: judge, judge_screen (GLM, $-cheap),
    # critic, escalation, judge_eval, premortem.
    quality_loop = {"kinds": {}, "total_usd": 0.0, "total_tokens": 0, "runs": 0,
                    "per_day": []}
    try:
        import database as db
        for r in db.query_all(
                "SELECT kind, COUNT(*) AS n, COALESCE(SUM(tokens),0) AS tok, "
                "COALESCE(SUM(cost_usd),0) AS usd FROM frontier_ledger GROUP BY kind"):
            quality_loop["kinds"][r["kind"]] = {
                "runs": int(r["n"]), "tokens": int(r["tok"]),
                "usd": round(float(r["usd"] or 0), 4)}
            quality_loop["total_usd"] += float(r["usd"] or 0)
            quality_loop["total_tokens"] += int(r["tok"])
            quality_loop["runs"] += int(r["n"])
        quality_loop["total_usd"] = round(quality_loop["total_usd"], 4)
        quality_loop["per_day"] = db.query_all(
            "SELECT date(created_at,'unixepoch','localtime') AS day, "
            "COALESCE(SUM(cost_usd),0) AS usd, COUNT(*) AS n "
            "FROM frontier_ledger GROUP BY day ORDER BY day DESC LIMIT 14")
    except Exception:
        pass

    result = {
        "providers": providers,
        "totals": {
            "sessions": sum(p["sessions"] for p in providers),
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "est_cost_usd": round(total_cost, 4),
        },
        "timeseries": timeseries,
        "per_model": {k: {**v, "cost": round(_cost(v["in"], v["out"], k), 4)}
                      for k, v in all_models.items()},
        "top_projects": [{"project": p, "tokens": t} for p, t in top_projects],
        "quality_loop": quality_loop,
        "price_table": PRICE_TABLE,
        "generated_at": now,
        "cache_ttl": _USAGE_TTL,
    }
    _USAGE_CACHE["ts"] = now
    _USAGE_CACHE["data"] = result
    return result
