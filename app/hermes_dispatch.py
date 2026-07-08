"""NEXUS Agent OS — Hermes dispatch client (the real-execution engine).

Executes a kanban task as a REAL Hermes Agent API session: one fresh session per
task, one streamed turn, deliverable files in the task workspace, real token
usage. Used by the /api/tasks/{id}/dispatch endpoint (S1) and by worker.py (S2).

Facts this module relies on (verified against hermes-agent source 2026-07-06,
anchors in SPEC-REAL-AGENTS.md §1):
- Base http://127.0.0.1:8642; auth "Authorization: Bearer $API_SERVER_KEY"
  (main.py loads ~/.hermes/.env — never print or log the key).
- POST /api/sessions -> {"session": {"id": "api_..."}}; persisted in
  ~/.hermes/state.db, survives gateway restarts, resumable by id.
- POST /api/sessions/{id}/chat/stream -> SSE "event:/data:" pairs; keepalive
  comment lines every ~30s; final events: assistant.completed {content},
  run.completed {usage:{input_tokens,output_tokens,total_tokens}}.
- "system_message" in the body = EPHEMERAL system prompt for that turn only.
- delegate_task is SYNCHRONOUS on this platform — a specialist's result comes
  back inside the same turn.
- A client disconnect does NOT kill the run: it finishes orphaned and flushes
  to state.db, recoverable via GET /api/sessions/{id}/messages (resume/harvest).
- Upstream Z.ai quota exhaustion may surface as a run FAILURE whose error text
  mentions the rate limit, not necessarily as HTTP 429 — detect both.
"""
import os
import re
import json
import time
import uuid
import datetime as dt
from pathlib import Path

import httpx

import database as db

BASE_DIR = Path(__file__).parent
WORKSPACES = BASE_DIR / "workspaces"

HERMES_API_BASE = os.environ.get("HERMES_API_BASE", "http://127.0.0.1:8642")

# SSE keepalives arrive every ~30s, so a 120s read timeout only trips when the
# stream is genuinely dead. No overall HTTP timeout — the turn cap below rules.
STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
DEFAULT_MAX_TURN_SECONDS = 2700  # 45 min hard cap per dispatched turn

QUOTA_SIGNATURES = ("429", "rate limit", "rate_limit", "too many concurrent", "quota")


class QuotaError(Exception):
    """Hermes/Z.ai rate-limit or quota-window exhaustion."""


class GatewayBusyError(Exception):
    """The Hermes gateway is up but saturated (heavy concurrent turns) —
    transient; callers should surface 'busy, try again shortly', not a 502."""


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    key = os.environ.get("API_SERVER_KEY", "")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def is_quota_error(text: str) -> bool:
    t = (text or "").lower()
    return any(sig in t for sig in QUOTA_SIGNATURES)


# ── Thin API wrappers ──

def api_health(timeout: float = 3.0) -> dict:
    """Probe the Hermes API server. Returns {connected, version}."""
    try:
        r = httpx.get(f"{HERMES_API_BASE}/health", headers=_headers(), timeout=timeout)
        return {"connected": r.status_code == 200,
                "version": (r.json() or {}).get("version") if r.status_code == 200 else None}
    except Exception as e:
        return {"connected": False, "error": str(e)[:200]}


def create_session(title: str, model: str | None = None,
                   system_prompt: str | None = None) -> str:
    """Create a fresh persistent Hermes session; returns its api_* id.
    model: per-task override (e.g. glm-5.1 for lighter work — Z.ai's concurrency
    limit is PER MODEL, so extra models are extra parallel capacity).
    system_prompt: PERSISTENT session-level system prompt (stronger than the
    per-turn ephemeral system_message — used to role-lock wizard sessions).
    Hermes enforces UNIQUE titles — on a collision (e.g. a retried task whose
    old session still exists) retry once with a short unique suffix."""
    payload = {"title": title}
    if model:
        payload["model"] = model
    if system_prompt:
        payload["system_prompt"] = system_prompt
    for attempt in (0, 1):
        try:
            # Generous timeout + one retry: when heavy tasks (vision, big
            # turns) saturate the gateway, session creation can take >15s —
            # failing hard here made the wizard 502 during normal load.
            r = httpx.post(f"{HERMES_API_BASE}/api/sessions", headers=_headers(),
                           json=payload, timeout=45)
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == 0:
                time.sleep(2)
                continue
            raise GatewayBusyError(f"Hermes gateway did not respond: {str(e)[:120]}")
        if r.status_code == 429:
            raise QuotaError(f"Hermes concurrency limit: {r.text[:200]}")
        if r.status_code == 400 and "invalid_title" in r.text and attempt == 0:
            payload["title"] = f"{title}~{uuid.uuid4().hex[:6]}"
            continue
        r.raise_for_status()
        data = r.json()
        return (data.get("session") or data)["id"]
    raise RuntimeError("session create failed after title retry")


def delete_session(session_id: str):
    """Best-effort session cleanup (used for throwaway wizard sessions)."""
    try:
        httpx.delete(f"{HERMES_API_BASE}/api/sessions/{session_id}",
                     headers=_headers(), timeout=10)
    except Exception:
        pass


def get_messages(session_id: str, limit: int = 100) -> list:
    """Session transcript from Hermes (state.db) — the REAL log."""
    r = httpx.get(f"{HERMES_API_BASE}/api/sessions/{session_id}/messages",
                  params={"limit": limit}, headers=_headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("data", data.get("messages", []))


def get_session(session_id: str) -> dict | None:
    """Session object incl. cumulative input_tokens/output_tokens; None if gone."""
    try:
        r = httpx.get(f"{HERMES_API_BASE}/api/sessions/{session_id}",
                      headers=_headers(), timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        return data.get("session") or data
    except Exception:
        return None


def stream_turn(session_id: str, input_text: str, system_message: str | None = None,
                on_event=None, max_seconds: int | None = None) -> dict:
    """Send one turn and consume its SSE stream to completion.

    on_event(name, data_dict) fires for every parsed event (heartbeats, live
    preview, activity). Returns {content, usage, error}. Raises QuotaError on
    rate-limit signatures so callers can back off instead of hammering.
    """
    url = f"{HERMES_API_BASE}/api/sessions/{session_id}/chat/stream"
    payload = {"input": input_text}
    if system_message:
        payload["system_message"] = system_message
    deadline = time.time() + (max_seconds or DEFAULT_MAX_TURN_SECONDS)
    content, usage, error, partial = "", {}, None, False

    with httpx.Client(timeout=STREAM_TIMEOUT) as client:
        with client.stream("POST", url, headers={**_headers(), "Accept": "text/event-stream"},
                           json=payload) as resp:
            if resp.status_code == 429:
                raise QuotaError(f"Hermes concurrency limit (HTTP 429)")
            if resp.status_code >= 400:
                body = b"".join(resp.iter_raw()).decode(errors="replace")[:300]
                if is_quota_error(body):
                    raise QuotaError(f"HTTP {resp.status_code}: {body}")
                return {"content": "", "usage": {}, "error": f"HTTP {resp.status_code}: {body}"}

            event_name = ""
            for line in resp.iter_lines():
                if on_event:
                    on_event("_line", None)  # every line (incl. keepalives) = liveness
                if time.time() > deadline:
                    error = "turn exceeded max_seconds cap; run may finish orphaned (recover via transcript)"
                    break
                if line.startswith("event: "):
                    event_name = line[7:].strip()
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:].strip())
                except Exception:
                    data = {}
                name, event_name = event_name, ""
                if on_event:
                    on_event(name, data)
                if name == "assistant.completed":
                    content = data.get("content") or content
                    partial = bool(data.get("partial") or data.get("interrupted"))
                elif name == "run.completed":
                    usage = data.get("usage") or {}
                    if not content:
                        content = data.get("content") or ""
                elif name == "error":
                    error = str(data.get("message") or data.get("error") or data)[:500]

    if error and is_quota_error(error):
        raise QuotaError(error)
    return {"content": content, "usage": usage, "error": error, "partial": partial}


# ── Per-model concurrency slots ──
# Z.ai allows ~10 concurrent requests PER MODEL and the Hermes API server caps
# 10 concurrent runs TOTAL. We stay under both (defaults 8/8, configurable) by
# COUNTING live dispatches before sending — a task without a free slot WAITS in
# the queue instead of hitting an upstream error.

DEFAULT_MODEL = "glm-5.2"
SLOT_HEARTBEAT_FRESH_S = 120  # a dispatch silent this long holds no upstream slot


def slots_in_use() -> dict:
    """Live in-flight dispatch counts per model (fresh executor heartbeats only)."""
    cutoff = time.time() - SLOT_HEARTBEAT_FRESH_S
    rows = db.query_all(
        "SELECT t.model AS model FROM dispatches d LEFT JOIN tasks t ON t.id = d.task_id "
        "WHERE d.state IN ('dispatching','streaming') "
        "AND COALESCE(d.heartbeat_at, d.started_at) > ?", (cutoff,))
    counts: dict = {}
    for r in rows:
        m = r.get("model") or DEFAULT_MODEL
        counts[m] = counts.get(m, 0) + 1
    return counts


def slot_available(model: str | None) -> bool:
    m = model or DEFAULT_MODEL
    # Per-model override (settings key dispatch.max_concurrent.<model>) beats
    # the global per-model cap — Z.AI's concurrency limit is per model (~10).
    # Only a positive integer counts as an override: absent/empty/"0" all fall
    # through to the global cap (the string "0" is truthy — a plain `or` chain
    # here once produced cap=0 and deadlocked every lane).
    raw = (db.get_setting(f"dispatch.max_concurrent.{m}", "") or "").strip()
    if raw.isdigit() and int(raw) > 0:
        per_model_cap = int(raw)
    else:
        per_model_cap = int(db.get_setting("dispatch.max_concurrent_per_model", "8"))
    total_cap = int(db.get_setting("dispatch.max_concurrent_total", "8"))
    counts = slots_in_use()
    if sum(counts.values()) >= total_cap:
        return False
    return counts.get(m, 0) < per_model_cap


# ── Budgets & quota backoff (SPEC R7) ──

def check_budgets(task: dict) -> str | None:
    """Return a blocked-state name if this task must NOT be dispatched now.
    Task-specific budget is checked BEFORE the global quota backoff so a budget
    verdict stays deterministic even in the middle of a 429 storm."""
    budget = task.get("budget_tokens") or int(db.get_setting("dispatch.default_task_budget", "1000000"))
    if (task.get("tokens_used") or 0) >= budget:
        return "blocked_budget"
    backoff_until = float(db.get_setting("dispatch.quota_backoff_until", "0") or 0)
    if backoff_until > time.time():
        return "blocked_quota"
    midnight = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    row = db.query_one(
        "SELECT COALESCE(SUM(tokens_in + tokens_out), 0) AS total FROM dispatches WHERE started_at >= ?",
        (midnight,))
    if row and row["total"] >= int(db.get_setting("dispatch.daily_cap", "10000000")):
        return "blocked_quota"
    return None


def note_quota_hit():
    """Exponential global backoff: 60s doubling per consecutive STORM, cap 30 min.
    Escalate at most once per backoff window — N lanes hitting the same 429
    burst must count as ONE hit, not N (2^N would jump straight to the cap)."""
    now = time.time()
    until = float(db.get_setting("dispatch.quota_backoff_until", "0") or 0)
    if until > now:
        return int(until - now)  # storm already acknowledged by another lane
    n = int(db.get_setting("dispatch.quota_consecutive", "0") or 0) + 1
    backoff = min(60 * (2 ** (n - 1)), 1800)
    db.set_setting("dispatch.quota_consecutive", n)
    db.set_setting("dispatch.quota_backoff_until", now + backoff)
    db.log_activity("warn", "dispatch", f"Quota/429 hit #{n} — backing off {backoff}s (all lanes)")
    return backoff


def note_quota_ok():
    """A success resets the ESCALATION counter only. An active backoff window is
    left to expire on its own (max 30 min): one lucky task finishing mid-storm
    must not un-pause every lane straight back into the 429s."""
    db.set_setting("dispatch.quota_consecutive", "0")


# ── Workflow dependencies (v2.1 — projects/campaigns as task DAGs) ──

def task_dependencies(task: dict) -> list[dict]:
    """Resolve a task's depends_on JSON into the actual predecessor rows."""
    try:
        dep_ids = json.loads(task.get("depends_on") or "[]")
    except Exception:
        dep_ids = []
    out = []
    for did in dep_ids:
        d = db.query_one("SELECT * FROM tasks WHERE id=?", (did,))
        if d:
            out.append(d)
    return out


def deps_satisfied(task: dict) -> bool:
    """A task may only run when every dependency has shipped (status done).
    FAIL-CLOSED: a dependency id with no row counts as NOT done — silently
    dropping unknown ids made such tasks vacuously claimable, and workers
    picked up gate probes mid-test (zombie dispatches crashed once the gate's
    cleanup removed the rows). A dangling dep now parks the task instead."""
    try:
        dep_ids = json.loads(task.get("depends_on") or "[]")
    except Exception:
        dep_ids = []
    if not dep_ids:
        return True
    rows = {d["id"]: d for d in task_dependencies(task)}
    return all(did in rows and rows[did].get("status") == "done"
               for did in dep_ids)


# ── Dispatch prompt contract (SPEC §2) ──

# This install's own venv python — carries the document stack (docx/xlsx/pptx/
# pdf/pillow) agents use for binary deliverables. Derived, not hardcoded, so
# the package installs under any user/target dir.
DOC_TOOLS_PY = str(Path(__file__).resolve().parent / ".venv" / "bin" / "python")

import worktree as wt


_CLIENT_SCOPES_FILE = os.path.expanduser("~/.hermes/client-scopes.json")


def publish_session_scope(session_id: str, client: str | None = None,
                          user: str | None = None):
    """Session→scope maps for the mem0-client provider.

    Two scopes, same bridge-file mechanism (M3 generalized one level up):
      "sessions" {sid: client} — client isolation (M3, unchanged name for
                                 backward compatibility)
      "users"    {sid: user}   — Block-1 per-user isolation: memories
                                 extracted from this session are stamped
                                 metadata.user and invisible to other users'
                                 sessions.
    Same bridge-file pattern as model-efforts.json; pruned at 800 entries."""
    if not client and not user:
        return
    try:
        data = {}
        if os.path.isfile(_CLIENT_SCOPES_FILE):
            with open(_CLIENT_SCOPES_FILE) as f:
                data = json.load(f)
        sessions = data.get("sessions") or {}
        users = data.get("users") or {}
        updated = data.get("updated") or {}
        if (client and sessions.get(session_id) == client and not user) or \
           (user and users.get(session_id) == user and not client) or \
           (client and user and sessions.get(session_id) == client
                and users.get(session_id) == user):
            return  # idempotent: nothing to write (hot path on session reuse)
        if client:
            sessions[session_id] = client
        if user:
            users[session_id] = user
        updated[session_id] = time.time()
        if len(updated) > 800:
            for sid in sorted(updated, key=updated.get)[:len(updated) - 800]:
                sessions.pop(sid, None)
                users.pop(sid, None)
                updated.pop(sid, None)
        # rewrite the three maps but PRESERVE any other top-level keys the
        # file carries (e.g. "default_user", the unmapped-session fallback
        # written by the mem0 user backfill migration)
        data.update({"sessions": sessions, "users": users, "updated": updated})
        with open(_CLIENT_SCOPES_FILE, "w") as f:
            json.dump(data, f, indent=1)
    except Exception as e:
        db.log_activity("warn", "system", f"session-scope publish failed: {str(e)[:80]}")


def _task_user(task_id: str) -> str | None:
    row = db.query_one("SELECT user_id FROM tasks WHERE id=?", (task_id,))
    return (row or {}).get("user_id")


def _repo_is_code(path: str) -> bool:
    """Code project vs content/campaign/thesis project — decides which
    repo-mode contract the agent gets."""
    markers = ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
               "go.mod", "src", "app", "lib")
    try:
        names = set(os.listdir(path))
    except Exception:
        return True
    if any(m in names for m in markers):
        return True
    code_exts = (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".sh")
    return any(n.endswith(code_exts) for n in names)


def _repo_slug(task: dict) -> str:
    """Pipeline tasks share one branch (stages build on each other); loose
    tasks get their own."""
    return (task.get("workflow_id") or task.get("id") or "task").replace("wf-", "").replace("task-", "")


def _code_map(worktree: str, max_chars: int = 4000) -> str:
    """Compact repository layout from `git ls-files` (SPEC-BLOCK2 R3.5):
    per-directory file counts + the files of the top two levels + a language
    histogram — so the agent stops re-discovering the tree with shell calls
    every round. Deterministic, no LLM, capped."""
    import subprocess
    try:
        r = subprocess.run(["git", "ls-files"], cwd=worktree, capture_output=True,
                           text=True, timeout=20)
        if r.returncode != 0:
            return ""
        paths = [p for p in r.stdout.splitlines() if p.strip()]
    except Exception:
        return ""
    if not paths:
        return ""
    by_dir: dict[str, int] = {}
    langs: dict[str, int] = {}
    shallow: list[str] = []
    for p in paths:
        parts = p.split("/")
        top = parts[0] if len(parts) > 1 else "."
        by_dir[top] = by_dir.get(top, 0) + 1
        ext = os.path.splitext(p)[1].lower()
        if ext:
            langs[ext] = langs.get(ext, 0) + 1
        if len(parts) <= 2:
            shallow.append(p)
    lines = [f"{len(paths)} tracked files. Layout (top-level → file count):"]
    for d, n in sorted(by_dir.items(), key=lambda kv: -kv[1])[:20]:
        lines.append(f"  {d}/  {n}" if d != "." else f"  (root)  {n}")
    top_langs = ", ".join(f"{e} ×{n}" for e, n in
                          sorted(langs.items(), key=lambda kv: -kv[1])[:8])
    if top_langs:
        lines.append(f"Languages: {top_langs}")
    lines.append("Files (top two levels):")
    for p in sorted(shallow)[:150]:
        lines.append(f"  {p}")
    if len(shallow) > 150:
        lines.append(f"  … {len(shallow) - 150} more at this depth")
    out = "\n".join(lines)
    return out[:max_chars]


def _repo_context(task: dict) -> dict | None:
    """Resolve the task's isolated worktree (idempotent) + repo conventions
    file + code map. Returns {worktree, branch, base, conventions, code_map}
    or None."""
    repo = (task.get("repo_path") or "").strip()
    if not repo:
        return None
    info = wt.ensure_task_worktree(repo, _repo_slug(task))
    if not info:
        return None
    conventions = ""
    for name in ("AGENTS.md", "CLAUDE.md", ".hermes.md"):
        p = Path(info["worktree_path"]) / name
        if p.is_file():
            try:
                conventions = f"[{name}]\n" + p.read_text()[:6000]
            except Exception:
                pass
            break
    return {"worktree": info["worktree_path"], "branch": info["worktree_branch"],
            "base": info.get("base_branch") or "main", "conventions": conventions,
            "code_map": _code_map(info["worktree_path"])}


def _knowledge_paths(task: dict) -> dict:
    """SPEC-ONBOARDING R2.3: the Business-Brain context/voice paths for THIS
    task's owner — a non-owner user with a completed personal onboarding gets
    their overlay; everyone else (and every legacy task) gets the canonical
    files. PLAYBOOK/RUBRIC stay shared (craft, not identity)."""
    root = Path(db.get_setting("onboarding.root", "") or os.path.expanduser("~/knowledge"))
    uid = (task.get("user_id") or "").strip()
    if uid and uid != "u_owner":
        d = root / "users" / uid
        if (d / "BUSINESS-CONTEXT.md").is_file() and (d / "STYLE-VOICE.md").is_file():
            return {"context": str(d / "BUSINESS-CONTEXT.md"),
                    "style": str(d / "STYLE-VOICE.md")}
    return {"context": str(root / "BUSINESS-CONTEXT.md"),
            "style": str(root / "STYLE-VOICE.md")}


def _attachment_lines(task: dict, workspace: Path) -> list[str]:
    """Operator-attached input files: the task's own + its project's."""
    dirs = [workspace / "attachments"]
    if task.get("workflow_id"):
        dirs.append(WORKSPACES / f"workflow-{task['workflow_id']}" / "attachments")
    out = []
    for d in dirs:
        try:
            if d.is_dir():
                out.extend(str(f) for f in sorted(d.iterdir()) if f.is_file())
        except Exception:
            pass
    return out


def build_framing(task: dict, workspace: Path, repo_ctx: dict | None = None) -> str:
    parts = [
        f"You are executing Nexus kanban task {task['id']} (\"{task['title']}\") autonomously "
        "for the Nexus Agent OS control plane. Work the task to completion in this turn.",
    ]
    if repo_ctx:
        is_code = _repo_is_code(repo_ctx["worktree"])
        common_head = (
            f"PROJECT-NATIVE TASK: you operate on the EXISTING project checked out at "
            f"{repo_ctx['worktree']} — an isolated git worktree on branch "
            f"{repo_ctx['branch']} (baseline: {repo_ctx['base']}; the operator's main "
            "checkout is untouched). Rules:\n"
            f"- Work INSIDE {repo_ctx['worktree']} — build on what exists there, do NOT "
            "start fresh in the task workspace.\n")
        if is_code:
            body = (
                "- Follow the repository's own conventions and commands (see the conventions "
                "file below if present). Its test/build/lint gates are YOUR gates — run them "
                "and paste real output.\n"
                "- Navigate by symbol (mcp-serena) and check every touched symbol's other "
                "usages before calling the work done.\n")
        else:
            body = (
                "- This is a CONTENT project (campaign/document/thesis materials). READ the "
                "existing materials first — new work must be consistent with them (voice, "
                "branding, decisions already made). Place deliverable files in sensible "
                "folders inside the project.\n"
                "- Do not modify previously delivered material unless the goal says so — "
                "add new versions alongside.\n")
        common_tail = (
            "- COMMIT your work on the branch in clear, scoped commits (git add/commit in "
            "the worktree). Never push, never merge, never switch branches.\n"
            f"- Write {workspace}/deliverable.md as a CHANGE REPORT: what you added/changed "
            "and why, files touched, and follow-ups. The DIFF on the branch is the real "
            "deliverable — the operator reviews and merges it manually."
            + (f"\n\nPROJECT CONVENTIONS {repo_ctx['conventions'][:6200]}"
               if repo_ctx.get("conventions") else "")
            + (f"\n\nCODE MAP (repository layout):\n{repo_ctx['code_map']}"
               if repo_ctx.get("code_map") else ""))
        parts.append(common_head + body + common_tail)
    else:
        parts.append(
            f"Write your final deliverable to the file {workspace}/deliverable.md using your file "
            "tools (the directory exists). You may create additional supporting files next to it. "
            "If the task calls for binary output formats (pdf, docx, xlsx, pptx, png), produce "
            f"them as files next to deliverable.md using {DOC_TOOLS_PY} — python-docx, openpyxl, "
            "python-pptx, reportlab, pypdf, pillow and markdown are preinstalled there — and have "
            "deliverable.md reference them. For browser-based checks use your browser tools or "
            f"Python playwright from that same interpreter; the npm 'playwright' package is NOT "
            "installed globally.")
    parts.append(
        "When the task needs a STRUCTURED FACT — exchange rates, weather, country/market "
        "data, public holidays, economic indicators, paper/package/repo metadata, "
        "naming/word ideas, product barcodes, webshop seed data, music metadata/BPM — "
        "read ~/.hermes/skills/fetching-structured-facts/SKILL.md first: curated keyless "
        "APIs with exact commands (verified working). More precise than web search for "
        "these; for everything else use web search as usual."
    )
    atts = _attachment_lines(task, workspace)
    if atts:
        parts.append(
            "The operator ATTACHED input files for this work — read them FIRST, they are "
            "part of the brief:\n" + "\n".join(f"- {a}" for a in atts)
            + f"\nExtract pdf/docx/xlsx/pptx content with {DOC_TOOLS_PY} "
              "(pypdf, python-docx, openpyxl, python-pptx).")
    domain = (task.get("domain") or "").strip()
    if domain and domain != "general":
        kp = _knowledge_paths(task)
        parts.append(
            f"This is a business deliverable in the '{domain}' domain. Follow the Business Brain "
            f"knowledge protocol: read {kp['context']}, {kp['style']} "
            f"and ~/knowledge/domains/{domain}/PLAYBOOK.md before working (those first two files "
            "are THIS task owner's business context and voice — use exactly these paths even if "
            "a specialist definition names other defaults); self-score the result "
            f"against ~/knowledge/domains/{domain}/RUBRIC.md and state the score in one line; end "
            "with a '**Learn:**' section of up to 3 bullets."
        )
    specialist = (task.get("specialist") or "").strip()
    if specialist:
        parts.append(
            f"Delegate the whole task to the specialist '{specialist}' using your delegate_task "
            "tool (it runs synchronously here) and incorporate its full result into the deliverable."
        )
    deps = [d for d in task_dependencies(task) if d.get("status") == "done"]
    if deps:
        lines = "\n".join(
            f"- {d['workspace_path'] or 'workspaces/' + d['id']}/deliverable.md "
            f"(output of '{d['title']}')" for d in deps)
        parts.append(
            "This task builds on completed predecessor tasks in the same workflow. "
            "FIRST read their deliverables with your file tools — they are your input:\n" + lines)
    if task.get("retry_feedback"):
        parts.append(
            "This is a RETRY: a previous attempt was rejected. Address every point of this "
            f"feedback before delivering:\n{task['retry_feedback']}"
        )
    parts.append("Finally, reply in chat with the complete final deliverable text — the reply is "
                 "stored as the task result.")
    return "\n\n".join(parts)


def parse_deliverable_meta(text: str) -> tuple[str | None, str | None]:
    """Best-effort extraction of the rubric self-score line and the Learn: section."""
    rubric = None
    m = re.search(r"^(?=.*(?:rubric|self[- ]?score|score))(?=.*\d).*$",
                  text or "", re.I | re.M)
    if m:
        rubric = m.group(0).strip()[:300]
    learn = None
    m2 = re.search(r"\*\*\s*Learn:?\s*\*\*:?(.*)$", text or "", re.S | re.I)
    if m2:
        learn = m2.group(1).strip()[:2000]
    return rubric, learn


# ── The executor: one task, end to end ──

def notify_desktop(title: str, body: str):
    """X3: best-effort desktop notification (notify-send). Silent no-op when
    there is no display/session — never breaks a dispatch."""
    try:
        import subprocess
        subprocess.run(["notify-send", "-a", "Nexus", "-i", "dialog-information",
                        title, body], timeout=5, capture_output=True)
    except Exception:
        pass


def _set_task(task_id: str, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE tasks SET {sets}, updated_at=? WHERE id=?",
               (*fields.values(), time.time(), task_id))


def _set_dispatch(dispatch_id: str, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE dispatches SET {sets} WHERE id=?", (*fields.values(), dispatch_id))


def _make_on_event(dispatch_id: str, task_id: str, agent_id: str):
    """Live-telemetry callback (R2): heartbeat agent + dispatch row on every SSE
    line, rolling preview from assistant deltas, tool events into the activity feed."""
    preview = {"buf": "", "last_write": 0.0}

    def on_event(name, data):
        now = time.time()
        if now - preview["last_write"] > 2.0:
            db.execute("UPDATE agents SET last_heartbeat=? WHERE id=?", (now, agent_id))
            db.execute("UPDATE dispatches SET heartbeat_at=? WHERE id=?", (now, dispatch_id))
            preview["last_write"] = now
        if name == "_line" or data is None:
            return
        if name == "assistant.delta":
            preview["buf"] = (preview["buf"] + (data.get("delta") or ""))[-200:]
            tail = " ".join(preview["buf"].split())[-70:]
            db.execute("UPDATE agents SET current_task=? WHERE id=?",
                       (f"{task_id}: …{tail}", agent_id))
        elif name == "tool.completed":
            db.log_activity("info", agent_id,
                            f"[{task_id}] tool {data.get('tool_name') or data.get('tool') or '?'} done",
                            user_id=_task_user(task_id))
        elif name == "run.started":
            db.log_activity("info", agent_id, f"[{task_id}] Hermes run started",
                            user_id=_task_user(task_id))

    return on_event


def _finalize_result(dispatch_id: str, task_id: str, agent_id: str, workspace: Path,
                     content: str, usage: dict, err_text: str | None, harvested: bool = False):
    """Common tail of every dispatch: token accounting, deliverable file, task/
    dispatch state. Raises QuotaError for rate-limit failures (caller backs off)."""
    task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if task is None:
        # The row vanished mid-run (deleted while dispatching — e.g. an e2e
        # suite's cleanup sweeping by title). Close the dispatch cleanly and
        # discard the result instead of crashing on a ghost.
        _set_dispatch(dispatch_id, state="failed", ended_at=time.time(),
                      error="task row deleted mid-run — result discarded")
        db.log_activity("warn", agent_id,
                        f"Task {task_id} was deleted while its dispatch ran — result discarded")
        return
    if err_text and is_quota_error(err_text):
        raise QuotaError(err_text)

    tin = int(usage.get("input_tokens") or 0)
    tout = int(usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (tin + tout))
    db.execute("UPDATE agents SET tokens_in=tokens_in+?, tokens_out=tokens_out+? WHERE id=?",
               (tin, tout, agent_id))
    db.execute("UPDATE tasks SET tokens_used=COALESCE(tokens_used,0)+? WHERE id=?",
               (total, task_id))
    (workspace / "_dispatch.json").write_text(json.dumps({
        "task_id": task_id, "agent_id": agent_id, "session_id": task.get("session_id"),
        "dispatch_id": dispatch_id, "usage": usage, "ended_at": time.time(),
        "harvested": harvested, "error": err_text,
    }, indent=2))

    if err_text:
        _set_task(task_id, dispatch_state="failed", dispatch_error=err_text)
        _set_dispatch(dispatch_id, state="failed", ended_at=time.time(),
                      tokens_in=tin, tokens_out=tout, error=err_text)
        db.execute("UPDATE agents SET tasks_failed=tasks_failed+1 WHERE id=?", (agent_id,))
        db.log_activity("error", agent_id, f"Task {task_id} dispatch failed: {err_text[:120]}",
                        user_id=task.get("user_id"))
        notify_desktop("Nexus: task failed", f"{task['title']} — {err_text[:120]}")
        return

    note_quota_ok()
    deliverable = workspace / "deliverable.md"
    if not deliverable.exists() and content:
        deliverable.write_text(content)
    rubric, learn = parse_deliverable_meta(content)
    new_status = "review" if task.get("high_stakes") else "done"
    fields = dict(dispatch_state="completed", result_summary=content[:4000],
                  rubric_score=rubric, learn_section=learn, status=new_status)
    if new_status == "done":
        fields["completed_at"] = time.time()
    _set_task(task_id, **fields)
    if new_status == "review":
        # R4: a high-stakes deliverable PAUSES here — a pending approval row
        # surfaces it in the approvals UI (+ nav badge) until a human decides.
        db.execute(
            "INSERT INTO approvals (id, agent_id, action_type, description, payload, "
            "status, risk_level, requested_at, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"appr-{uuid.uuid4().hex[:10]}", agent_id, "deliverable",
             f"High-stakes deliverable ready for review: '{task['title']}'",
             json.dumps({"task_id": task_id}), "pending", "high", time.time(),
             task.get("user_id")))  # the approval belongs to the task's owner
        db.log_activity("warn", agent_id,
                        f"Task {task_id} awaits approval (high-stakes) — nothing ships unjudged",
                        user_id=task.get("user_id"))
        notify_desktop("Nexus: approval needed ⚖",
                       f"High-stakes deliverable ready for review: {task['title']}")
    else:
        notify_desktop("Nexus: task done ✓", f"{task['title']} — deliverable is ready")
    _set_dispatch(dispatch_id, state="completed", ended_at=time.time(),
                  tokens_in=tin, tokens_out=tout)
    db.execute("UPDATE agents SET tasks_completed=tasks_completed+1 WHERE id=?", (agent_id,))
    db.log_activity("info", agent_id,
                    f"Task {task_id} {'harvested' if harvested else 'completed'} "
                    f"({total} tokens) → {new_status}", user_id=task.get("user_id"))


_FAILURE_PREFIXES = ("API call failed", "⏳", "⚠️ The model declined")
RESUME_QUIET_DEFAULT_S = 600  # orphan transcript silent this long = run is dead


def _final_assistant(msgs: list) -> dict | None:
    """The transcript's LAST message, only if it is a FINAL assistant text.
    An assistant message mid-run (finish_reason='tool_calls', or followed by
    tool results) is progress narration, NOT the deliverable — harvesting it
    ships a partial result and marks the task done."""
    if not msgs:
        return None
    last = msgs[-1]
    if last.get("role") != "assistant" or last.get("tool_calls"):
        return None
    if last.get("finish_reason") == "tool_calls":
        return None
    if not (last.get("content") or "").strip():
        return None
    return last


def orphan_run_state(task: dict) -> str:
    """What happened to a dead executor's orphaned Hermes run:
    'finished' — a final assistant reply is sitting in the transcript;
    'active'   — the transcript is still moving (client disconnect does NOT
                 kill a Hermes run): a continue-turn now would start a SECOND
                 concurrent run on the same session and interleave them;
    'dead'     — silent past dispatch.resume_quiet_s: safe to continue-turn;
    'gone'     — no session / unreadable transcript."""
    session_id = task.get("session_id")
    if not session_id:
        return "gone"
    try:
        msgs = get_messages(session_id)
    except Exception:
        return "gone"
    if not msgs:
        return "dead"
    if _final_assistant(msgs):
        return "finished"
    quiet = float(db.get_setting("dispatch.resume_quiet_s", str(RESUME_QUIET_DEFAULT_S)))
    age = time.time() - float(msgs[-1].get("timestamp") or 0)
    return "active" if age < quiet else "dead"


def _try_harvest(task: dict) -> dict | None:
    """R3.3: a dead executor's run finishes ORPHANED on the Hermes side and lands
    in state.db. If a FINAL assistant reply exists, recover it without spending
    a single new token. Returns {content, usage} or None."""
    session_id = task.get("session_id")
    if not session_id:
        return None
    try:
        msgs = get_messages(session_id)
    except Exception:
        return None
    last_asst = _final_assistant(msgs)
    if not last_asst:
        return None
    content = last_asst["content"]
    if content.startswith(_FAILURE_PREFIXES):
        return None
    # Usage delta: session carries cumulative tokens; subtract what we've billed.
    # (Baseline caveat: if the task was ever fresh-re-dispatched after a dead
    # session, tokens_used still includes the old session — the delta clamps to
    # 0 and undercounts. Narrow, accepted.)
    sess = get_session(session_id) or {}
    seen = int(task.get("tokens_used") or 0)
    delta = max(0, int(sess.get("input_tokens") or 0)
                + int(sess.get("output_tokens") or 0) - seen)
    # Book the whole delta as output so the daily-cap (dispatches SUM) and the
    # watchdog cost-cap (agents.tokens_*) SEE harvested tokens — the in/out
    # split is unknowable here, the guardrails matter more.
    return {"content": content,
            "usage": {"input_tokens": 0, "output_tokens": delta,
                      "total_tokens": delta}}


def run_task_dispatch(dispatch_id: str, task_id: str, agent_id: str,
                      resume: bool = False) -> dict:
    """Execute one claimed task as a real Hermes session. Blocking; call from the
    lane's worker process. resume=True = the previous executor died mid-dispatch:
    harvest the orphaned result if it finished, else send a continue-turn into
    the SAME session (context kept); fresh re-dispatch only if the session died."""
    task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    agent = db.query_one("SELECT * FROM agents WHERE id=?", (agent_id,))
    if not task or not agent:
        _set_dispatch(dispatch_id, state="failed", ended_at=time.time(),
                      error="task or agent vanished before dispatch")
        return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))

    workspace = WORKSPACES / task_id
    workspace.mkdir(parents=True, exist_ok=True)
    db.execute("UPDATE agents SET status='busy', current_task=? WHERE id=?",
               (f"{task_id}: dispatching…", agent_id))
    _set_task(task_id, workspace_path=str(workspace))
    on_event = _make_on_event(dispatch_id, task_id, agent_id)

    try:
        # Free recovery first: the orphaned run may already be complete (R3.3).
        if resume:
            state = orphan_run_state(task)
            if state == "finished":
                harvested = _try_harvest(task)
                if harvested:
                    _set_task(task_id, dispatch_state="finalizing")
                    _finalize_result(dispatch_id, task_id, agent_id, workspace,
                                     harvested["content"], harvested["usage"], None, harvested=True)
                    return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))
            elif state == "active":
                # The orphaned run is STILL EXECUTING on the Hermes side — a
                # continue-turn now would open a second concurrent run on the
                # same session. Refresh the heartbeat and wait; the lane's
                # stale check re-enters here until it finishes or goes quiet.
                _set_dispatch(dispatch_id, session_id=task.get("session_id"),
                              state="streaming", heartbeat_at=time.time())
                _set_task(task_id, dispatch_state="streaming")
                db.log_activity("info", agent_id,
                                f"Task {task_id}: orphaned run still active — waiting, not resuming")
                return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))
            if task.get("session_id") and get_session(task["session_id"]) is None:
                # Session unusable → fall back to a fresh re-dispatch (R3.4).
                db.log_activity("warn", agent_id,
                                f"Task {task_id}: session {task['session_id']} gone — fresh re-dispatch")
                _set_task(task_id, session_id=None)
                task["session_id"] = None

        # Test-only fault injection for the quota gate (SPEC R7.3) — off by default.
        if db.get_setting("dispatch.force_429") == "1":
            raise QuotaError("simulated 429 (dispatch.force_429)")

        blocked = check_budgets(task)
        if blocked:
            _set_task(task_id, dispatch_state=blocked,
                      dispatch_error=f"{blocked} at dispatch time")
            _set_dispatch(dispatch_id, state=blocked, ended_at=time.time(), error=blocked)
            db.log_activity("warn", agent_id, f"Task {task_id} not dispatched: {blocked}",
                            user_id=task.get("user_id"))
            return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))

        session_id = task.get("session_id")
        if not session_id:
            _set_task(task_id, dispatch_state="dispatching")
            session_id = create_session(f"nexus:{task_id}", model=task.get("model"))
            _set_task(task_id, session_id=session_id)
            task["session_id"] = session_id
        # M3 + Block 1: session memory scoping — client tag isolates client
        # facts, user tag isolates the owner's memories from other users.
        publish_session_scope(session_id, client=task.get("client"),
                              user=task.get("user_id"))
        _set_dispatch(dispatch_id, session_id=session_id, state="streaming",
                      heartbeat_at=time.time())
        _set_task(task_id, dispatch_state="streaming", dispatch_error=None)
        db.log_activity("info", agent_id,
                        f"{'Resuming' if resume else 'Dispatched'} task {task_id} "
                        f"('{task['title']}') via Hermes session {session_id}",
                        user_id=task.get("user_id"))

        repo_ctx = _repo_context(task)
        if task.get("repo_path") and not repo_ctx:
            _set_task(task_id, dispatch_state="failed",
                      dispatch_error=f"repo worktree setup failed for {task.get('repo_path')}")
            _set_dispatch(dispatch_id, state="failed", ended_at=time.time(),
                          error="worktree setup failed")
            db.log_activity("error", agent_id,
                            f"Task {task_id}: could not create worktree in {task.get('repo_path')}")
            return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))
        framing = build_framing(task, workspace, repo_ctx)
        if resume:
            input_text = (f"You were interrupted mid-task. Continue task {task_id} now and "
                          "finish it. The original instructions still apply: write the final "
                          f"deliverable to {workspace}/deliverable.md and reply with the "
                          "complete final deliverable text.")
        else:
            input_text = f"{task['title']}\n\n{task.get('description') or ''}".strip()
        result = stream_turn(session_id, input_text, system_message=framing, on_event=on_event,
                             max_seconds=int(db.get_setting("dispatch.max_turn_seconds",
                                                            str(DEFAULT_MAX_TURN_SECONDS))))

        _set_task(task_id, dispatch_state="finalizing")
        content = result.get("content") or ""
        if repo_ctx:
            # The branch diff IS the deliverable: snapshot anything the agent
            # left uncommitted (never lose work), then capture the full diff
            # vs the baseline into the workspace for review/UI/judging.
            try:
                if wt.snapshot_commit(repo_ctx["worktree"],
                                      f"nexus {task_id}: uncommitted-work snapshot"):
                    db.log_activity("warn", agent_id,
                                    f"Task {task_id}: agent left uncommitted changes — snapshot-committed")
                diff = wt.capture_diff(repo_ctx["worktree"], repo_ctx["base"])
                (workspace / "changes.diff").write_text(diff or "(no changes on the branch)\n")
                db.log_activity("info", agent_id,
                                f"Task {task_id}: captured branch diff "
                                f"({len(diff.splitlines())} lines) from {repo_ctx['branch']}")
            except Exception as e:
                db.log_activity("error", agent_id,
                                f"Task {task_id}: diff capture failed: {str(e)[:100]}")
        # Hermes surfaces upstream provider failures (e.g. Z.ai 429 after retries)
        # as assistant TEXT with no error event — a partial flag and/or the
        # "API call failed" wrapper string are the reliable signals.
        err_text = result.get("error")
        if not err_text and (result.get("partial") or content.startswith(_FAILURE_PREFIXES)):
            err_text = (content or "run ended partial/interrupted")[:300]
        _finalize_result(dispatch_id, task_id, agent_id, workspace,
                         content, result.get("usage") or {}, err_text)

    except QuotaError as e:
        backoff = note_quota_hit()
        _set_task(task_id, dispatch_state="blocked_quota", dispatch_error=str(e)[:300])
        _set_dispatch(dispatch_id, state="blocked_quota", ended_at=time.time(), error=str(e)[:300])
        db.log_activity("warn", agent_id, f"Task {task_id} blocked by quota — backoff {backoff}s",
                        user_id=_task_user(task_id))
    except Exception as e:
        _set_task(task_id, dispatch_state="failed", dispatch_error=str(e)[:300])
        _set_dispatch(dispatch_id, state="failed", ended_at=time.time(), error=str(e)[:300])
        db.execute("UPDATE agents SET tasks_failed=tasks_failed+1 WHERE id=?", (agent_id,))
        db.log_activity("error", agent_id, f"Task {task_id} dispatch crashed: {str(e)[:120]}",
                        user_id=_task_user(task_id))
    finally:
        # A lane with a live worker is always 'running' (never 'idle') — the
        # watchdog only heals running/busy/crashed, so 'idle' would be a
        # self-heal blind spot for a later worker death.
        db.execute("UPDATE agents SET status='running', current_task='' "
                   "WHERE id=? AND status='busy'", (agent_id,))

    return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))


def start_dispatch(task_id: str, agent_id: str) -> str:
    """Create the dispatches audit row. Caller must already own the claim."""
    did = f"disp-{uuid.uuid4().hex[:10]}"
    db.execute(
        "INSERT INTO dispatches (id, task_id, agent_id, started_at, state) VALUES (?,?,?,?,?)",
        (did, task_id, agent_id, time.time(), "queued"))
    db.execute("UPDATE tasks SET dispatch_state='queued' WHERE id=?", (task_id,))
    return did
