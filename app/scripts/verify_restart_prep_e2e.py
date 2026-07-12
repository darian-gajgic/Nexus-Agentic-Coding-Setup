"""NEXUS verify gate — restart preparation (clean PC reboot drain), end to end.

Recreates the 2026-07-11 scratch test as a committed gate and adds the D3
drain-gap regressions (bugfix campaign 2026-07-12, findings [0][1][2]):
  1  admin-only + prepare/double-prepare/cancel/grace
  2  concurrent prepares keep the ORIGINAL prev_dispatch_enabled (D3c lock)
  3  busy counts critic_verdict='escalating' (D3b) — seeded row
  4  drain-harvest (D3a): with dispatch OFF (prep armed), a stale streaming
     dispatch whose upstream run already FINISHED is harvested to completed by
     the lane, while a queued task does NOT execute
  5  restore-across-restart: systemctl restart nexus → dispatch.enabled
     restored, marker cleared, seeded 'escalating' healed to 'error' (D3b)

Costs one tiny GLM turn (the finished-orphan fixture) and restarts the nexus
service ONCE (step 5) — run it when that's acceptable.

Run:  .venv/bin/python scripts/verify_restart_prep_e2e.py
"""
import json
import pathlib
import shutil
import subprocess
import sys
import threading
import time

import requests
import urllib3

urllib3.disable_warnings()
APP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "scripts"))
import os  # noqa: E402

from _gate_common import load_env  # noqa: E402
load_env()  # hermes_dispatch.create_session needs API_SERVER_KEY

import auth  # noqa: E402
import database as db  # noqa: E402
from _gate_auth import owner_cookie  # noqa: E402

BASE = "https://127.0.0.1:8777"
CK = owner_cookie()
P = F = 0
made_tasks: list = []
made_agents: list = []


def ok(name, cond, extra=""):
    global P, F
    if cond:
        P += 1
        print(f"  PASS  {name}", flush=True)
    else:
        F += 1
        print(f"  FAIL  {name}  {extra}", flush=True)


def api(method, path, **kw):
    return requests.request(method, BASE + path, cookies=CK, verify=False,
                            timeout=kw.pop("timeout", 20), **kw)


def _health_ok():
    try:
        return api("GET", "/api/health").json().get("status") == "ok"
    except Exception:
        return False


def wait_for(fn, timeout=60, step=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def task_row(tid):
    return db.query_one("SELECT * FROM tasks WHERE id=?", (tid,))


prev_dispatch = db.get_setting("dispatch.enabled")
print(f"pre-test dispatch.enabled raw = {prev_dispatch!r}", flush=True)

try:
    print("=== 0. Preflight ===", flush=True)
    ok("nexus server up", _health_ok())
    # a stray marker from a crashed run would poison every check below
    if api("GET", "/api/system/restart-prep").json().get("active"):
        api("POST", "/api/system/prepare-restart/cancel")
        prev_dispatch = db.get_setting("dispatch.enabled")
    ok("no restart-prep marker at start",
       api("GET", "/api/system/restart-prep").json().get("active") is False)

    print("=== 1. Admin-only ===", flush=True)
    r = requests.get(BASE + "/api/system/restart-prep", verify=False, timeout=10)
    ok("anonymous GET denied", r.status_code in (401, 403), str(r.status_code))
    r = requests.post(BASE + "/api/system/prepare-restart", verify=False, timeout=10)
    ok("anonymous POST denied", r.status_code in (401, 403), str(r.status_code))

    print("=== 2. Concurrent prepares (D3c) ===", flush=True)
    results: list = []

    def _prep_once():
        try:
            results.append(api("POST", "/api/system/prepare-restart", timeout=30).json())
        except Exception as e:  # noqa: BLE001
            results.append({"error": str(e)})

    threads = [threading.Thread(target=_prep_once) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    marker = json.loads(db.get_setting("system.restart_prep") or "{}")
    ok("concurrent prepares kept the ORIGINAL prev_dispatch_enabled",
       marker.get("prev_dispatch_enabled") == prev_dispatch,
       f"marker={marker!r} want prev={prev_dispatch!r}")
    ok("dispatch paused", db.get_setting("dispatch.enabled") == "0")
    st = api("GET", "/api/system/restart-prep").json()
    prepared_at = st.get("prepared_at")
    ok("prep active", st.get("active") is True, str(st)[:200])

    print("=== 3. Double prepare + grace ===", flush=True)
    st = api("POST", "/api/system/prepare-restart").json()
    ok("double prepare flagged", st.get("already_prepared") is True, str(st)[:200])
    ok("double prepare keeps prepared_at", st.get("prepared_at") == prepared_at)
    ok("double prepare keeps prev",
       st.get("prev_dispatch_enabled") == prev_dispatch, str(st)[:200])
    busy0 = (st.get("busy") or {}).get("total")
    if busy0 == 0:
        st2 = wait_for(lambda: (lambda s: s if s.get("safe") else None)(
            api("GET", "/api/system/restart-prep").json()), timeout=20)
        ok("safe after grace (no in-flight)", bool(st2))
    else:
        print(f"  SKIP  safe-after-grace (busy.total={busy0})", flush=True)

    print("=== 4. Busy counts 'escalating' (D3b) ===", flush=True)
    now = time.time()
    esc_tid = f"task-rpesc{int(now) % 1000000}"
    made_tasks.append(esc_tid)
    db.execute("INSERT INTO tasks (id, title, status, created_at, updated_at, "
               "user_id, critic_verdict) VALUES (?,?,?,?,?,?,?)",
               (esc_tid, "restart-prep gate escalating probe", "review", now, now,
                auth.DEFAULT_USER_ID, "escalating"))
    st = api("GET", "/api/system/restart-prep").json()
    ok("busy.critics counts an in-flight escalation",
       (st.get("busy") or {}).get("critics", 0) >= 1, str(st.get("busy")))
    ok("not safe while escalating", st.get("safe") is False)
    db.execute("UPDATE tasks SET critic_verdict=NULL WHERE id=?", (esc_tid,))

    print("=== 5. Drain-harvest (D3a): finished orphan completes, queued waits ===",
          flush=True)
    lane = api("POST", "/api/agents",
               json={"name": "E2E-RestartPrep", "auto_claim": False}).json()
    made_agents.append(lane["id"])
    ok("lane spawned", bool(lane.get("pid")), str(lane)[:120])
    import hermes_dispatch as hd
    sess = hd.create_session(f"nexus-rp-gate-{int(time.time())}")
    turn = hd.stream_turn(sess, "Reply with exactly: OK", max_seconds=120)
    ok("fixture run finished upstream",
       not turn.get("error") and bool(turn.get("content")), str(turn)[:150])
    now = time.time()
    h_tid = f"task-rphrv{int(now) % 1000000}"
    made_tasks.append(h_tid)
    ws = APP / "workspaces" / h_tid
    ws.mkdir(parents=True, exist_ok=True)
    db.execute("INSERT INTO tasks (id, title, description, status, created_at, "
               "updated_at, user_id, claimed_by, claimed_at, dispatch_state, "
               "session_id, workspace_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (h_tid, "restart-prep gate harvest probe", "Reply OK", "in_progress",
                now, now, auth.DEFAULT_USER_ID, lane["id"], now, "streaming",
                sess, str(ws)))
    db.execute("INSERT INTO dispatches (id, task_id, agent_id, session_id, state, "
               "started_at, heartbeat_at) VALUES (?,?,?,?,?,?,?)",
               (f"disp-rpgate{int(now)}", h_tid, lane["id"], sess, "streaming",
                now - 300, now - 200))  # stale > worker.STALE_DISPATCH_S=90
    q_tid = f"task-rpq{int(now) % 1000000}"
    made_tasks.append(q_tid)
    db.execute("INSERT INTO tasks (id, title, description, status, created_at, "
               "updated_at, user_id, claimed_by, claimed_at, dispatch_state) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)",
               (q_tid, "restart-prep gate queued probe", "Reply OK", "in_progress",
                now, now, auth.DEFAULT_USER_ID, lane["id"], now, "queued"))
    fin = wait_for(lambda: task_row(h_tid).get("dispatch_state") == "completed",
                   timeout=90, step=2)
    ok("finished orphan harvested to completed during drain (dispatch off)",
       bool(fin), str(task_row(h_tid).get("dispatch_state")))
    ok("harvested deliverable written",
       (ws / "deliverable.md").is_file()
       and len((ws / "deliverable.md").read_text().strip()) > 0)
    time.sleep(10)  # > several worker ticks
    ok("queued task did NOT execute during drain",
       task_row(q_tid).get("dispatch_state") == "queued",
       str(task_row(q_tid).get("dispatch_state")))

    print("=== 6. Cancel restores ===", flush=True)
    st = api("POST", "/api/system/prepare-restart/cancel").json()
    ok("cancel -> cancelled", st.get("cancelled") is True, str(st)[:150])
    raw_now = db.get_setting("dispatch.enabled")
    ok("cancel restored dispatch.enabled", raw_now == prev_dispatch,
       f"now={raw_now!r} want={prev_dispatch!r}")
    ok("cancel cleared marker", db.get_setting("system.restart_prep") is None)
    st = api("POST", "/api/system/prepare-restart/cancel").json()
    ok("second cancel -> cancelled:false", st.get("cancelled") is False)

    print("=== 7. Restore + heal across a REAL service restart ===", flush=True)
    api("POST", "/api/system/prepare-restart")
    db.execute("UPDATE tasks SET critic_verdict='escalating' WHERE id=?", (esc_tid,))
    # [R2] fixture: capture the fleet's circuit-breaker counters BEFORE the
    # clean restart — the post-boot respawn of the SIGTERM'd lanes must NOT
    # increment them (watchdog boot grace), or every restart marches the
    # whole fleet toward max_restarts retirement.
    pre_counts = {a["id"]: int(a.get("restart_count") or 0)
                  for a in db.query_all("SELECT id, restart_count FROM agents "
                                        "WHERE status IN ('running','busy')")}
    t_restart = time.time()
    subprocess.run(["systemctl", "--user", "restart", "nexus"], check=True, timeout=60)
    ok("service back up", bool(wait_for(_health_ok, timeout=60, step=2)))
    ok("startup restored dispatch.enabled",
       db.get_setting("dispatch.enabled") == prev_dispatch,
       f"now={db.get_setting('dispatch.enabled')!r} want={prev_dispatch!r}")
    ok("startup cleared the marker", db.get_setting("system.restart_prep") is None)
    row = task_row(esc_tid)
    ok("boot healed 'escalating' -> 'error' (D3b)",
       row.get("critic_verdict") == "error"
       and "escalation orphaned by restart" in (row.get("critic_output") or ""),
       str({k: row.get(k) for k in ("critic_verdict", "critic_output")})[:200])
    if pre_counts:
        ph = ",".join("?" * len(pre_counts))

        def _respawned():
            rows = db.query_all(
                f"SELECT id, started_at FROM agents WHERE id IN ({ph})",
                tuple(pre_counts))
            return len(rows) == len(pre_counts) and \
                all((r.get("started_at") or 0) > t_restart for r in rows)
        ok("[R2] lanes respawned after the boot", bool(wait_for(_respawned, timeout=90, step=3)))
        post_counts = {a["id"]: int(a.get("restart_count") or 0)
                       for a in db.query_all(
                           f"SELECT id, restart_count FROM agents WHERE id IN ({ph})",
                           tuple(pre_counts))}
        ok("[R2] boot respawn did NOT increment the circuit-breaker counters",
           post_counts == pre_counts, f"pre={pre_counts} post={post_counts}")
    else:
        ok("[R2] no running lanes to check (skipped — empty fleet)", True)
finally:
    for tid in made_tasks:
        db.execute("DELETE FROM dispatches WHERE task_id=?", (tid,))
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        shutil.rmtree(APP / "workspaces" / tid, ignore_errors=True)
    for aid in made_agents:
        try:
            api("POST", f"/api/agents/{aid}/retire")
            api("DELETE", f"/api/agents/{aid}")
        except Exception:
            pass
    # never leave the drain armed or dispatch paused
    try:
        if api("GET", "/api/system/restart-prep").json().get("active"):
            api("POST", "/api/system/prepare-restart/cancel")
    except Exception:
        pass

print(f"\n{'ALL PASSED' if F == 0 else 'FAILURES'}: {P} passed, {F} failed")
sys.exit(1 if F else 0)
