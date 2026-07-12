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
import shutil
import time
import uuid
import datetime as dt
from pathlib import Path

import httpx

import auth
import database as db
import feedback_log
import settings_registry as sreg

BASE_DIR = Path(__file__).parent
WORKSPACES = BASE_DIR / "workspaces"

HERMES_API_BASE = sreg.conf("hermes.api_base")  # setting → env → default; restart applies

# SSE keepalives arrive every ~30s, so a 120s read timeout only trips when the
# stream is genuinely dead. No overall HTTP timeout — the turn guards below rule.
STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
# Wall-clock backstop per dispatched turn. NOT a kill switch: run_task_dispatch
# treats hitting it as "detach and wait" (the orphaned run keeps executing and
# is harvested), so this only bounds a runaway run — healthy long tasks are
# governed by the stall guard, which measures silence, not duration.
DEFAULT_MAX_TURN_SECONDS = 14400
# Cut the SSE stream when the run emits no real event for this long. Keepalive
# comment lines don't count — they flow even when the run is hung. Sized to
# clear a single silent long-running tool call (test suite, npm install).
DEFAULT_TURN_STALL_SECONDS = 900
# Matched by identity in run_task_dispatch — a cut turn is recoverable, so its
# dispatch must NOT be finalized as failed (the run survives the disconnect).
TURN_CAP_ERROR = "turn exceeded max_seconds cap; run may finish orphaned (recover via transcript)"
TURN_STALLED_ERROR = "turn stalled — no SSE event within the stall window; run may finish orphaned (recover via transcript)"


def is_turn_cut(err: str | None) -> bool:
    """A cut turn (wall-clock cap / stall guard / dropped socket). The Hermes
    RUN survives the disconnect and usually finishes orphaned — for dispatches
    this is recoverable (wait → harvest/continue), never a terminal failure."""
    return bool(err) and (err.startswith(TURN_CAP_ERROR)
                          or err.startswith(TURN_STALLED_ERROR))

QUOTA_SIGNATURES = ("429", "rate limit", "rate_limit", "too many concurrent", "quota")


class QuotaError(Exception):
    """Hermes/Z.ai rate-limit or quota-window exhaustion."""


class GatewayBusyError(Exception):
    """The Hermes gateway is up but saturated (heavy concurrent turns) —
    transient; callers should surface 'busy, try again shortly', not a 502."""


class DispatchCancelled(Exception):
    """Operator pressed stop (tasks.cancel_requested set) — the executor aborts
    the streaming turn and finalizes as cancelled instead of failed."""


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    key = os.environ.get("API_SERVER_KEY", "")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def is_quota_error(text: str) -> bool:
    t = (text or "").lower()
    return any(sig in t for sig in QUOTA_SIGNATURES)


def classify_failure(err) -> str:
    """Coarse, greppable taxonomy of WHY a dispatch/worker died — logged as
    [cause=…] in the activity feed so failure storms can be diagnosed from the
    logs instead of guessed at (CUDA OOM vs Hermes timeout vs quota vs other)."""
    t = str(err or "").lower()
    if not t:
        return "unknown"
    if ("cuda" in t and ("out of memory" in t or "oom" in t)) \
            or "cudaerrormemoryallocation" in t or "cublas" in t:
        return "cuda-oom"
    if is_quota_error(t):
        return "quota"
    if "timeout" in t or "timed out" in t or "exceeded max_seconds" in t \
            or "turn stalled" in t:
        return "hermes-timeout"
    if "gateway did not respond" in t or "connecterror" in t or "connection refused" in t \
            or "connection reset" in t or "all connection attempts failed" in t:
        return "gateway-unreachable"
    if "database is locked" in t or "sqlite" in t:
        return "sqlite"
    return "other"


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
    system_prompt: stored by the upstream api_server but NEVER injected into
    chat turns (verified 2026-07-11 — same upstream flaw class as the
    session-model core-mod). It only seeds the session title and a metadata
    flag. ANY role lock must ALSO ride every turn as the per-turn ephemeral
    system_message, or it silently never reaches the model (the Deep Plan
    interviewer executed its goal with tools because of exactly this).
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
    remove_session_key(session_id)  # Settings v2: no dangling bridge keys


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
                on_event=None, max_seconds: int | None = None,
                stall_seconds: int | None = None) -> dict:
    """Send one turn and consume its SSE stream to completion.

    on_event(name, data_dict) fires for every parsed event (heartbeats, live
    preview, activity). Returns {content, usage, error}. Raises QuotaError on
    rate-limit signatures so callers can back off instead of hammering.
    max_seconds is a wall-clock cap (right for one-reply interactive chats);
    stall_seconds cuts on SILENCE instead — no parsed event for that long
    (keepalive comment lines don't count: they flow even when the run is hung).
    Dispatch passes both; a cut turn returns TURN_CAP_ERROR/TURN_STALLED_ERROR
    and the caller decides whether that is terminal (for dispatches it is NOT —
    the orphaned run survives the disconnect and is waited on / harvested).
    """
    url = f"{HERMES_API_BASE}/api/sessions/{session_id}/chat/stream"
    payload = {"input": input_text}
    if system_message:
        payload["system_message"] = system_message
    deadline = time.time() + (max_seconds or DEFAULT_MAX_TURN_SECONDS)
    last_progress = time.time()
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
            try:
                for line in resp.iter_lines():
                    if on_event:
                        on_event("_line", None)  # every line (incl. keepalives) = liveness
                    now = time.time()
                    if line.startswith("event: "):
                        event_name = line[7:].strip()
                        continue  # its data line is imminent — guard between complete events
                    if line.startswith("data: "):
                        last_progress = now  # a real event — the run is making progress
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
                    # Guards run AFTER the line is processed: a final event landing
                    # at/past the boundary is captured, not discarded. With
                    # run.completed already in hand the cut costs nothing — same
                    # rule as the TransportError 'if not usage' guard below.
                    if now > deadline:
                        if not usage and not error:
                            error = TURN_CAP_ERROR
                        break
                    if stall_seconds and now - last_progress > stall_seconds:
                        if not usage and not error:
                            error = TURN_STALLED_ERROR
                        break
            except httpx.TransportError as e:
                # The SOCKET died mid-turn (read timeout past the keepalives, a
                # gateway hiccup) — the RUN did not: it finishes orphaned, same
                # as a cap cut. Only a dispatch caller treats this as
                # recoverable; interactive callers surface it as the error.
                if not usage:  # with run.completed already seen, the drop cost nothing
                    error = f"{TURN_STALLED_ERROR} [stream dropped: {type(e).__name__}]"

    if error and is_quota_error(error):
        raise QuotaError(error)
    return {"content": content, "usage": usage, "error": error, "partial": partial}


# ── Per-model concurrency slots ──
# Z.ai allows ~10 concurrent requests PER MODEL and the Hermes API server caps
# 10 concurrent runs TOTAL. We stay under both (defaults 8/8, configurable) by
# COUNTING live dispatches before sending — a task without a free slot WAITS in
# the queue instead of hitting an upstream error.

# C2 (rotation readiness): the ultimate dispatch fallback resolves through the
# ONE fallback map in database.py, so a generation rotation edits the registry —
# not this literal. Kept as a module constant (read once at import) for the hot
# path; a plain string tail-guards a missing/renamed purpose.
DEFAULT_MODEL = db.fallback_model("complicated") or "glm-5.2"
SLOT_HEARTBEAT_FRESH_S = 120  # a dispatch silent this long holds no upstream slot


def slots_in_use() -> dict:
    """Live in-flight dispatch counts per EFFECTIVE run model (fresh executor
    heartbeats only). Each dispatch persists the model it actually runs on
    (dispatches.model — overload fallback included); tasks.model is only the
    pre-fallback intent, so counting by it booked every fallback dispatch under
    the original model and over-admitted the fallback pool. tasks.model remains
    the fallback for legacy rows still in flight across the upgrade."""
    cutoff = time.time() - SLOT_HEARTBEAT_FRESH_S
    rows = db.query_all(
        "SELECT COALESCE(d.model, t.model) AS model "
        "FROM dispatches d LEFT JOIN tasks t ON t.id = d.task_id "
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


# ── Orphaned-dispatch reconciler ──
# A task can end up with an ACTIVE dispatch_state ('queued'/'dispatching'/
# 'streaming'/'finalizing') while no executor is actually working it: its worker
# died leaving the row behind, or its kanban status drifted so the task matches
# NEITHER the worker's resume query (status='in_progress' + its own claim) NOR the
# auto-claim query (status='todo') — e.g. a 'backlog' task stuck at 'streaming'.
# The watchdog heals dead LANES, not orphaned dispatch ROWS, so such a task — and
# any workflow waiting on it — strands forever. This is the safety net: it spots
# them (newest in-flight dispatch silent past the threshold) and resets each to a
# clean, re-claimable state so a lane picks it up fresh.
RECONCILE_STALE_S = 600  # a dispatch silent this long (>> the 30s keepalive and the
                         # worker's own 90s resume window) has no live executor
RECONCILE_LANE_FRESH_S = 120  # an agent heartbeating within this window has a live
                              # worker process (the lane loop beats every ~2s)


def reconcile_stalled_dispatches(stale_s: int | None = None, source: str = "watchdog") -> list[str]:
    """Re-queue tasks stranded in an active dispatch_state with a dead heartbeat.

    Scope: ONLY dispatches no live executor will ever pick up again. Two guards
    keep it from clobbering healthy work:
      - a task claimed by an agent whose worker still heartbeats, with
        status='in_progress' (so it matches that lane's own work query), is
        merely PARKED — e.g. waiting for a free per-model concurrency slot, or
        inside the lane's own 90s resume window. The lane handles it; skip.
      - a task whose orphaned Hermes run is still executing ('active') or
        already finished ('finished') keeps its session_id: the re-queued task
        flows into the resume path (harvest the finished result for free, or
        wait out / continue the live run) instead of abandoning that work in a
        fresh dispatch. This also makes the BOOT-time reconcile defer to
        resume after a long outage. Gateway unreachable → defer the decision
        to the next sweep rather than guessing.

    Returns the reset task ids. Otherwise mirrors _retry_task's reset shape
    (session_id=NULL forces a FRESH dispatch — never a 'continue' into a
    half-briefed/broken session). A live dispatch heartbeats at least every
    ~30s (SSE keepalive, even mid-tool-call), so the default threshold never
    catches running work; tune via setting dispatch.reconcile_stale_s.
    """
    if stale_s is None:
        try:
            stale_s = int(db.get_setting("dispatch.reconcile_stale_s", str(RECONCILE_STALE_S)))
        except (TypeError, ValueError):
            stale_s = RECONCILE_STALE_S
    now = time.time()
    cutoff = now - stale_s
    default_budget = int(sreg.conf("dispatch.default_task_budget") or 5000000)
    active = ("queued", "dispatching", "streaming", "finalizing")
    placeholders = ",".join("?" * len(active))
    reset: list[str] = []
    gateway_ok: bool | None = None  # probed lazily, once per sweep
    for t in db.query_all(
            "SELECT id, user_id, status, claimed_by, session_id, tokens_used, "
            f"budget_tokens FROM tasks WHERE dispatch_state IN ({placeholders})", active):
        tid = t["id"]
        hb = db.query_one(
            "SELECT MAX(COALESCE(heartbeat_at, started_at, 0)) AS ts FROM dispatches "
            f"WHERE task_id=? AND state IN ({placeholders})", (tid, *active))
        ts = (hb or {}).get("ts") or 0
        if ts > cutoff:
            continue  # a live (or recently-live) executor is on it — leave it
        if t.get("claimed_by") and t.get("status") == "in_progress":
            ag = db.query_one("SELECT last_heartbeat FROM agents WHERE id=?",
                              (t["claimed_by"],))
            if ag and float(ag.get("last_heartbeat") or 0) > now - RECONCILE_LANE_FRESH_S:
                continue  # a live lane owns this claim (slot-parked, not dead)
        keep_session = False
        if t.get("session_id"):
            if gateway_ok is None:
                gateway_ok = bool(api_health().get("connected"))
            if not gateway_ok:
                continue  # can't judge the session (gateway down, e.g. early boot) — next sweep
            keep_session = orphan_run_state(t) in ("finished", "active")
        # 1) close the orphaned in-flight rows so they can't be resumed or miscounted
        db.execute(
            "UPDATE dispatches SET state='failed', ended_at=?, "
            "error='reconciled: orphaned dispatch (stale heartbeat), task re-queued' "
            f"WHERE task_id=? AND state IN ({placeholders})", (now, tid, *active))
        # 2) one attempt's budget headroom so a stranded task doesn't re-block instantly
        used = int(t.get("tokens_used") or 0)
        if used > 0:
            db.execute("UPDATE tasks SET budget_tokens=? WHERE id=?",
                       (used + int(t.get("budget_tokens") or default_budget), tid))
        # 3) reset to a clean, claimable state. session kept => the next lane
        #    RESUMES (harvest/continue); session_id=NULL => fresh dispatch.
        if keep_session:
            db.execute(
                "UPDATE tasks SET status='todo', dispatch_state='none', "
                "claimed_by=NULL, claimed_at=NULL, dispatch_error=NULL, updated_at=? WHERE id=?",
                (now, tid))
        else:
            db.execute(
                "UPDATE tasks SET status='todo', dispatch_state='none', session_id=NULL, "
                "claimed_by=NULL, claimed_at=NULL, dispatch_error=NULL, updated_at=? WHERE id=?",
                (now, tid))
        # 4) expire the now-superseded deliverable approval, if any (parity with _retry_task)
        db.execute(
            "UPDATE approvals SET status='expired', decided_at=?, decided_by='reconciled: task reset' "
            "WHERE status='pending' AND action_type='deliverable' AND payload LIKE ?",
            (now, f'%"task_id": "{tid}"%'))
        db.log_activity("warn", source,
                        f"Task {tid}: reconciled orphaned dispatch (no heartbeat for "
                        f"{int((now - ts) / 60)}m) — re-queued "
                        + ("to resume its live/harvestable session" if keep_session
                           else "for a fresh attempt"),
                        user_id=t.get("user_id"))
        reset.append(tid)
    return reset


# ── Budgets & quota backoff (SPEC R7) ──

def _type_setting(prefix: str, task: dict, fallback: int) -> int:
    """Item 17: per-deliverable-type override (e.g. dispatch.turn_seconds.content)
    falling back to the global value — content tasks don't need a 4h cap or a
    5M budget."""
    dtype = (task.get("deliverable_type") or "").strip()
    if dtype:
        v = sreg.conf(f"{prefix}.{dtype}")  # setting → registry default → ""
        if v:
            try:
                return int(float(v))
            except (TypeError, ValueError):
                pass
    return fallback


def check_budgets(task: dict) -> str | None:
    """Return a blocked-state name if this task must NOT be dispatched now.
    Task-specific budget is checked BEFORE the global quota backoff so a budget
    verdict stays deterministic even in the middle of a 429 storm."""
    budget = task.get("budget_tokens") \
        or _type_setting("dispatch.default_budget", task,
                         int(sreg.conf("dispatch.default_task_budget") or 5000000))
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


def fallback_model_for(model: str | None) -> str | None:
    """Peak-overload failover target for `model`, or None (disabled / unset /
    already the fallback). Z.ai load-sheds busy models at peak hours (429
    error 1305) — instead of parking the task behind the GLOBAL backoff, one
    retry runs on this model (its own concurrency pool, usually free)."""
    if sreg.conf("dispatch.fallback_enabled") != "1":
        return None
    fb = (sreg.conf("dispatch.fallback_model") or "").strip()
    if not fb or fb == (model or DEFAULT_MODEL):
        return None
    return fb


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


# ── Per-session API keys (Settings v2 — docs/SPEC-SETTINGS-V2.md §6) ──
# Same bridge-file pattern as model-efforts.json / client-scopes.json: the
# patched Hermes zai provider checks this map per request and falls back to
# its env key. Only sessions whose owner configured a personal/global-override
# credential get an entry — an absent entry = today's behavior. The file is
# 0600 like ~/.hermes/.env (same plaintext-at-rest posture as the default key
# it overrides); the DB copy stays encrypted.

_SESSION_KEYS_FILE = os.path.expanduser("~/.hermes/session-keys.json")
_SESSION_KEYS_MAX_AGE_S = 7 * 86400


def resolve_task_model(task: dict) -> str | None:
    """The model this task's session runs on: explicit per-task choice, else
    the owner's 'complicated' purpose assignment, else None (Hermes default)."""
    return task.get("model") or db.default_task_model(task.get("user_id"))


def _session_key_for(user_id: str | None, model_id: str | None) -> str | None:
    """The owner's key for the provider serving model_id (None = env default).
    Import here, not module-top: worker lanes only pay for cryptography once a
    credential actually exists."""
    if not user_id:
        return None
    rows = [m for m in db.visible_models(user_id, enabled_only=True)
            if m["route"] == "hermes" and (model_id is None or m["model_id"] == model_id)]
    if not rows:
        return None
    m = rows[0]
    import secrets_store
    return secrets_store.resolve_key(user_id, m["provider"], m.get("credential_id"))


def _rewrite_session_keys(mutate):
    try:
        data = {}
        if os.path.isfile(_SESSION_KEYS_FILE):
            with open(_SESSION_KEYS_FILE) as f:
                data = json.load(f)
        sessions = data.get("sessions") or {}
        mutate(sessions)
        now = time.time()
        sessions = {sid: e for sid, e in sessions.items()
                    if (e.get("ts") or now) > now - _SESSION_KEYS_MAX_AGE_S}
        tmp = f"{_SESSION_KEYS_FILE}.tmp-{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"sessions": sessions, "updated_at": now}, f, indent=1)
        os.replace(tmp, _SESSION_KEYS_FILE)  # atomic — a crash can't half-write all keys
    except Exception as e:
        db.log_activity("warn", "system", f"session-keys bridge write failed: {str(e)[:80]}")


def publish_session_key(session_id: str, user_id: str | None, model_id: str | None):
    """Give this session the owner's API key (bridge entry) — no-op when the
    owner has no credential for the serving provider. MERGES into an existing
    entry (a published per-task effort must survive)."""
    key = _session_key_for(user_id, model_id)
    if not key:
        return

    def _set(s):
        entry = dict(s.get(session_id) or {})
        entry.update({"api_key": key, "ts": time.time()})
        s[session_id] = entry
    _rewrite_session_keys(_set)


def session_effort_for_task(task: dict, model: str | None) -> str | None:
    """Mode-coherence (2026-07-12b, I-3 follow-up): the per-task reasoning
    effort — the last mode-blind knob. Deterministic, hermes effort scale;
    None = no bridge entry (the config default / per-model setting applies,
    i.e. exactly the pre-feature behavior).

    Rules: high_stakes or Smart → xhigh (maximum thinking where quality is the
    point); Eco → medium on light tiers, high once the cascade escalated it to
    the strong tier (cost-conscious even after escalation); Balanced content →
    high (creative generation gains little from maximum deliberation — the
    'when to think deeply' result; the rubric/judge still gate quality);
    Balanced research/analysis/code → None (xhigh default, reasoning-heavy)."""
    if db.get_setting("dispatch.session_effort", "1") != "1":
        return None
    sp = (task.get("spend_profile") or "").strip()
    dtype = (task.get("deliverable_type") or "").strip()
    m = (model or "").lower()
    light = "air" in m or "flash" in m or "turbo" in m
    if task.get("high_stakes") or sp == "smart":
        return "xhigh"
    if sp == "eco":
        return "medium" if light else "high"
    if dtype == "content" and not light:
        return "high"
    return None


def publish_session_effort(session_id: str, task: dict, model: str | None):
    """Publish the per-task effort into the session bridge entry (merge-safe;
    the zai plugin's session-effort core-mod reads it per request)."""
    effort = session_effort_for_task(task, model)
    if not effort:
        return

    def _set(s):
        entry = dict(s.get(session_id) or {})
        entry.update({"effort": effort, "ts": time.time()})
        s[session_id] = entry
    _rewrite_session_keys(_set)


def remove_session_key(session_id: str):
    """Drop a finished session's bridge entry (retries re-publish on dispatch)."""
    if not os.path.isfile(_SESSION_KEYS_FILE):
        return
    _rewrite_session_keys(lambda s: s.pop(session_id, None))


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
    if uid and uid != auth.DEFAULT_USER_ID:
        d = root / "users" / uid
        if (d / "BUSINESS-CONTEXT.md").is_file() and (d / "STYLE-VOICE.md").is_file():
            return {"context": str(d / "BUSINESS-CONTEXT.md"),
                    "style": str(d / "STYLE-VOICE.md")}
    return {"context": str(root / "BUSINESS-CONTEXT.md"),
            "style": str(root / "STYLE-VOICE.md")}


_EXEMPLAR_TYPES = ("content", "research", "analysis")


def _exemplar_score(rubric_text: str | None) -> float | None:
    """Parse the numeric self-score out of a deliverable's rubric line
    (e.g. 'Rubric self-score: 3.8/4' → 3.8). Best-effort — the score line is
    free text; the number before any '/' is the score on its own scale."""
    if not rubric_text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*\d+", rubric_text) or \
        re.search(r"(\d+(?:\.\d+)?)", rubric_text)
    try:
        return float(m.group(1)) if m else None
    except Exception:
        return None


def golden_exemplars(task: dict) -> list[dict]:
    """Q1: the operator's own best past work as few-shot exemplars — deterministic
    SQL, no embeddings. Past tasks of the same domain (+ same client when set)
    that the frontier judge SHIP'd and that self-scored at/above the threshold,
    same owner, freshest first; unioned with curated ~/knowledge examples
    (curated lead for reading priority, but a slot is RESERVED for the operator's
    own work so curated files can't crowd it out of exemplars.max). Guards: never
    for code_change, never on a retry round, never the task's own earlier
    versions. Returns [{"path", "own"}] dicts (own=True → the operator's own
    SHIP'd deliverable; own=False → a curated reference exemplar) so the framing
    can label them honestly; token-cheap — the executor reads them via file
    tools. L3 lifecycle: pool capped at max×3, age-out past
    exemplars.max_age_months."""
    if db.get_setting("exemplars.enabled", "1") != "1":
        return []
    dtype = (task.get("deliverable_type") or "").strip()
    if dtype not in _EXEMPLAR_TYPES:  # never for code_change (repo context suffices) / untyped
        return []
    if (task.get("retry_feedback") or "").strip():
        return []  # a retry round: the feedback matters more than exemplars
    domain = (task.get("domain") or "").strip()
    if not domain or domain == "general":
        return []
    root = Path(db.get_setting("onboarding.root", "") or os.path.expanduser("~/knowledge"))
    if not (root / "domains" / domain / "RUBRIC.md").is_file():
        return []  # only judgeable domains
    try:
        max_n = max(1, int(db.get_setting("exemplars.max", "2") or 2))
        min_score = float(db.get_setting("exemplars.min_score", "3.5") or 3.5)
        max_age_days = max(1, int(db.get_setting("exemplars.max_age_months", "12") or 12)) * 30.4
    except Exception:
        max_n, min_score, max_age_days = 2, 3.5, 365.0
    uid = task.get("user_id")
    client = (task.get("client") or "").strip()
    cutoff = time.time() - max_age_days * 86400
    # Fetch a bounded candidate pool (top-K = max×3), freshest first. client
    # narrows when the current task names one; otherwise any client of the domain.
    sql = ("SELECT id, rubric_score, completed_at, workspace_path, client, title "
           "FROM tasks WHERE judge_verdict='SHIP' AND domain=? AND user_id IS ? "
           "AND id != ? AND workspace_path IS NOT NULL AND completed_at >= ?")
    params = [domain, uid, task.get("id"), cutoff]
    if client:
        sql += " AND client=?"
        params.append(client)
    sql += " ORDER BY completed_at DESC LIMIT ?"
    params.append(max_n * 3)
    picks = []
    for r in db.query_all(sql, tuple(params)):
        sc = _exemplar_score(r.get("rubric_score"))
        if sc is None or sc < min_score:
            continue
        p = os.path.join(r.get("workspace_path") or "", "deliverable.md")
        if os.path.isfile(p):
            picks.append((sc, r.get("completed_at") or 0, p))
    picks.sort(key=lambda x: (x[0], x[1]), reverse=True)
    paths = [p for _, _, p in picks[:max_n]]  # the operator's OWN past work, best first
    # Curated reference exemplars shipped with the domain — NOT the operator's own
    # work (labelled honestly in build_framing so the executor isn't told a stock
    # example is the operator's own excellence).
    curated_dir = root / "domains" / domain / "examples"
    curated = []
    try:
        if curated_dir.is_dir():
            curated = [str(f) for f in sorted(curated_dir.iterdir())
                       if f.is_file() and f.suffix.lower() in (".md", ".txt")]
    except Exception:
        curated = []
    # Reserve at least one slot for the operator's OWN past work when both kinds
    # exist, so a domain's 2-3 curated files can't crowd it out of exemplars.max
    # (default 2) — the operator's own SHIP'd deliverable is the more authentic
    # quality bar. Curated still LEAD (they "win ties" for reading priority), but
    # only up to the budget that leaves room for the reserved own-work slot.
    reserve_own = 1 if (paths and curated and max_n >= 2) else 0
    cur_budget = max_n - reserve_own
    ordered = ([(p, False) for p in curated[:cur_budget]]
               + [(p, True) for p in paths]
               + [(p, False) for p in curated[cur_budget:]])
    out, seen = [], set()
    for p, own in ordered:
        if p not in seen:
            seen.add(p)
            out.append({"path": p, "own": own})
    return out[:max_n]


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


def build_framing(task: dict, workspace: Path, repo_ctx: dict | None = None,
                  agent_id: str | None = None) -> str:
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
                "add new versions alongside.\n"
                f"- ALSO copy every final deliverable FILE (pptx/docx/pdf/png/…) into "
                f"{workspace}/ next to deliverable.md — the operator's Deliverables view "
                "reads that folder; the project keeps its own copy on the branch.\n")
        common_tail = (
            "- COMMIT your work on the branch in clear, scoped commits (git add/commit in "
            "the worktree). Never push, never merge, never switch branches.\n"
            f"- Write {workspace}/deliverable.md as a CHANGE REPORT: what you added/changed "
            "and why, files touched, and follow-ups. The DIFF on the branch is the real "
            "deliverable — the operator reviews and merges it manually."
            # Item 17: conventions capped tighter (agents read the file on
            # demand anyway); the code map only helps CODE work — a content
            # task gains nothing from a language histogram (−4k chars/call).
            + (f"\n\nPROJECT CONVENTIONS {repo_ctx['conventions'][:4000]}"
               if repo_ctx.get("conventions") else "")
            + (f"\n\nCODE MAP (repository layout):\n{repo_ctx['code_map']}"
               if is_code and repo_ctx.get("code_map") else ""))
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
        "UNCERTAINTY TAGGING: mark every claim you could NOT verify against a primary "
        "source inline as `[UNSURE: reason]` (e.g. a number you estimated, a fact you "
        "could not confirm, an inference you drew). Unmarked claims are treated as "
        "verified assertions — the grounded critic and judge check unmarked claims to "
        "that standard and treat an unmarked-but-false claim as a critical failure, so "
        "flagging honest uncertainty PROTECTS your score.")
    if (task.get("deliverable_type") or "") != "code_change":
        # Item 17: dev stages virtually never need exchange rates/holidays —
        # the skill stays discoverable on disk; content/research keep the hint.
        parts.append(
            "When the task needs a STRUCTURED FACT — exchange rates, weather, country/market "
            "data, public holidays, economic indicators, paper/package/repo metadata, "
            "naming/word ideas, product barcodes, webshop seed data, music metadata/BPM — "
            "read ~/.hermes/skills/fetching-structured-facts/SKILL.md first: curated keyless "
            "APIs with exact commands (verified working). More precise than web search for "
            "these; for everything else use web search as usual."
        )
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
        # Feedback loop: recent domain-matching WINS/LESSONS ride with the
        # domain block — deliberately NOT skipped on retry rounds (lessons
        # matter most exactly then). Size-capped in feedback_log.
        fb_block = feedback_log.dispatch_block(domain, task.get("user_id"))
        if fb_block:
            parts.append(fb_block)
    specialist = (task.get("specialist") or "").strip()
    if specialist:
        parts.append(
            f"Delegate the whole task to the specialist '{specialist}' using your delegate_task "
            "tool (it runs synchronously here) and incorporate its full result into the deliverable."
        )
    # Q4 (project decision log): every workflow member reads the running brief of
    # binding choices earlier stages made — before its predecessor deliverables
    # (P10a framing order) — and ends its own deliverable with a ## Decisions
    # section that _finalize_result harvests back into it. ~Zero extra tokens,
    # coherence across the whole project.
    if task.get("workflow_id"):
        dpath = WORKSPACES / f"workflow-{task['workflow_id']}" / "DECISIONS.md"
        if dpath.is_file():
            parts.append(
                f"PROJECT DECISION LOG — read {dpath} FIRST: it records the binding "
                "choices earlier stages of this project already made (naming, structure, "
                "stack, tone, scope). Respect every one unless this task's brief overrides "
                "it; if you must deviate, say so explicitly and why.")
        parts.append(
            "END your deliverable with a `## Decisions` section: every choice you made "
            "that later stages of this project must respect (naming, structure, stack, "
            "tone, key trade-offs) — one line each, with the reason. Omit it only if you "
            "genuinely made no such choice.")
    # Q1 (golden exemplars): the operator's own best past work as the quality bar
    # (P10a order — after DECISIONS, before predecessor deliverables).
    exemplars = golden_exemplars(task)
    if exemplars:
        own = [e["path"] for e in exemplars if e.get("own")]
        curated = [e["path"] for e in exemplars if not e.get("own")]
        bar = ["QUALITY BAR — read these FIRST and match their quality bar, voice, depth and "
               "structure. Do NOT copy their content — this is a different task:"]
        if own:
            bar.append("The operator's OWN past deliverables for this business, rated excellent:")
            bar += [f"- {p}" for p in own]
        if curated:
            bar.append("Curated reference exemplars of excellent work in this domain (not the "
                       "operator's own — treat as the craft bar to meet):")
            bar += [f"- {p}" for p in curated]
        parts.append("\n".join(bar))
    deps = [d for d in task_dependencies(task) if d.get("status") == "done"]
    if deps:
        # framing.brief_mode (token saver): only DIRECT predecessors' deliverables
        # are ever injected (task_dependencies resolves the direct depends_on list),
        # so in brief mode a member deep in the DAG leans on the DECISIONS.md brief
        # above for cross-stage context instead of a longer reading list.
        brief_mode = db.get_setting("framing.brief_mode", "1") == "1"
        shown_deps = deps[:8]  # item 17: bound the reading list (fan-out plans)
        lines = "\n".join(
            f"- {d['workspace_path'] or 'workspaces/' + d['id']}/deliverable.md "
            f"(output of '{d['title']}')" for d in shown_deps)
        if len(deps) > len(shown_deps):
            lines += f"\n- …{len(deps) - len(shown_deps)} more predecessor deliverable(s) in their workspaces"
        parts.append(
            "This task builds on completed predecessor tasks in the same workflow. "
            "FIRST read their deliverables with your file tools — they are your input:\n"
            + lines
            + ("\n(Cross-stage decisions live in the project DECISION LOG above — you "
               "need only these direct inputs plus that log.)" if brief_mode else ""))
    # Operator attachments — P10(a) framing order: injected AFTER predecessor
    # deliverables (and DECISIONS/exemplars) so, on later-wins precedence, the
    # operator's own attached brief overrides earlier project context; only the
    # retry feedback comes later (the final word).
    atts = _attachment_lines(task, workspace)
    if atts:
        shown_atts = atts[:20]  # item 17: unbounded path lists cost tokens every call
        att_lines = "\n".join(f"- {a}" for a in shown_atts)
        if len(atts) > len(shown_atts):
            att_lines += (f"\n- …{len(atts) - len(shown_atts)} more attached file(s) — "
                          "list the attachments/ directories for the rest")
        parts.append(
            "The operator ATTACHED input files for this work — read them FIRST, they are "
            "part of the brief and take precedence over the project context above:\n"
            + att_lines
            + f"\nExtract pdf/docx/xlsx/pptx content with {DOC_TOOLS_PY} "
              "(pypdf, python-docx, openpyxl, python-pptx).")
    if task.get("retry_feedback"):
        parts.append(
            "This is a RETRY: a previous attempt was rejected. Address every point of this "
            f"feedback before delivering:\n{task['retry_feedback']}"
        )
    # Item 3: the executing lane's own memory rides with the brief — standing
    # rules the operator taught it (longterm) + its consolidated track record
    # (lts auto-summary). Capped; evals stay agent-less (config-pure).
    if agent_id and db.get_setting("agentmem.framing_enabled", "1") == "1":
        try:
            mem_bits = []
            taught = db.query_all(
                "SELECT content FROM memory WHERE agent_id=? AND scope='longterm' "
                "ORDER BY created_at DESC LIMIT 6", (agent_id,))
            if taught:
                mem_bits.append("Standing facts the operator taught this lane — honor them:\n"
                                + "\n".join(f"- {r['content'][:200]}" for r in taught))
            summ = db.query_one(
                "SELECT content FROM memory WHERE agent_id=? AND scope='lts' "
                "AND kind='auto-summary' ORDER BY created_at DESC LIMIT 1", (agent_id,))
            if summ:
                mem_bits.append(f"This lane's track record: {summ['content'][:400]}")
            if mem_bits:
                parts.append(("AGENT LANE MEMORY:\n" + "\n".join(mem_bits))[:800])
        except Exception:
            pass
    parts.append("Finally, reply in chat with the complete final deliverable text — the reply is "
                 "stored as the task result.")
    return "\n\n".join(parts)


_DECISIONS_RE = re.compile(
    r"^\s{0,3}#{1,6}\s*Decisions\s*$(.*?)(?=^\s{0,3}#{1,6}\s|\Z)",
    re.I | re.M | re.S)


def parse_decisions_section(text: str) -> str | None:
    """Q4: pull the `## Decisions` section body out of a deliverable (any
    heading level). Returns the trimmed bullet block or None."""
    m = _DECISIONS_RE.search(text or "")
    if not m:
        return None
    body = m.group(1).strip()
    return body[:4000] or None


def harvest_decisions(task: dict, content: str):
    """Q4 harvest (deterministic, no LLM): record this task's `## Decisions`
    lines in its project's running DECISIONS.md so every later stage reads a
    coherent log of the choices already made. [6]: ONE block per task — a
    rework round REPLACES the task's block (keyed by a task-id marker) instead
    of appending a duplicate; later stages are told the log is binding, so a
    stale block from a rejected draft would anchor them to reversed choices."""
    wid = task.get("workflow_id")
    if not wid:
        return
    body = parse_decisions_section(content)
    if not body:
        return
    try:
        import fcntl
        wdir = WORKSPACES / f"workflow-{wid}"
        wdir.mkdir(parents=True, exist_ok=True)
        path = wdir / "DECISIONS.md"
        stamp = time.strftime("%Y-%m-%d")
        header = "# Project decisions\n\nThe binding choices each stage made. Later stages MUST respect these.\n"
        marker = f"<!-- task:{task['id']} -->"
        # Final-review F3: collapse whitespace — a newline in the title would
        # strand the marker off the `### ` line, so the supersede regex below
        # silently no-ops and the rework's decisions never land.
        title = re.sub(r"\s+", " ", str(task.get("title") or task["id"])).strip()[:120]
        block = f"\n### {title} ({stamp}) {marker}\n{body}\n"
        # Read-modify-write under an exclusive lock: parallel lanes finalizing
        # siblings of the same workflow must not erase each other's blocks.
        with path.open("a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            text = f.read() or header
            if marker in text:
                pat = re.compile(r"\n### [^\n]*" + re.escape(marker)
                                 + r"[^\n]*\n.*?(?=\n### |\Z)", re.S)
                text = pat.sub(lambda m: block, text, count=1)
            else:
                text += block
            f.seek(0)
            f.truncate()
            f.write(text)
    except Exception as e:
        db.log_activity("warn", "dispatch",
                        f"decision-log harvest failed for {task.get('id')}: {str(e)[:80]}")


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


def _repo_diff_present(workspace: Path) -> bool:
    """Repo mode: a non-empty branch diff captured at finalize = real work
    shipped on the branch, whatever the chat reply looks like."""
    p = workspace / "changes.diff"
    try:
        if not p.is_file():
            return False
        d = p.read_text().strip()
        return bool(d) and not d.startswith("(no changes")
    except Exception:
        return False


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
        # Telemetry only: a transient SQLite error (locked/busy under load)
        # must never abort the live SSE stream it decorates — the next event
        # retries the same writes anyway. Exception: the cancel poll below
        # RAISES on purpose to abort the stream.
        now = time.time()
        cancel = False
        try:
            if now - preview["last_write"] > 2.0:
                db.execute("UPDATE agents SET last_heartbeat=? WHERE id=?", (now, agent_id))
                db.execute("UPDATE dispatches SET heartbeat_at=? WHERE id=?", (now, dispatch_id))
                preview["last_write"] = now
                # Item 5 (stop): keepalives arrive ~30s apart even during
                # silent tool calls, so this bounds stop latency to ~30s.
                row = db.query_one("SELECT cancel_requested FROM tasks WHERE id=?", (task_id,))
                cancel = bool(row and row.get("cancel_requested"))
            if not cancel:
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
                    if isinstance(data, dict) and data.get("run_id"):
                        db.execute("UPDATE dispatches SET run_id=? WHERE id=?",
                                   (str(data["run_id"])[:80], dispatch_id))
                    db.log_activity("info", agent_id, f"[{task_id}] Hermes run started",
                                    user_id=_task_user(task_id))
        except Exception:
            pass
        if cancel:
            raise DispatchCancelled(f"stop requested for {task_id}")

    return on_event


def _write_experience(agent_id: str, task: dict, outcome: str, tokens: int,
                      err: str | None = None, learn: str | None = None,
                      rubric=None):
    """Item 3: one deterministic 'experience' row per finished dispatch — the
    lane's task log (Agent memory tab). No LLM; the hourly consolidation sweep
    (agent_memory.py) condenses these into the lane's rolling 'lts' summary.
    Best-effort: memory failures never fail a dispatch."""
    try:
        if db.get_setting("agentmem.enabled", "1") != "1":
            return
        ttl_days = float(db.get_setting("agentmem.experience_ttl_days", "90") or 90)
        bits = [f"[{outcome}] {(task.get('title') or '?')[:80]}"]
        if task.get("specialist"):
            bits.append(f"specialist={task['specialist']}")
        if task.get("domain") and task.get("domain") != "general":
            bits.append(f"domain={task['domain']}")
        bits.append(f"{tokens:,} tok")
        if rubric is not None:
            bits.append(f"self-score {rubric}")
        if learn:
            bits.append(f"learned: {' '.join(str(learn).split())[:300]}")
        if err:
            bits.append(f"failed: {' '.join(str(err).split())[:160]}")
        now = time.time()
        db.execute(
            "INSERT INTO memory (id, agent_id, scope, kind, content, source, "
            "created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
            (f"mem-{uuid.uuid4().hex[:10]}", agent_id, "experience", "dispatch",
             " · ".join(bits)[:1000], "auto", now, now + ttl_days * 86400))
        # The in-flight scratchpad row is consumed by the finished task.
        db.execute("DELETE FROM memory WHERE agent_id=? AND scope='stm' "
                   "AND kind='inflight' AND content LIKE ?",
                   (agent_id, f"%{task.get('id')}%"))
    except Exception:
        pass


def _finalize_cancel(dispatch_id: str, task_id: str, agent_id: str):
    """Operator stop (item 5): close the dispatch as 'cancelled' and park the
    task back in Backlog, unclaimed. session_id is dropped ON PURPOSE — the
    orphaned upstream run (if any) must never be waited on or harvested (the
    operator said stop), and the next dispatch starts fresh."""
    task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if task and task.get("session_id"):
        remove_session_key(task["session_id"])
    _set_dispatch(dispatch_id, state="cancelled", ended_at=time.time(),
                  error="stopped by operator")
    _set_task(task_id, status="backlog", dispatch_state="cancelled",
              claimed_by=None, claimed_at=None, session_id=None,
              cancel_requested=None, dispatch_error=None)
    db.log_activity("warn", agent_id,
                    f"Task {task_id} stopped by operator — returned to Backlog",
                    user_id=_task_user(task_id))
    if task:
        notify_desktop("Nexus: task stopped ⏹", f"{task['title']} — back in Backlog")


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
    if task.get("session_id"):
        # Settings v2: the run is over — drop its bridge-key entry (a retry
        # re-publishes on its next dispatch).
        remove_session_key(task["session_id"])
    if err_text and is_quota_error(err_text):
        raise QuotaError(err_text)
    # Real 429 storms don't always raise: on sessions WITH history (e.g. a
    # resume continue-turn) the run completes CLEANLY with either empty
    # content or the raw error string AS the reply ("API call failed after
    # 3 retries: HTTP 429: …") — no error event, no exception (both shapes
    # verified 2026-07-08 against the live gateway; fresh first turns raise
    # instead). But an empty/short reply is NOT proof of a quota hit: in repo
    # mode the branch diff is the real deliverable (a terse reply with a
    # non-empty changes.diff is a SUCCESS), and QuotaError pauses EVERY lane
    # via note_quota_hit. So: only an actual rate-limit signature in the reply
    # enters the quota machinery (fallback retry, then backoff); a
    # signature-less empty run fails THIS task only.
    stripped = (content or "").strip()
    if not err_text and not harvested and not (workspace / "deliverable.md").exists() \
            and not _repo_diff_present(workspace):
        if stripped and len(stripped) < 300 and is_quota_error(stripped):
            raise QuotaError(stripped)
        if not stripped:
            err_text = "empty run result — upstream produced no content"

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
        db.log_activity("error", agent_id,
                        f"Task {task_id} dispatch failed [cause={classify_failure(err_text)}]: "
                        f"{err_text[:120]}", user_id=task.get("user_id"))
        notify_desktop("Nexus: task failed", f"{task['title']} — {err_text[:120]}")
        _write_experience(agent_id, task, "failed", total, err=err_text)
        return

    note_quota_ok()
    deliverable = workspace / "deliverable.md"
    if not deliverable.exists() and content:
        deliverable.write_text(content)
    harvest_decisions(task, content)  # Q4: append this stage's ## Decisions to the project log
    rubric, learn = parse_deliverable_meta(content)
    new_status = "review" if task.get("high_stakes") else "done"
    # The completed rework consumed its feedback — clear it. Left set, a later
    # unrelated re-dispatch still opens with a stale "This is a RETRY" block,
    # exemplar injection stays suppressed for the task's lifetime, and (since
    # previous feedback outranks judge findings in _retry_task) a reject
    # without comment would resend THIS round's feedback instead of the newest
    # judge report. Failed dispatches keep it: their next attempt needs it.
    fields = dict(dispatch_state="completed", result_summary=content[:4000],
                  rubric_score=rubric, learn_section=learn, status=new_status,
                  retry_feedback=None)
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
             # Q7b: decision-card fields so the inbox renders headline/why/cost.
             json.dumps({"task_id": task_id,
                         "headline": f"“{task['title']}” is ready for your review.",
                         "recommendation": "Approve & ship",
                         "reasons": ["high-stakes deliverable — nothing ships unjudged",
                                     "review the work, or send it back with changes"],
                         "cost_hint": ""}),
             "pending", "high", time.time(),
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
    _write_experience(agent_id, task, "completed", total, learn=learn, rubric=rubric)
    try:  # L1: capture the routing outcome at this terminal task state
        import routing as _routing
        _routing.record_outcome(task_id)
    except Exception:
        pass
    db.log_activity("info", agent_id,
                    f"Task {task_id} {'harvested' if harvested else 'completed'} "
                    f"({total} tokens) → {new_status}", user_id=task.get("user_id"))


_FAILURE_PREFIXES = ("API call failed", "⏳", "⚠️ The model declined")
RESUME_QUIET_DEFAULT_S = 600  # orphan transcript silent this long = run is dead
# Floor margin over the stall cutoff for the effective quiet window. A run that
# survives a stall-cut is BY DEFINITION already silent > stall when the lane
# re-enters (~stall + 90s STALE_DISPATCH_S), so any quiet ≤ stall guarantees a
# false 'dead' verdict and a continue-turn into a live run. Covers the
# cut→re-entry lag (90s) + the 120s read timeout + flush lag.
RESUME_QUIET_MARGIN_S = 300


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
    # Effective quiet is floored above the stall cutoff: raising the stall
    # auto-raises quiet; lowering quiet below the floor is a no-op. Derived
    # HERE — the single choke point shared by worker._wait_on_active_orphan,
    # the resume path, and reconcile_stalled_dispatches.keep_session.
    stall = float(db.get_setting("dispatch.max_turn_stall_seconds",
                                 str(DEFAULT_TURN_STALL_SECONDS)))
    quiet = max(quiet, stall + RESUME_QUIET_MARGIN_S)
    age = time.time() - float(msgs[-1].get("timestamp") or 0)
    return "active" if age < quiet else "dead"


def _turn_cut_count(task_id: str) -> int:
    """How many of this task's dispatches were cut mid-turn (cap/stall). The
    worker's supersede preserves the cut error on the old row, so this survives
    the lane re-entry churn. Bounds the resume budget auto-extension."""
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM dispatches WHERE task_id=? AND "
        "(error LIKE 'turn exceeded max_seconds cap%' OR error LIKE 'turn stalled%')",
        (task_id,))
    return int((row or {}).get("n") or 0)


# Item 1: non-code artifact files (a .pptx, a PDF report, images…) created on
# a task branch ARE the user-facing deliverable for content-in-repo tasks —
# but the Deliverables UI reads only the workspace. Mirror them there.
ARTIFACT_EXTS = {".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".odp", ".ods",
                 ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                 ".mp3", ".wav", ".mp4", ".zip", ".csv", ".epub"}
ARTIFACT_MAX_BYTES = 50 * 1024 * 1024
ARTIFACT_MAX_FILES = 20


def _copy_branch_artifacts(repo_ctx: dict, workspace: Path, agent_id: str, task_id: str):
    """Mirror artifact-type files added/changed on the task branch into
    workspace/artifacts/ so the existing deliverables plumbing (list, download,
    preview, primary-output chip) sees them. Best-effort — never fails a
    finalize."""
    try:
        rows = wt.changed_files(repo_ctx["worktree"], repo_ctx["base"])
        copied = 0
        for _status, rel in rows:
            if copied >= ARTIFACT_MAX_FILES:
                db.log_activity("warn", agent_id,
                                f"Task {task_id}: artifact copy capped at {ARTIFACT_MAX_FILES} files")
                break
            if Path(rel).suffix.lower() not in ARTIFACT_EXTS:
                continue
            src = Path(repo_ctx["worktree"]) / rel
            if not src.is_file() or src.stat().st_size > ARTIFACT_MAX_BYTES:
                continue
            dest = workspace / "artifacts" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
        if copied:
            db.log_activity("info", agent_id,
                            f"Task {task_id}: captured {copied} artifact file(s) "
                            f"from branch {repo_ctx['branch']} into the workspace")
    except Exception as e:
        db.log_activity("warn", agent_id,
                        f"Task {task_id}: artifact copy failed: {str(e)[:100]}")


def _capture_repo_result(task: dict, workspace: Path, agent_id: str,
                         repo_ctx: dict | None = None):
    """The branch diff IS the deliverable for repo tasks: snapshot anything the
    agent left uncommitted (never lose work), then capture the full diff vs the
    baseline into the workspace for review/UI/judging. Called on EVERY path that
    finalizes a repo task's result — including harvest, or changes.diff goes
    stale at whatever the last live stream saw."""
    repo_ctx = repo_ctx or _repo_context(task)
    if not repo_ctx:
        return
    task_id = task["id"]
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
        _copy_branch_artifacts(repo_ctx, workspace, agent_id, task_id)
    except Exception as e:
        db.log_activity("error", agent_id,
                        f"Task {task_id}: diff capture failed: {str(e)[:100]}")


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
                      resume: bool = False, fallback_model: str | None = None) -> dict:
    """Execute one claimed task as a real Hermes session. Blocking; call from the
    lane's worker process. resume=True = the previous executor died mid-dispatch:
    harvest the orphaned result if it finished, else send a continue-turn into
    the SAME session (context kept); fresh re-dispatch only if the session died.
    fallback_model is internal — set by the QuotaError failover retry so the
    second pass runs on the overload-fallback model (and never falls back again)."""
    task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    agent = db.query_one("SELECT * FROM agents WHERE id=?", (agent_id,))
    if not task or not agent:
        _set_dispatch(dispatch_id, state="failed", ended_at=time.time(),
                      error="task or agent vanished before dispatch")
        return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))
    if task.get("cancel_requested"):
        # Stop arrived between claim and execution (or before a resume) —
        # honor it before spending anything.
        _finalize_cancel(dispatch_id, task_id, agent_id)
        return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))

    run_model = fallback_model or resolve_task_model(task)
    if resume and not fallback_model and task.get("session_id"):
        # A resumed session may run on a DIFFERENT model than the task row says
        # (an overload fallback creates its session on the fallback model but
        # never updates tasks.model). The dispatch that created the session
        # recorded the EFFECTIVE model — resume on (and slot-count) that one.
        prev = db.query_one(
            "SELECT model FROM dispatches WHERE session_id=? AND model IS NOT NULL "
            "ORDER BY started_at DESC LIMIT 1", (task["session_id"],))
        if prev and prev.get("model"):
            run_model = prev["model"]
    workspace = WORKSPACES / task_id
    workspace.mkdir(parents=True, exist_ok=True)
    db.execute("UPDATE agents SET status='busy', current_task=? WHERE id=?",
               (f"{task_id}: dispatching…", agent_id))
    _set_task(task_id, workspace_path=str(workspace))
    on_event = _make_on_event(dispatch_id, task_id, agent_id)

    resume_with_context = False  # the session's transcript actually heard the brief
    try:
        # Free recovery first: the orphaned run may already be complete (R3.3).
        if resume:
            state = orphan_run_state(task)
            if state == "finished":
                harvested = _try_harvest(task)
                if harvested:
                    _set_task(task_id, dispatch_state="finalizing")
                    if task.get("repo_path"):
                        _capture_repo_result(task, workspace, agent_id)
                    _finalize_result(dispatch_id, task_id, agent_id, workspace,
                                     harvested["content"], harvested["usage"], None, harvested=True)
                    return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))
                # unharvestable final reply (failure string) — the transcript
                # still holds the full brief, so a continue-turn is safe
                resume_with_context = True
            elif state == "active":
                # The orphaned run is STILL EXECUTING on the Hermes side — a
                # continue-turn now would open a second concurrent run on the
                # same session. Refresh the heartbeat and wait; the lane's
                # stale check re-enters here until it finishes or goes quiet.
                _set_dispatch(dispatch_id, session_id=task.get("session_id"),
                              state="streaming", heartbeat_at=time.time(), model=run_model)
                _set_task(task_id, dispatch_state="streaming")
                db.log_activity("info", agent_id,
                                f"Task {task_id}: orphaned run still active — waiting, not resuming")
                return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))
            elif state == "dead" and task.get("session_id"):
                # 'dead' covers BOTH a quiet transcript and an EMPTY one (the
                # previous worker died before its first turn went out). A bare
                # "continue" into a session that never heard the brief strands
                # the agent with half a task — only continue on real context.
                try:
                    resume_with_context = bool(get_messages(task["session_id"]))
                except Exception:
                    resume_with_context = False
            if task.get("session_id") and get_session(task["session_id"]) is None:
                # Session unusable → fall back to a fresh re-dispatch (R3.4).
                db.log_activity("warn", agent_id,
                                f"Task {task_id}: session {task['session_id']} gone — fresh re-dispatch")
                _set_task(task_id, session_id=None)
                task["session_id"] = None
                resume_with_context = False

        # Test-only fault injection for the quota gate (SPEC R7.3) — off by default.
        if db.get_setting("dispatch.force_429") == "1":
            raise QuotaError("simulated 429 (dispatch.force_429)")

        blocked = check_budgets(task)
        # [17]: query the cut count ONCE (guard + log share it) — and only on
        # the budget-blocked resume path, exactly as before.
        cuts = _turn_cut_count(task_id) if blocked == "blocked_budget" and resume else 0
        if 0 < cuts <= 3:
            # B2: this resume finishes work the budget already paid for — parking
            # it one step from the finish strands the whole spend. Grant the same
            # one-slice headroom a judge retry gets (_retry_task), bounded to 3
            # cut-turn extensions so a looping run can't mint budget forever.
            slice_ = int(task.get("budget_tokens")
                         or int(sreg.conf("dispatch.default_task_budget") or 5000000))
            new_budget = int(task.get("tokens_used") or 0) + slice_
            _set_task(task_id, budget_tokens=new_budget)
            task["budget_tokens"] = new_budget
            db.log_activity("info", agent_id,
                            f"Task {task_id}: budget extended to {new_budget:,} to finish "
                            f"a cut-turn run (cut #{cuts})",
                            user_id=task.get("user_id"))
            blocked = check_budgets(task)  # daily cap / quota backoff still bind
        if blocked:
            _set_task(task_id, dispatch_state=blocked,
                      dispatch_error=f"{blocked} at dispatch time")
            _set_dispatch(dispatch_id, state=blocked, ended_at=time.time(), error=blocked)
            db.log_activity("warn", agent_id, f"Task {task_id} not dispatched: {blocked}",
                            user_id=task.get("user_id"))
            return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))

        # Item 3: the lane's stm scratchpad — what it is working on right now.
        try:
            if db.get_setting("agentmem.enabled", "1") == "1":
                stm_ttl = float(db.get_setting("agentmem.stm_ttl_hours", "48") or 48)
                db.execute("DELETE FROM memory WHERE agent_id=? AND scope='stm' "
                           "AND kind='inflight' AND content LIKE ?",
                           (agent_id, f"%{task_id}%"))
                db.execute(
                    "INSERT INTO memory (id, agent_id, scope, kind, content, source, "
                    "created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
                    (f"mem-{uuid.uuid4().hex[:10]}", agent_id, "stm", "inflight",
                     f"working on {(task.get('title') or '?')[:120]} (task {task_id})",
                     "auto", time.time(), time.time() + stm_ttl * 3600))
        except Exception:
            pass

        session_id = task.get("session_id")
        if not session_id:
            _set_task(task_id, dispatch_state="dispatching")
            session_id = create_session(f"nexus:{task_id}", model=run_model)
            _set_task(task_id, session_id=session_id)
            task["session_id"] = session_id
        # M3 + Block 1: session memory scoping — client tag isolates client
        # facts, user tag isolates the owner's memories from other users.
        publish_session_scope(session_id, client=task.get("client"),
                              user=task.get("user_id"))
        # Settings v2: the owner's personal API key (if configured) rides the
        # same bridge mechanism — re-published on every (re)dispatch, removed
        # at finalize.
        publish_session_key(session_id, task.get("user_id"), run_model)
        # Mode-coherence (2026-07-12b): per-task reasoning effort — the mode ×
        # task-type × tier choice rides the same bridge (zai session-effort mod).
        publish_session_effort(session_id, task, run_model)
        _set_dispatch(dispatch_id, session_id=session_id, state="streaming",
                      heartbeat_at=time.time(), model=run_model)
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
        framing = build_framing(task, workspace, repo_ctx, agent_id=agent_id)
        if resume and resume_with_context:
            input_text = (f"You were interrupted mid-task. Continue task {task_id} now and "
                          "finish it. The original instructions still apply: write the final "
                          f"deliverable to {workspace}/deliverable.md and reply with the "
                          "complete final deliverable text.")
        else:
            # Fresh dispatch, OR a "resume" whose session never heard the brief
            # (worker died before/at the first turn) — send the FULL brief.
            input_text = f"{task['title']}\n\n{task.get('description') or ''}".strip()
        if db.get_setting("dispatch.stub_stream") == "1":
            # Gate-only knob (verify_stop_e2e): a synthetic keepalive loop —
            # the cancel poll in on_event fires exactly as on a real stream.
            deadline = time.time() + 120
            while time.time() < deadline:
                on_event("_line", None)
                time.sleep(1)
            result = {"content": "stubbed deliverable (dispatch.stub_stream)",
                      "usage": {}, "error": None, "partial": False}
        else:
            result = stream_turn(session_id, input_text, system_message=framing,
                                 on_event=on_event,
                                 max_seconds=_type_setting(
                                     "dispatch.turn_seconds", task,
                                     int(db.get_setting("dispatch.max_turn_seconds",
                                                        str(DEFAULT_MAX_TURN_SECONDS)))),
                                 stall_seconds=int(db.get_setting(
                                     "dispatch.max_turn_stall_seconds",
                                     str(DEFAULT_TURN_STALL_SECONDS))))

        if is_turn_cut(result.get("error")):
            # The turn outlived its guard but the RUN is still alive upstream
            # (a client disconnect never kills it) — failing here strands work
            # the run will finish on its own. Record the cut on the dispatch
            # row, keep it live, and return: the lane's stale-heartbeat check
            # re-enters via resume, where orphan_run_state waits while it's
            # active, harvests it for free when finished, or continue-turns a
            # quiet one. No snapshot/diff here either — the agent is still
            # writing; committing under it captured half-done work.
            _set_dispatch(dispatch_id, state="streaming", heartbeat_at=time.time(),
                          error=result["error"])
            _set_task(task_id, dispatch_state="streaming")
            db.log_activity("warn", agent_id,
                            f"Task {task_id}: turn cut ({result['error'][:80]}) — run "
                            "continues orphaned; lane will wait & harvest",
                            user_id=task.get("user_id"))
            return db.query_one("SELECT * FROM dispatches WHERE id=?", (dispatch_id,))

        _set_task(task_id, dispatch_state="finalizing")
        content = result.get("content") or ""
        if repo_ctx:
            _capture_repo_result(task, workspace, agent_id, repo_ctx)
        # Hermes surfaces upstream provider failures (e.g. Z.ai 429 after retries)
        # as assistant TEXT with no error event — a partial flag and/or the
        # "API call failed" wrapper string are the reliable signals.
        err_text = result.get("error")
        if not err_text and (result.get("partial") or content.startswith(_FAILURE_PREFIXES)):
            err_text = (content or "run ended partial/interrupted")[:300]
        _finalize_result(dispatch_id, task_id, agent_id, workspace,
                         content, result.get("usage") or {}, err_text)

    except QuotaError as e:
        # Peak-hours failover: the task's model is being load-shed upstream —
        # retry ONCE on the configured fallback model (fresh session, its own
        # concurrency pool) instead of blocking. Only a second strike (the
        # fallback is overloaded too) declares the storm and starts the backoff.
        fb = None if fallback_model else fallback_model_for(run_model)
        if fb:
            old_sid = task.get("session_id")
            if old_sid:
                remove_session_key(old_sid)  # the retry re-publishes for its session
            _set_task(task_id, session_id=None)
            db.log_activity("warn", agent_id,
                            f"Task {task_id}: {run_model or DEFAULT_MODEL} overloaded "
                            f"({str(e)[:80]}) — falling back to {fb}",
                            user_id=_task_user(task_id))
            return run_task_dispatch(dispatch_id, task_id, agent_id,
                                     resume=False, fallback_model=fb)
        backoff = note_quota_hit()
        _set_task(task_id, dispatch_state="blocked_quota", dispatch_error=str(e)[:300])
        _set_dispatch(dispatch_id, state="blocked_quota", ended_at=time.time(), error=str(e)[:300])
        db.log_activity("warn", agent_id, f"Task {task_id} blocked by quota — backoff {backoff}s",
                        user_id=_task_user(task_id))
    except DispatchCancelled:
        # Operator stop mid-stream: snapshot whatever the agent already wrote
        # on the branch (repo tasks) so no work is lost, then park in Backlog.
        if task.get("repo_path"):
            _capture_repo_result(task, workspace, agent_id)
        _finalize_cancel(dispatch_id, task_id, agent_id)
    except Exception as e:
        _set_task(task_id, dispatch_state="failed", dispatch_error=str(e)[:300])
        _set_dispatch(dispatch_id, state="failed", ended_at=time.time(), error=str(e)[:300])
        db.execute("UPDATE agents SET tasks_failed=tasks_failed+1 WHERE id=?", (agent_id,))
        db.log_activity("error", agent_id,
                        f"Task {task_id} dispatch crashed [cause={classify_failure(e)}] "
                        f"({type(e).__name__}): {str(e)[:120]}",
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
