"""NEXUS Agent OS — Self-Healing Watchdog.

Background thread that keeps the agent fleet alive:
  - restarts dead agents (PID gone while status=running/busy)
  - detects stuck agents (stale heartbeat) and restarts them
  - enforces per-agent max_tasks recycle
  - enforces per-agent cost caps (max_tokens -> status 'cost_capped')

Mirrors the amux self-healing pattern: the fleet should survive unattended.
"""
import os
import sys
import time
import signal
import threading
import psutil

import database as db
import agent_manager as am

# Defaults (overridable via settings table at runtime)
# stale_threshold_s must exceed the dispatch stream's worst tolerated silence
# (SSE keepalives ~30s, read timeout 120s in hermes_dispatch) — killing a
# healthy mid-stream worker risks a second concurrent turn on the session.
DEFAULTS = {
    "interval_s": 10,
    "stale_threshold_s": 150,
    "restart_on_stuck": True,
    "restart_on_dead": True,
}


def _setting(key: str, cast=None, default=None):
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
    if not row:
        return default
    if cast is None:
        return row["value"]
    try:
        return cast(row["value"])
    except (ValueError, TypeError):
        return default


def get_config() -> dict:
    return {
        "interval_s": _setting("watchdog.interval_s", int, DEFAULTS["interval_s"]),
        "stale_threshold_s": _setting("watchdog.stale_threshold_s", int, DEFAULTS["stale_threshold_s"]),
        "restart_on_stuck": _setting("watchdog.restart_on_stuck", lambda v: v == "1", DEFAULTS["restart_on_stuck"]),
        "restart_on_dead": _setting("watchdog.restart_on_dead", lambda v: v == "1", DEFAULTS["restart_on_dead"]),
    }


def _is_alive(pid, agent_id=None) -> bool:
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        if not (proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE):
            return False
        if agent_id:
            # After a reboot the recorded pid can be recycled by an unrelated
            # process — a bare liveness check would then report a dead lane
            # as alive. The lane's cmdline is `python worker.py <agent_id> …`.
            cmd = " ".join(proc.cmdline())
            if "worker.py" not in cmd or agent_id not in cmd:
                return False
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _agent_cfg(agent: dict) -> dict:
    """Parse the agent config JSON for caps; tolerate missing/bad JSON."""
    import json
    raw = agent.get("config") or "{}"
    try:
        cfg = json.loads(raw) if isinstance(raw, str) else (raw or {})
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def _recent_actions(limit=20) -> list[dict]:
    return db.query_all(
        "SELECT * FROM activity WHERE source = 'watchdog' ORDER BY ts DESC LIMIT ?",
        (limit,),
    )


def _once(cfg: dict) -> list[dict]:
    """Run one watchdog sweep. Returns the list of actions taken this sweep."""
    actions = []
    now = time.time()
    # Include 'crashed' so agents marked dead by the metrics loop get healed.
    agents = db.query_all("SELECT * FROM agents WHERE status IN ('running','busy','crashed')")
    for a in agents:
        pid = a.get("pid")
        alive = _is_alive(pid, a["id"])
        hb_age = (now - a["last_heartbeat"]) if a.get("last_heartbeat") else 9999

        # 1. Cost cap enforcement (highest priority)
        acfg = _agent_cfg(a)
        max_tokens = acfg.get("max_tokens", 0) or 0
        total_tokens = (a.get("tokens_in") or 0) + (a.get("tokens_out") or 0)
        if max_tokens and total_tokens >= max_tokens:
            db.execute("UPDATE agents SET status = 'cost_capped' WHERE id = ?", (a["id"],))
            db.log_activity("warn", "watchdog",
                f"Agent '{a['name']}' cost-capped: {total_tokens} >= {max_tokens} tokens")
            actions.append({"agent": a["id"], "action": "cost_capped", "tokens": total_tokens})
            continue  # do not restart a cost-capped agent

        # 2. Dead agent -> restart
        if not alive and cfg["restart_on_dead"] and pid:
            try:
                am.restart_agent(a["id"])
                db.execute("UPDATE agents SET restart_count = restart_count + 1 WHERE id = ?", (a["id"],))
                db.log_activity("warn", "watchdog",
                    f"Agent '{a['name']}' was dead (pid {pid} gone) — auto-restarted")
                actions.append({"agent": a["id"], "action": "restarted_dead"})
            except Exception as e:
                db.log_activity("error", "watchdog", f"Restart of '{a['name']}' failed: {e}")
                actions.append({"agent": a["id"], "action": "restart_failed", "error": str(e)})
            continue

        # 3. Stuck agent -> mark stuck + maybe restart
        if alive and hb_age > cfg["stale_threshold_s"]:
            if cfg["restart_on_stuck"]:
                try:
                    am.restart_agent(a["id"])
                    db.execute("UPDATE agents SET restart_count = restart_count + 1 WHERE id = ?", (a["id"],))
                    db.log_activity("warn", "watchdog",
                        f"Agent '{a['name']}' stuck (no heartbeat {int(hb_age)}s) — auto-restarted")
                    actions.append({"agent": a["id"], "action": "restarted_stuck", "hb_age": int(hb_age)})
                except Exception as e:
                    db.log_activity("error", "watchdog", f"Stuck-restart of '{a['name']}' failed: {e}")
            else:
                db.execute("UPDATE agents SET status = 'stuck' WHERE id = ?", (a["id"],))
                db.log_activity("warn", "watchdog",
                    f"Agent '{a['name']}' stuck (no heartbeat {int(hb_age)}s)")
                actions.append({"agent": a["id"], "action": "marked_stuck", "hb_age": int(hb_age)})

    # 4. Stranded claims: a task claimed but never dispatched (worker died in
    # the claim→dispatch window, or the claiming agent's row was deleted) is
    # invisible to every lane's _find_work forever. Release stale ones.
    stale_claim_s = _setting("watchdog.stale_claim_s", int, 3600)
    strays = db.query_all(
        "SELECT id, title, claimed_by FROM tasks WHERE status='in_progress' "
        "AND (dispatch_state IS NULL OR dispatch_state IN ('', 'none')) "
        "AND COALESCE(claimed_at, 0) > 0 AND claimed_at < ?",
        (now - stale_claim_s,))
    for t in strays:
        db.execute("UPDATE tasks SET status='todo', claimed_by=NULL, claimed_at=NULL, "
                   "updated_at=? WHERE id=? AND status='in_progress'", (now, t["id"]))
        db.log_activity("warn", "watchdog",
            f"Released task '{t['title']}' — claimed by {t['claimed_by']} "
            f"but never dispatched for >{stale_claim_s}s")
        actions.append({"task": t["id"], "action": "released_stranded_claim"})
    return actions


def watchdog_loop(stop_event: threading.Event):
    """Background thread: run a watchdog sweep every interval_s seconds."""
    # Seed default settings so the config is visible/editable from the UI.
    for k, v in DEFAULTS.items():
        key = f"watchdog.{k}"
        if not db.query_one("SELECT value FROM settings WHERE key = ?", (key,)):
            db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                       (key, "1" if isinstance(v, bool) else str(v)))
    while not stop_event.is_set():
        try:
            cfg = get_config()
            _once(cfg)
        except Exception as e:
            print(f"[watchdog] error: {e}", file=sys.stderr)
            cfg = DEFAULTS
        stop_event.wait(cfg["interval_s"])
