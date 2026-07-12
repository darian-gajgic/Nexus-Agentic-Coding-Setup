#!/usr/bin/env python3
"""Item 5/11/2b/2c/1 runtime gate — stop mechanism, bulk start/stop, delete
cascades, branch-artifact surfacing.

Run:  .venv/bin/python scripts/verify_stop_e2e.py

Self-cleaning: probe users, tasks, workflows, scratch repo, settings are all
removed/restored. The live-stream stop test uses the gate-only
`dispatch.stub_stream` knob (synthetic keepalive loop — zero LLM tokens; a
throwaway Hermes session is created and deleted).
"""
import json
import os
import secrets as _secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# hermes_dispatch.create_session needs API_SERVER_KEY — same loader as worker.py
for _env_path in [os.path.expanduser("~/.hermes/.env"), ".env"]:
    if os.path.exists(_env_path):
        for _line in open(_env_path):
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

import database as db          # noqa: E402
import auth                    # noqa: E402
import hermes_dispatch as hd   # noqa: E402
import worktree as wt          # noqa: E402

BASE = "https://127.0.0.1:8777"
PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def mk_task(uid, **kw):
    tid = f"task-{uuid.uuid4().hex[:8]}"
    now = time.time()
    fields = {"id": tid, "title": kw.pop("title", f"probe {tid}"), "description": "probe",
              "status": kw.pop("status", "backlog"), "priority": 2, "created_at": now,
              "updated_at": now, "user_id": uid, "dispatch_state": kw.pop("dispatch_state", "none")}
    fields.update(kw)
    cols = ", ".join(fields)
    db.execute(f"INSERT INTO tasks ({cols}) VALUES ({','.join('?' * len(fields))})",
               tuple(fields.values()))
    return tid


ADMIN_PW = "probe-" + _secrets.token_urlsafe(9)
admin_u, err = auth.create_user("probe-stop-admin", "Probe Stop Admin", ADMIN_PW, role="admin")
assert admin_u, err
UID = admin_u["id"]
agent_id = f"agent-{uuid.uuid4().hex[:8]}"
db.execute("INSERT INTO agents (id, name, status, created_at) VALUES (?,?,?,?)",
           (agent_id, "probe-stop-lane", "running", time.time()))
scratch_repo = os.path.expanduser(f"~/Projects/probe-stopgate-{uuid.uuid4().hex[:6]}")
stub_prev = db.get_setting("dispatch.stub_stream")
created_tasks, created_wfs = [], []

try:
    c = httpx.Client(base_url=BASE, verify=False, timeout=30)
    r = c.post("/api/auth/login", json={"username": "probe-stop-admin", "password": ADMIN_PW})
    ok("probe admin login", r.status_code == 200, r.text[:120])

    # ── 1. stop a queued (not yet streaming) task → immediate ──
    t1 = mk_task(UID, status="in_progress", dispatch_state="queued", claimed_by=agent_id)
    created_tasks.append(t1)
    db.execute("INSERT INTO dispatches (id, task_id, agent_id, started_at, state) VALUES (?,?,?,?,?)",
               (f"disp-{uuid.uuid4().hex[:8]}", t1, agent_id, time.time(), "queued"))
    r = c.post(f"/api/tasks/{t1}/stop")
    ok("queued stop → immediate", r.status_code == 200 and r.json().get("stopped") == "immediate", r.text[:150])
    row = db.query_one("SELECT * FROM tasks WHERE id=?", (t1,))
    ok("queued stop: backlog + cancelled + unclaimed",
       row["status"] == "backlog" and row["dispatch_state"] == "cancelled" and not row["claimed_by"])
    ok("queued stop: flag kept as race guard", bool(row["cancel_requested"]))
    drow = db.query_one("SELECT state FROM dispatches WHERE task_id=?", (t1,))
    ok("queued dispatch row → cancelled", drow and drow["state"] == "cancelled")

    # ── 2. stop a done task → noop ──
    t2 = mk_task(UID, status="done", dispatch_state="completed")
    created_tasks.append(t2)
    r = c.post(f"/api/tasks/{t2}/stop")
    ok("done task stop → noop", r.status_code == 200 and r.json().get("stopped") == "noop", r.text[:150])
    ok("done task untouched", db.query_one("SELECT status FROM tasks WHERE id=?", (t2,))["status"] == "done")

    # ── 3. LIVE-stream stop: run the real executor on the stubbed stream ──
    # The stub branch requires BOTH the setting and this in-process env marker,
    # so a crashed gate can never leak stubbed dispatches to real lanes.
    os.environ["NEXUS_GATE_STUB"] = "1"
    db.set_setting("dispatch.stub_stream", "1")
    t3 = mk_task(UID, status="in_progress", dispatch_state="none", claimed_by=agent_id)
    created_tasks.append(t3)
    did3 = hd.start_dispatch(t3, agent_id)
    stopper = threading.Timer(6.0, lambda: db.execute(
        "UPDATE tasks SET cancel_requested=? WHERE id=?", (time.time(), t3)))
    stopper.start()
    t0 = time.time()
    hd.run_task_dispatch(did3, t3, agent_id)
    took = time.time() - t0
    row = db.query_one("SELECT * FROM tasks WHERE id=?", (t3,))
    ok("live stop: executor aborted the stream", 5 < took < 60, f"took {took:.1f}s")
    ok("live stop: task backlog + cancelled + flag cleared",
       row["status"] == "backlog" and row["dispatch_state"] == "cancelled"
       and not row["cancel_requested"] and not row["session_id"])
    drow = db.query_one("SELECT * FROM dispatches WHERE id=?", (did3,))
    ok("live stop: dispatch row cancelled", drow["state"] == "cancelled"
       and "stopped by operator" in (drow["error"] or ""))

    # ── 4. reconciler never re-queues a cancelled task ──
    hd.reconcile_stalled_dispatches(stale_s=0)
    row = db.query_one("SELECT status, dispatch_state FROM tasks WHERE id=?", (t3,))
    ok("reconciler leaves cancelled task alone",
       row["status"] == "backlog" and row["dispatch_state"] == "cancelled")

    # ── 5. top-check: a pre-set flag cancels before spending ──
    t5 = mk_task(UID, status="in_progress", dispatch_state="queued",
                 claimed_by=agent_id, cancel_requested=time.time())
    created_tasks.append(t5)
    did5 = hd.start_dispatch(t5, agent_id)
    hd.run_task_dispatch(did5, t5, agent_id)
    row = db.query_one("SELECT * FROM tasks WHERE id=?", (t5,))
    ok("pre-set flag → cancelled before any turn",
       row["dispatch_state"] == "cancelled" and row["status"] == "backlog"
       and not row["cancel_requested"])

    # ── 6. bulk-status: 3-task chain backlog → todo, deps intact ──
    wid = f"wf-{uuid.uuid4().hex[:8]}"
    db.execute("INSERT INTO workflows (id, name, goal, status, created_at, updated_at, user_id) "
               "VALUES (?,?,?,?,?,?,?)", (wid, "probe-bulk-wf", "probe", "active",
                                          time.time(), time.time(), UID))
    created_wfs.append(wid)
    a1 = mk_task(UID, workflow_id=wid, title="probe bulk stage 1")
    a2 = mk_task(UID, workflow_id=wid, title="probe bulk stage 2", depends_on=json.dumps([a1]))
    a3 = mk_task(UID, workflow_id=wid, title="probe bulk stage 3", depends_on=json.dumps([a2]))
    created_tasks += [a1, a2, a3]
    r = c.post("/api/tasks/bulk-status", json={"ids": [a1, a2, a3, "task-ghost"], "status": "todo"})
    j = r.json()
    ok("bulk start: 3 changed, ghost skipped",
       sorted(j.get("changed", [])) == sorted([a1, a2, a3]) and len(j.get("skipped", [])) == 1, r.text[:200])
    ok("bulk start: deps preserved",
       json.loads(db.query_one("SELECT depends_on FROM tasks WHERE id=?", (a2,))["depends_on"]) == [a1])
    ok("bulk start: dep gating still blocks stage 2",
       not hd.deps_satisfied(db.query_one("SELECT * FROM tasks WHERE id=?", (a2,))))

    # ── 7. bulk-stop over a mixed set ──
    r = c.post("/api/tasks/bulk-stop", json={"ids": [a1, t2]})
    res = {x["id"]: x["stopped"] for x in r.json().get("results", [])}
    ok("bulk stop: todo task stopped, done task noop",
       res.get(a1) == "immediate" and res.get(t2) == "noop", r.text[:200])

    # ── 8. workflow cascade delete ──
    ws_dir = hd.WORKSPACES / a3
    ws_dir.mkdir(parents=True, exist_ok=True)
    (ws_dir / "deliverable.md").write_text("probe")
    db.execute("UPDATE tasks SET workspace_path=? WHERE id=?", (str(ws_dir), a3))
    r = c.delete(f"/api/workflows/{wid}?cascade=tasks")
    ok("cascade delete: 3 tasks reported", r.status_code == 200 and r.json().get("deleted_tasks") == 3, r.text[:200])
    ok("cascade delete: rows gone",
       not db.query_one("SELECT 1 FROM tasks WHERE workflow_id=?", (wid,))
       and not db.query_one("SELECT 1 FROM workflows WHERE id=?", (wid,)))
    ok("cascade delete: workspace gone", not ws_dir.exists())

    # ── 9. branch artifacts: copy-back + branch-files endpoints ──
    os.makedirs(scratch_repo)
    def git(*args):
        return subprocess.run(["git", *args], cwd=scratch_repo, capture_output=True, text=True)
    git("init", "-b", "main")
    Path(scratch_repo, "README.md").write_text("probe\n")
    git("add", "-A")
    git("-c", "user.name=nexus", "-c", "user.email=nexus@local", "commit", "-m", "init")
    db.execute("INSERT OR REPLACE INTO project_owners (path, user_id, created_at) VALUES (?,?,?)",
               (os.path.realpath(scratch_repo), UID, time.time()))
    t9 = mk_task(UID, title="probe artifact task", repo_path=scratch_repo)
    created_tasks.append(t9)
    task9 = db.query_one("SELECT * FROM tasks WHERE id=?", (t9,))
    ctx = hd._repo_context(task9)
    ok("worktree created for probe task", bool(ctx), str(ctx))
    Path(ctx["worktree"], "How-To-Clean.pptx").write_bytes(b"PK\x03\x04 fake pptx bytes")
    Path(ctx["worktree"], "notes.md").write_text("notes\n")
    subprocess.run(["git", "add", "-A"], cwd=ctx["worktree"], capture_output=True)
    subprocess.run(["git", "-c", "user.name=nexus", "-c", "user.email=nexus@local",
                    "commit", "-m", "deck"], cwd=ctx["worktree"], capture_output=True)
    ws9 = hd.WORKSPACES / t9
    ws9.mkdir(parents=True, exist_ok=True)
    db.execute("UPDATE tasks SET workspace_path=? WHERE id=?", (str(ws9), t9))
    hd._capture_repo_result(task9, ws9, agent_id, ctx)
    ok("artifact copied into workspace/artifacts",
       (ws9 / "artifacts" / "How-To-Clean.pptx").is_file())
    ok("non-artifact .md NOT copied", not (ws9 / "artifacts" / "notes.md").exists())
    r = c.get(f"/api/tasks/{t9}/branch-files")
    names = {f["name"] for f in r.json().get("files", [])}
    ok("branch-files lists the deck", "How-To-Clean.pptx" in names, r.text[:200])
    r = c.get(f"/api/tasks/{t9}/branch-files/How-To-Clean.pptx")
    ok("branch file downloads via git show",
       r.status_code == 200 and r.content.startswith(b"PK\x03\x04"), str(r.status_code))
    r = c.get(f"/api/tasks/{t9}/branch-files/../../etc/passwd")
    ok("membership gate rejects traversal", r.status_code == 404, str(r.status_code))

    # ── 10. project delete (trash mode) ──
    r = c.post("/api/projects/delete", json={
        "path": scratch_repo, "confirm": os.path.basename(scratch_repo),
        "delete_tasks": True, "delete_repo": "trash"})
    ok("project delete ok", r.status_code == 200, r.text[:250])
    ok("repo dir moved to trash", not os.path.isdir(scratch_repo))
    trashed = [d for d in os.listdir(os.path.expanduser("~/.nexus-trash"))
               if d.startswith(os.path.basename(scratch_repo))]
    ok("trash copy exists", bool(trashed))
    ok("project_owners row gone",
       not db.query_one("SELECT 1 FROM project_owners WHERE path=?",
                        (os.path.realpath(scratch_repo),)))
    ok("member task deleted by project delete",
       not db.query_one("SELECT 1 FROM tasks WHERE id=?", (t9,)))
    for d in trashed:
        shutil.rmtree(os.path.join(os.path.expanduser("~/.nexus-trash"), d), ignore_errors=True)
    # An unowned/foreign path 404s before the confirm check; a wrong confirm
    # on an owned path 400s — both refuse the delete.
    ok("wrong confirm/foreign path rejected", c.post("/api/projects/delete", json={
        "path": os.path.expanduser("~/Projects"), "confirm": "nope"}).status_code in (400, 404))

finally:
    os.environ.pop("NEXUS_GATE_STUB", None)
    if stub_prev is None:
        db.execute("DELETE FROM settings WHERE key='dispatch.stub_stream'")
    else:
        db.set_setting("dispatch.stub_stream", stub_prev)
    _trash = os.path.expanduser("~/.nexus-trash")
    for tid in created_tasks:
        t = db.query_one("SELECT * FROM tasks WHERE id=?", (tid,))
        if t:
            db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        shutil.rmtree(hd.WORKSPACES / tid, ignore_errors=True)
        # task deletion now trashes workspaces instead of rmtree — sweep ours
        if os.path.isdir(_trash):
            for d in os.listdir(_trash):
                if d.startswith(f"{tid}-"):
                    shutil.rmtree(os.path.join(_trash, d), ignore_errors=True)
        db.execute("DELETE FROM dispatches WHERE task_id=?", (tid,))
    for wid in created_wfs:
        db.execute("DELETE FROM workflows WHERE id=?", (wid,))
    db.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    db.execute("DELETE FROM project_owners WHERE path=?", (os.path.realpath(scratch_repo),))
    shutil.rmtree(scratch_repo, ignore_errors=True)
    db.execute("DELETE FROM auth_sessions WHERE user_id=?", (UID,))
    db.execute("DELETE FROM users WHERE id=?", (UID,))
    db.execute("DELETE FROM activity WHERE user_id=?", (UID,))

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
