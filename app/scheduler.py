"""NEXUS Agent OS — Cron Scheduler.

Cron parser supporting: * , */N , single value , comma list , ranges a-b and
a-b/N , across the five standard fields (minute hour dom month dow; dow accepts
7 as Sunday). Unsupported syntax raises ValueError at parse time so a job that
would never fire is rejected at creation instead of silently sleeping forever.
A scheduler thread fires jobs whose next_run has passed.
"""
import sys
import json
import time
import uuid
import threading
import datetime as dt

import auth
import database as db


def _parse_field(expr: str, lo: int, hi: int) -> set:
    """Parse one cron field into the set of ints it matches.
    Raises ValueError on syntax it does not understand — a silently-empty
    field set would make the job unmatchable and next_run() scan a year."""
    out: set = set()
    for part in expr.split(","):
        part = part.strip()
        step = 1
        if "/" in part and not part.startswith("*/"):
            part, _, step_s = part.partition("/")
            step = int(step_s)
        if part == "*":
            out.update(range(lo, hi + 1, step))
        elif part.startswith("*/"):
            out.update(range(lo, hi + 1, int(part[2:])))
        elif "-" in part:
            a_s, _, b_s = part.partition("-")
            a, b = int(a_s), int(b_s)
            if a > b or a < lo or b > hi + (1 if hi == 6 else 0):
                raise ValueError(f"range '{part}' outside {lo}-{hi}")
            out.update(v for v in range(a, b + 1, step))
        elif part.isdigit():
            v = int(part)
            if not (lo <= v <= hi + (1 if hi == 6 else 0)):
                raise ValueError(f"value '{part}' outside {lo}-{hi}")
            out.add(v)
        else:
            raise ValueError(f"unsupported cron syntax: '{part}'")
    if hi == 6:  # dow field: accept 7 as Sunday (both conventions exist)
        if 7 in out:
            out.discard(7)
            out.add(0)
    if not out:
        raise ValueError(f"cron field '{expr}' matches nothing")
    return out


def parse_cron(cron_expr: str) -> tuple:
    """Parse all five fields; raises ValueError on anything unmatchable."""
    parts = (cron_expr or "").split()
    if len(parts) != 5:
        raise ValueError("cron expression needs exactly 5 fields")
    m, h, dom, mon, dow = parts
    return (_parse_field(m, 0, 59), _parse_field(h, 0, 23),
            _parse_field(dom, 1, 31), _parse_field(mon, 1, 12),
            _parse_field(dow, 0, 6))


def _cron_matches(cron_expr: str, t: dt.datetime) -> bool:
    try:
        ms, hs, doms, mons, dows = parse_cron(cron_expr)
    except ValueError:
        return False
    # Python weekday: Monday=0..Sunday=6 -> cron Sunday=0
    cron_dow = (t.weekday() + 1) % 7
    return (
        t.minute in ms
        and t.hour in hs
        and t.day in doms
        and t.month in mons
        and cron_dow in dows
    )


def next_run(cron_expr: str, after: float | None = None) -> float:
    """Compute the next unix ts the expression matches, at minute granularity."""
    try:
        parse_cron(cron_expr)
    except ValueError:
        return time.time() + 86400  # unmatchable: don't scan a year of minutes
    base = dt.datetime.fromtimestamp(after if after else time.time())
    base = base.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    for _ in range(60 * 24 * 366):  # cap at 1 year
        if _cron_matches(cron_expr, base):
            return base.timestamp()
        base += dt.timedelta(minutes=1)
    return time.time() + 86400  # fallback: tomorrow


def _trigger(job: dict):
    """Fire a scheduled job: create a REAL task on the board so the normal
    claim/dispatch flow executes it. (Before, firing only wrote a cosmetic
    agent label + log line — run_count grew but no work ever ran.) Jobs are
    admin-created and global, so the task belongs to the owner; status 'todo'
    is what worker lanes auto-claim, and agent_id pins the assignee."""
    try:
        tid = f"task-{uuid.uuid4().hex[:8]}"
        now = time.time()
        # B4: apply the job's task template (Super Result / deliverable type /
        # autopilot preset / high-stakes / domain) so recurring high-value jobs
        # get the quality machinery automatically.
        try:
            tmpl = json.loads(job.get("task_template") or "{}") or {}
        except Exception:
            tmpl = {}
        dtype = tmpl.get("deliverable_type")
        db.execute(
            "INSERT INTO tasks (id, title, description, status, priority, "
            "assignee_id, created_at, updated_at, tags, position, user_id, "
            "super_result, deliverable_type, high_stakes, domain, autopilot, spend_profile) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, f"[scheduled] {job['name']}", job["action"], "todo", 2,
             job.get("agent_id") or None, now, now, json.dumps(["scheduled"]), 0,
             auth.DEFAULT_USER_ID,
             1 if tmpl.get("super_result") else 0, dtype if dtype else None,
             1 if tmpl.get("high_stakes") else 0, tmpl.get("domain"),
             tmpl.get("autopilot"), tmpl.get("spend_profile")))
        if tmpl.get("super_result"):
            # give the recurring task its Super Result loop, exactly like the API path
            try:
                import server as _srv
                _srv._sync_super_result_loop("task", db.query_one("SELECT * FROM tasks WHERE id=?", (tid,)))
            except Exception as e:
                db.log_activity("warn", "scheduler", f"SR loop sync failed for {tid}: {str(e)[:80]}")
        if job.get("agent_id"):
            db.execute("UPDATE agents SET current_task = ? WHERE id = ?",
                       (f"[scheduled] {job['name']}: {job['action']}", job["agent_id"]))
        db.log_activity("info", "scheduler",
                        f"Job '{job['name']}' fired: task {tid} created — {job['action']}",
                        user_id=auth.DEFAULT_USER_ID)
        status = "ok"
    except Exception as e:
        db.log_activity("error", "scheduler", f"Job '{job['name']}' failed: {e}")
        status = f"error: {e}"
    now = time.time()
    nr = next_run(job["cron_expr"], now)
    db.execute(
        "UPDATE scheduled_jobs SET last_run = ?, next_run = ?, run_count = run_count + 1, last_status = ? WHERE id = ?",
        (now, nr, status, job["id"]),
    )


def scheduler_loop(stop_event: threading.Event):
    """Background thread: fire due jobs every ~15s."""
    while not stop_event.is_set():
        try:
            now = time.time()
            due = db.query_all(
                "SELECT * FROM scheduled_jobs WHERE enabled = 1 AND next_run <= ?",
                (now,),
            )
            for job in due:
                _trigger(job)
        except Exception as e:
            print(f"[scheduler] error: {e}", file=sys.stderr)
        stop_event.wait(15)
