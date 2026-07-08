"""NEXUS Agent OS — Worker process (real dispatch lane).

Each agent row is an executor lane; this process is its engine. It claims ONE
kanban task at a time (atomic CAS shared with the HTTP endpoint) and executes
it as a REAL Hermes API session via hermes_dispatch — real specialists, real
tokens, real deliverable files. The v1 simulation is gone.

Work priority each tick:
  1. my interrupted dispatch (previous executor died) → resume/harvest (R3.3)
  2. my queued tasks (operator hit "dispatch" in the UI/API)
  3. my blocked tasks whose budget/quota block has cleared
  4. claimable 'todo' work (assigned to me, or unassigned if auto_claim is on)

The lane idles when settings key dispatch.enabled != 1. It exits cleanly when
its agent row is retired, stopped, or deleted — zombie prevention (R3.1).
"""
import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _load_hermes_env():
    """Same loader as main.py — the worker needs API_SERVER_KEY for Hermes."""
    for env_path in [os.path.expanduser("~/.hermes/.env"), ".env"]:
        if not os.path.exists(env_path):
            continue
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_hermes_env()

import database as db
import hermes_dispatch as hd

POLL_S = 2.0
STALE_DISPATCH_S = 90.0  # dispatch heartbeat older than this = executor is dead


def _agent_cfg(agent: dict) -> dict:
    try:
        cfg = json.loads(agent.get("config") or "{}")
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


_slot_wait_logged: dict = {}  # task_id -> last log ts (avoid 2s-tick log spam)


def _slot_ok(task: dict, agent_id: str) -> bool:
    """Per-model concurrency gate: a task without a free GLM slot WAITS."""
    run_model = hd.resolve_task_model(task)  # Settings v2: owner default counts too
    if hd.slot_available(run_model):
        return True
    now = time.time()
    if now - _slot_wait_logged.get(task["id"], 0) > 60:
        _slot_wait_logged[task["id"]] = now
        db.log_activity("info", agent_id,
                        f"Task {task['id']} waiting for a free {run_model or hd.DEFAULT_MODEL} "
                        f"slot (in flight: {hd.slots_in_use()})", user_id=task.get("user_id"))
    return False


def _find_work(agent_id: str, auto_claim: bool, dispatch_on: bool):
    """Return (task, mode) for the next thing this lane should do, else (None, None)."""
    now = time.time()
    mine = db.query_all(
        "SELECT * FROM tasks WHERE claimed_by=? AND status='in_progress' "
        "ORDER BY claimed_at", (agent_id,))
    for t in mine:
        st = t.get("dispatch_state")
        if st in (None, "", "none"):
            # MY claim with no dispatch yet: the previous worker died between
            # claim and start_dispatch (e.g. a server restart killed the lane)
            # — without this branch the task is invisible forever and manual
            # dispatch 409s on the stale ownership.
            if not hd.deps_satisfied(t):
                continue  # inputs not done yet — resurrect only when they are
            if _slot_ok(t, agent_id):
                db.log_activity("warn", agent_id,
                                f"Task {t['id']}: claim had no dispatch (lane died "
                                "mid-claim?) — starting dispatch now",
                                user_id=t.get("user_id"))
                return t, "claimed"
            continue
        if st == "queued":
            if _slot_ok(t, agent_id):
                return t, "queued"
            continue
        if st in ("dispatching", "streaming", "finalizing"):
            d = db.query_one(
                "SELECT * FROM dispatches WHERE task_id=? AND state IN "
                "('queued','dispatching','streaming') ORDER BY started_at DESC LIMIT 1",
                (t["id"],))
            hb = (d or {}).get("heartbeat_at") or (d or {}).get("started_at") or 0
            if now - hb > STALE_DISPATCH_S and _slot_ok(t, agent_id):
                return t, "resume"
        if st in ("blocked_quota", "blocked_budget") and not hd.check_budgets(t) \
                and _slot_ok(t, agent_id):
            return t, "retry"
    if not (auto_claim and dispatch_on):
        return None, None
    # Don't claim new work while the global quota backoff is active.
    if float(db.get_setting("dispatch.quota_backoff_until", "0") or 0) > now:
        return None, None
    cands = db.query_all(
        "SELECT * FROM tasks WHERE status='todo' AND (assignee_id IS NULL "
        "OR assignee_id='' OR assignee_id=?) ORDER BY priority, created_at",
        (agent_id,))
    for t in cands:
        if not hd.deps_satisfied(t):
            continue  # workflow dependency not shipped yet — runs when it is
        if not _slot_ok(t, agent_id):
            continue  # don't even claim without a free slot for its model
        if db.claim_task_cas(t["id"], agent_id):
            db.log_activity("info", agent_id, f"Claimed task '{t['title']}'",
                            user_id=t.get("user_id"))
            return db.query_one("SELECT * FROM tasks WHERE id=?", (t["id"],)), "claimed"
    return None, None


def _execute(task: dict, mode: str, agent_id: str):
    tid = task["id"]
    if mode == "queued":
        d = db.query_one(
            "SELECT * FROM dispatches WHERE task_id=? AND state='queued' "
            "ORDER BY started_at DESC LIMIT 1", (tid,))
        did = d["id"] if d else hd.start_dispatch(tid, agent_id)
        # A manual re-dispatch of a previously-failed task already has a
        # session that heard the original prompt — resume it (harvest or
        # continue-turn) instead of replaying the same instructions into it.
        hd.run_task_dispatch(did, tid, agent_id, resume=bool(task.get("session_id")))
    elif mode == "resume":
        db.execute(
            "UPDATE dispatches SET state='failed', ended_at=?, "
            "error='executor died — resumed by new worker' "
            "WHERE task_id=? AND state IN ('queued','dispatching','streaming')",
            (time.time(), tid))
        db.log_activity("warn", agent_id,
                        f"Task {tid}: previous executor died — resuming session",
                        user_id=task.get("user_id"))
        did = hd.start_dispatch(tid, agent_id)
        hd.run_task_dispatch(did, tid, agent_id, resume=True)
    else:  # "retry" (block cleared) or freshly "claimed"
        did = hd.start_dispatch(tid, agent_id)
        # If a session already exists (blocked MID-stream earlier), resume it —
        # harvest first, else continue-turn. Replaying the original prompt into
        # a session that already heard it would duplicate instructions.
        hd.run_task_dispatch(did, tid, agent_id, resume=bool(task.get("session_id")))


def main():
    agent_id = sys.argv[1]
    while True:
        agent = db.query_one("SELECT * FROM agents WHERE id=?", (agent_id,))
        if not agent or agent.get("status") in ("retired", "stopped"):
            return  # lane ended through its real lifecycle — exit, no zombie
        now = time.time()
        db.execute("UPDATE agents SET last_heartbeat=? WHERE id=?", (now, agent_id))
        if agent.get("status") == "cost_capped":
            # The watchdog capped this agent — PAUSE the lane (don't claim or
            # dispatch) until an operator raises the cap / resets the status.
            time.sleep(POLL_S)
            continue

        dispatch_on = db.get_setting("dispatch.enabled", "0") == "1"
        cfg = _agent_cfg(agent)
        auto_claim = bool(cfg.get("auto_claim", True))
        try:
            task, mode = _find_work(agent_id, auto_claim, dispatch_on)
            if task and dispatch_on:
                _execute(task, mode, agent_id)
        except Exception as e:
            db.log_activity("error", agent_id, f"worker loop error: {str(e)[:150]}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
