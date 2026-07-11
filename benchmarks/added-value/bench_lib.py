"""Shared helpers for the added-value benchmark. Stdlib only.

Design notes:
- Never print or log secrets. The GLM key is read from ~/.hermes/.env at call
  time and lives only in memory / the request header.
- Every network helper returns (ok, payload_or_error) — callers decide retry.
- All state lives under runs/<run-id>/ so every stage is resumable/idempotent.
"""
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config.json").read_text())

ARMS = ("A", "B", "C")


# ── run layout ───────────────────────────────────────────────────────────

def run_dir(run_id: str) -> Path:
    d = HERE / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def briefs_path(run_id: str) -> Path:
    return run_dir(run_id) / "briefs.jsonl"


def load_briefs(run_id: str) -> list:
    p = briefs_path(run_id)
    if not p.exists():
        sys.exit(f"no briefs.jsonl in runs/{run_id} — run 01_collect.py first")
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def arm_dir(run_id: str, arm: str, case_id: str) -> Path:
    d = run_dir(run_id) / "arms" / arm / case_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def done_marker(run_id: str, arm: str, case_id: str) -> Path:
    return arm_dir(run_id, arm, case_id) / "meta.json"


def write_result(run_id: str, arm: str, case_id: str, deliverable: str | None,
                 meta: dict):
    d = arm_dir(run_id, arm, case_id)
    if deliverable is not None:
        (d / "deliverable.md").write_text(deliverable)
    meta.setdefault("arm", arm)
    meta.setdefault("case_id", case_id)
    meta.setdefault("finished_at", time.time())
    (d / "meta.json").write_text(json.dumps(meta, indent=2))


# ── corpus parsing (same frontmatter convention as app/evals.py) ─────────

def parse_case_md(text: str) -> tuple:
    fm, body = {}, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip("\"'")
            body = text[end + 4:].strip()
    return fm, body


# ── env / secrets ────────────────────────────────────────────────────────

def read_glm_key() -> str:
    """GLM key from ~/.hermes/.env (first configured name found). Never log it."""
    envf = Path(CFG["hermes_env_file"]).expanduser()
    if not envf.exists():
        sys.exit(f"missing {envf} — cannot call Z.AI for Arm C / GLM judge")
    names = set(CFG["glm_key_names"])
    for raw in envf.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip() in names and v.strip():
                return v.strip().strip("\"'")
    sys.exit(f"none of {sorted(names)} set in {envf}")


# cjudge's scrub list — the same vars, so bench Claude calls behave like the
# repo's own frontier calls (subscription auth, no ambient overrides).
_SCRUB = [
    "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_SUPPORTED_CAPABILITIES",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_SUPPORTED_CAPABILITIES",
    "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_SUBAGENT_MODEL",
    "CLAUDE_CODE_MAX_TOOL_USE_CONCURRENCY", "CLAUDE_CODE_EFFORT_LEVEL",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_CODE_WORKFLOWS",
    "CLAUDE_CODE_ALWAYS_ENABLE_EFFORT", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "API_TIMEOUT_MS", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
]


def scrubbed_env(extra: dict | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    if extra:
        env.update(extra)
    return env


# ── clean Claude home for Arm B ("normal user") ──────────────────────────

def ensure_clean_claude_home() -> Path:
    """A CLAUDE_CONFIG_DIR holding ONLY credentials + a model pin.
    No CLAUDE.md, no memory, no project state → 'normal user'."""
    home = HERE / "claude-home"
    home.mkdir(exist_ok=True)
    src = Path.home() / ".claude" / ".credentials.json"
    dst = home / ".credentials.json"
    if src.exists():
        shutil.copy2(src, dst)
        os.chmod(dst, 0o600)
    (home / "settings.json").write_text(json.dumps(
        {"model": CFG["arm_b_model"]}, indent=2))
    # onboarding/global state, minus this machine's project map
    legacy = Path.home() / ".claude.json"
    if legacy.exists():
        try:
            state = json.loads(legacy.read_text())
            state.pop("projects", None)
            (home / ".claude.json").write_text(json.dumps(state))
        except Exception:
            pass
    return home


def run_claude(prompt: str, cwd: Path, timeout_s: int, model: str = "",
               config_dir: Path | None = None) -> tuple:
    """claude -p with JSON envelope. Returns (ok, dict|err). dict has
    result/usage/total_cost_usd when the CLI provides them."""
    cmd = ["claude"]
    if model:
        cmd += ["--model", model]
    cmd += ["--output-format", "json", "-p", prompt]
    extra = {"CLAUDE_CONFIG_DIR": str(config_dir)} if config_dir else {}
    env = scrubbed_env(extra)
    cwd.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True,
                           text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return False, f"claude timed out after {timeout_s}s"
    except FileNotFoundError:
        return False, "claude CLI not found on PATH"
    out = (r.stdout or "").strip()
    if r.returncode != 0 and not out:
        return False, f"claude exit {r.returncode}: {(r.stderr or '')[-400:]}"
    try:
        env_json = json.loads(out)
    except Exception:
        # non-JSON fallback: treat raw stdout as the result text
        return True, {"result": out, "usage": {}, "total_cost_usd": None,
                      "_envelope": "raw"}
    if isinstance(env_json, dict) and "result" in env_json:
        return True, env_json
    return True, {"result": out, "usage": {}, "total_cost_usd": None}


# ── Z.AI (OpenAI-compatible) client for Arm C + GLM judge ────────────────

def zai_chat(messages: list, model: str, max_tokens: int, timeout_s: int,
             key: str) -> tuple:
    url = CFG["arm_c_base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages,
                       "max_tokens": max_tokens, "stream": False}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode()[:300]
        except Exception:
            pass
        return False, f"HTTP {e.code}: {detail}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return False, f"unexpected response shape: {str(data)[:300]}"
    return True, {"content": content, "usage": data.get("usage") or {}}


def is_quota_shed(err: str) -> bool:
    e = (err or "").lower()
    return "429" in e or "1305" in e or "overload" in e or "rate limit" in e


# ── Nexus API (same-machine trust, mirrors scripts/_gate_auth.py) ────────

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
_COOKIE_CACHE: dict = {}


def _owner_cookie() -> str:
    """'' while login is off; 'nexus_session=<tok>' when required. Minted via
    the app venv exactly like the verify gates do."""
    if "v" in _COOKIE_CACHE:
        return _COOKIE_CACHE["v"]
    app = Path(CFG["app_dir"])
    py = app / ".venv" / "bin" / "python"
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import auth\n"
        "print('' if not auth.auth_required() "
        "else auth.create_session('u_owner', 'bench'))"
    ) % str(app)
    try:
        r = subprocess.run([str(py), "-c", code], capture_output=True,
                           text=True, timeout=30)
        tok = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
        if r.returncode != 0:
            tok = ""
    except Exception:
        tok = ""
    _COOKIE_CACHE["v"] = f"nexus_session={tok}" if tok else ""
    return _COOKIE_CACHE["v"]


def nexus(method: str, path: str, body: dict | None = None,
          timeout_s: int = 60) -> tuple:
    url = CFG["nexus_base_url"].rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json"})
    ck = _owner_cookie()
    if ck:
        req.add_header("Cookie", ck)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s,
                                    context=_SSL_CTX) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode()[:400]
        except Exception:
            raw = ""
        return False, f"HTTP {e.code} {path}: {raw}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    try:
        return True, json.loads(raw)
    except Exception:
        return True, {"_raw": raw}


# ── judge JSON contract ──────────────────────────────────────────────────

SENT_BEGIN = "NEXUS_BENCH_JSON_BEGIN"
SENT_END = "NEXUS_BENCH_JSON_END"


def extract_sentinel_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(re.escape(SENT_BEGIN) + r"(.*?)" + re.escape(SENT_END),
                  text, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        # tolerate a bare trailing JSON object
        m2 = re.search(r"\{.*\}\s*$", text, re.S)
        blob = m2.group(0) if m2 else None
    if blob is None:
        return None
    try:
        return json.loads(blob.strip())
    except Exception:
        return None


def dims_mean(parsed: dict) -> float | None:
    dims = parsed.get("dims") or []
    scores = [d.get("score") for d in dims
              if isinstance(d.get("score"), (int, float))]
    return round(sum(scores) / len(scores), 3) if scores else None


# ── costing ──────────────────────────────────────────────────────────────

def list_price_usd(model: str, tok_in: int, tok_out: int,
                   tok_cache: int = 0) -> float | None:
    p = CFG["prices_per_mtok"].get(model)
    if not p:
        return None
    return round((tok_in * p.get("in", 0) + tok_out * p.get("out", 0)
                  + tok_cache * p.get("cache", 0)) / 1_000_000, 4)


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)
