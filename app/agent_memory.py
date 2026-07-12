"""Agent lane memory (item 3, 2026-07-12) — the automatic writers behind the
"Agent memory" tab, which was scaffolded (SuperAGI two-part model) but never
had a producer.

Scope semantics (surfaced verbatim in the UI):
  stm       — scratchpad: what the lane is working on right now (auto, TTL ~48h)
  experience— task log: one deterministic line per finished dispatch (auto,
              TTL ~90d) — written by hermes_dispatch._write_experience
  lts       — rolling summary: the hourly sweep below condenses the task log
              into ONE replace-in-place 'auto-summary' row per lane
  longterm  — operator-taught standing rules (never expire, always injected)

The consolidation is ONE cheap-model call per lane per sweep (throwaway
session, same pattern as the feedback AI-draft); `agentmem.stub=1` short-
circuits it for gates. Everything is best-effort — memory must never break
dispatching."""

import time
import uuid

import database as db
import hermes_dispatch as hd

CONSOLIDATE_PROMPT = (
    "You maintain the long-term memory of ONE worker agent lane in an agent "
    "fleet. INPUT: the previous summary (may be empty) and its recent task-log "
    "lines (newest first). OUTPUT: plain text of at most 120 words, no "
    "markdown, an UPDATED summary covering: the kinds of work it handles well "
    "(domains/specialists), recurring failure causes and their fixes, notable "
    "streaks or regressions, and anything an operator should know before "
    "assigning it work. Merge, don't append — drop stale facts contradicted "
    "by newer entries. Reply with ONLY the summary text.")


def _setting_int(key: str, default: int) -> int:
    try:
        return int(float(db.get_setting(key, str(default)) or default))
    except (TypeError, ValueError):
        return default


def expire_sweep() -> int:
    """Enforce memory.expires_at (nothing else does): drop expired rows."""
    cur = db.execute("DELETE FROM memory WHERE expires_at IS NOT NULL AND expires_at < ?",
                     (time.time(),))
    return cur.rowcount


def _fresh_experiences(agent_id: str, since: float) -> list[dict]:
    return db.query_all(
        "SELECT content, created_at FROM memory WHERE agent_id=? AND "
        "scope='experience' AND created_at > ? ORDER BY created_at DESC LIMIT 40",
        (agent_id, since))


def _current_summary(agent_id: str) -> dict | None:
    return db.query_one(
        "SELECT * FROM memory WHERE agent_id=? AND scope='lts' AND "
        "kind='auto-summary' ORDER BY created_at DESC LIMIT 1", (agent_id,))


def consolidate_agent(agent_id: str, force: bool = False) -> str | None:
    """Condense one lane's fresh experience rows into its rolling summary.
    Returns the new summary text, or None when there was nothing to do."""
    prev = _current_summary(agent_id)
    since = (prev or {}).get("created_at") or 0
    fresh = _fresh_experiences(agent_id, since)
    threshold = 1 if force else _setting_int("agentmem.consolidate_after", 10)
    if len(fresh) < threshold:
        return None
    lines = "\n".join(r["content"] for r in fresh)
    prev_text = (prev or {}).get("content") or "(none)"
    if db.get_setting("agentmem.stub") == "1":
        summary = f"[stub summary] {len(fresh)} task(s) consolidated"
    else:
        model = db.default_task_model(None)
        easy = db.resolve_assignment(None, "easy")
        if easy and easy.get("model_id"):
            model = easy["model_id"]
        sid = hd.create_session("nexus:agentmem", model=model)
        try:
            res = hd.stream_turn(
                sid, f"PREVIOUS SUMMARY:\n{prev_text}\n\nRECENT TASK LOG:\n{lines}",
                system_message=CONSOLIDATE_PROMPT, max_seconds=120)
        finally:
            hd.delete_session(sid)
        summary = " ".join((res.get("content") or "").split()).strip()
        if res.get("error") or not summary:
            return None
    db.execute("DELETE FROM memory WHERE agent_id=? AND scope='lts' AND kind='auto-summary'",
               (agent_id,))
    db.execute(
        "INSERT INTO memory (id, agent_id, scope, kind, content, source, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (f"mem-{uuid.uuid4().hex[:10]}", agent_id, "lts", "auto-summary",
         summary[:1200], "auto", time.time()))
    return summary


def consolidate_sweep() -> int:
    """Hourly (scheduler): expiry first, then consolidate every non-retired
    lane that accumulated enough fresh experience. Skips entirely while the
    quota backoff is active (the summary call would just add pressure)."""
    if db.get_setting("agentmem.enabled", "1") != "1":
        return 0
    expire_sweep()
    if float(db.get_setting("dispatch.quota_backoff_until", "0") or 0) > time.time():
        return 0
    done = 0
    for a in db.query_all("SELECT id FROM agents WHERE status != 'retired'"):
        try:
            if consolidate_agent(a["id"]):
                done += 1
        except Exception:
            continue  # one lane's failure never blocks the others
    return done
