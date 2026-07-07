#!/usr/bin/env python
"""Block 2 runtime gate (docs/SPEC-BLOCK2.md) — review v2, galaxy memory
editing, PR creation, code map.

Self-cleaning probe against the LIVE server:
  R1  review JSON: real line numbers (o/n) + Pygments `h` per line, lexer
      fallback; per-line comment CRUD + cross-user 404; retry consumes OPEN
      comments into retry_feedback (single chokepoint) and marks them consumed
  R2  memory edit/merge/delete on SEEDED qdrant probe points: re-embed proof,
      payload-tag preservation, foreign-tag 404, shared-point member 403 /
      admin 200, merge creates-then-deletes
  R3  POST /api/tasks/{id}/pr against a scratch repo + local bare origin with
      a STUBBED gh (settings pr.cmd — restored): branch pushed, URL stored,
      no-remote & no-branch 409s, foreign 404
  R4  code map present in the repo dispatch framing

Probe tasks carry a NEVER-DONE dependency so no real lane can claim them.
Run: .venv/bin/python scripts/verify_block2_e2e.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import auth  # noqa: E402
import database as db  # noqa: E402

BASE = "https://127.0.0.1:8777"
QDRANT = os.environ.get("MEM0_QDRANT_URL", "http://localhost:6333")
QPTS = f"{QDRANT}/collections/mem0/points"
PASS = FAIL = 0
CLEANUP = []


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def client_for(user_id: str) -> httpx.Client:
    token = auth.create_session(user_id, "block2-gate")
    CLEANUP.append(lambda t=token: auth.destroy_session(t))
    c = httpx.Client(base_url=BASE, verify=False, timeout=60)
    c.cookies.set("nexus_session", token)
    return c


def seed_task(user_id="u_owner", repo_path=None):
    """Probe task via direct INSERT (user_id stamped — stale-gate lesson).
    The bogus dependency keeps every real lane from ever claiming it."""
    tid = f"task-b2probe{uuid.uuid4().hex[:8]}"
    ws = ROOT / "workspaces" / tid
    ws.mkdir(parents=True, exist_ok=True)
    now = time.time()
    db.execute(
        "INSERT INTO tasks (id, title, description, status, created_at, updated_at, "
        "user_id, workspace_path, repo_path, depends_on, result_summary, dispatch_state) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (tid, f"b2 probe {tid[-4:]}", "block2 gate probe", "done", now, now,
         user_id, str(ws), repo_path, json.dumps(["task-block2-never-done"]),
         "probe deliverable", "completed"))
    CLEANUP.append(lambda: (db.execute("DELETE FROM review_comments WHERE task_id=?", (tid,)),
                            db.execute("DELETE FROM tasks WHERE id=?", (tid,)),
                            shutil.rmtree(ws, ignore_errors=True)))
    return tid, ws


def seed_point(text, user=None):
    pid = str(uuid.uuid4())
    payload = {"data": text, "hash": "b2probe", "created_at": "2026-07-08T12:00:00",
               "user_id": "hermes", "agent_id": "hermes", "channel": "nexus"}
    if user:
        payload["user"] = user
    r = requests.put(QPTS + "?wait=true", json={"points": [
        {"id": pid, "vector": {"": [0.01] * 768}, "payload": payload}]}, timeout=15)
    assert r.ok, r.text
    CLEANUP.append(lambda: requests.post(QPTS + "/delete?wait=true",
                                         json={"points": [pid]}, timeout=15))
    return pid


def qpoint(pid, with_vector=False):
    if with_vector:
        r = requests.post(QPTS, json={"ids": [pid], "with_payload": True,
                                      "with_vector": True}, timeout=15)
        pts = (r.json().get("result") or [])
        return pts[0] if pts else None
    r = requests.get(f"{QPTS}/{pid}", timeout=15)
    return r.json().get("result") if r.ok else None


def dense(pt):
    """qdrant returns the default ('') named vector unwrapped as a list."""
    v = (pt or {}).get("vector")
    return v.get("") if isinstance(v, dict) else v


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30)
    return r.returncode, (r.stdout + r.stderr).strip()


DIFF_FIXTURE = """\
diff --git a/tool.py b/tool.py
index 0000000..1111111 100644
--- a/tool.py
+++ b/tool.py
@@ -1,4 +1,5 @@
 import os
-def greet(name):
-    return "hi " + name
+def greet(name: str) -> str:
+    # politeness upgrade
+    return f"hello {name}"
 print(greet("nexus"))
diff --git a/data.xyzunknown b/data.xyzunknown
new file mode 100644
index 0000000..2222222
--- /dev/null
+++ b/data.xyzunknown
@@ -0,0 +1,1 @@
+opaque-blob-line
"""


def main():
    owner = client_for("u_owner")
    # a throwaway member user for the isolation checks (real users preserved)
    uid2 = f"u_b2probe{uuid.uuid4().hex[:6]}"
    db.execute("INSERT INTO users (id, username, display_name, password_hash, role, "
               "active, created_at) VALUES (?,?,?,?, 'member', 1, ?)",
               (uid2, f"b2probe-{uid2[-4:]}", "block2 probe", "!", time.time()))
    CLEANUP.append(lambda: (db.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid2,)),
                            db.execute("DELETE FROM users WHERE id=?", (uid2,))))
    other = client_for(uid2)

    # ═══ R1: review v2 — line numbers, highlight, comments, retry ═══
    print("═══ R1: review v2 ═══")
    tid, ws = seed_task(repo_path=str(ROOT))  # repo mode: reads changes.diff
    (ws / "changes.diff").write_text(DIFF_FIXTURE)
    r = owner.get(f"/api/tasks/{tid}/review").json()
    ok("git-mode review parses fixture", r.get("mode") == "git" and len(r.get("files", [])) == 2,
       json.dumps(r)[:150])
    py = r["files"][0]
    lines = py["hunks"][0]["lines"]
    ctx, dels, adds = lines[0], [l for l in lines if l["t"] == "-"], [l for l in lines if l["t"] == "+"]
    ok("context line carries BOTH file positions", ctx.get("o") == 1 and ctx.get("n") == 1)
    ok("deletion carries old / addition carries new line no",
       dels[0].get("o") == 2 and "n" not in dels[0] and adds[0].get("n") == 2 and "o" not in adds[0],
       json.dumps([dels[0], adds[0]]))
    ok("python lines are Pygments-highlighted",
       any('<span class="' in (l.get("h") or "") for l in lines))
    ok("unknown extension falls back to plain (no h)",
       all("h" not in l for h in r["files"][1]["hunks"] for l in h["lines"]))

    cr = owner.post(f"/api/tasks/{tid}/review/comments",
                    json={"file_path": "tool.py", "side": "new", "line_no": 2,
                          "line_text": "def greet(name: str) -> str:", "body": "type the return properly"})
    ok("comment created", cr.status_code == 200 and cr.json()["comment"]["status"] == "open",
       cr.text[:120])
    cid = cr.json()["comment"]["id"]
    owner.post(f"/api/tasks/{tid}/review/comments",
               json={"file_path": "tool.py", "side": "old", "line_no": 3, "body": "old concat was fine"})
    ok("bad side rejected", owner.post(f"/api/tasks/{tid}/review/comments",
       json={"file_path": "tool.py", "side": "weird", "line_no": 1, "body": "x"}).status_code == 400)
    ok("empty body rejected", owner.post(f"/api/tasks/{tid}/review/comments",
       json={"file_path": "tool.py", "side": "new", "line_no": 1, "body": "  "}).status_code == 400)
    ok("owner lists 2 open", owner.get(f"/api/tasks/{tid}/review/comments").json()["open"] == 2)
    ok("foreign user: comments 404", other.get(f"/api/tasks/{tid}/review/comments").status_code == 404)
    ok("foreign user: create 404", other.post(f"/api/tasks/{tid}/review/comments",
       json={"file_path": "tool.py", "side": "new", "line_no": 1, "body": "leak?"}).status_code == 404)
    ok("edit open comment", owner.patch(f"/api/tasks/{tid}/review/comments/{cid}",
       json={"body": "type the RETURN properly"}).status_code == 200)

    rr = owner.post(f"/api/tasks/{tid}/retry", json={"feedback": "operator: overall direction fine"})
    t = db.query_one("SELECT * FROM tasks WHERE id=?", (tid,))
    fb = t.get("retry_feedback") or ""
    ok("retry succeeded", rr.status_code == 200 and t["status"] == "todo", rr.text[:120])
    ok("operator feedback leads the block", fb.startswith("operator: overall direction fine"))
    ok("line comments rode along verbatim",
       "Reviewer LINE COMMENTS" in fb and "tool.py:2 [new]" in fb
       and "type the RETURN properly" in fb and "tool.py:3 [old]" in fb, fb[:200])
    ok("comments consumed after retry",
       owner.get(f"/api/tasks/{tid}/review/comments").json()["open"] == 0)
    ok("consumed comment refuses edits", owner.patch(
        f"/api/tasks/{tid}/review/comments/{cid}", json={"body": "x"}).status_code == 409)
    ok("workspace snapshot NOT taken for repo tasks (branch diff is the review)",
       not (ws / "_history").exists())

    # workspace-mode review (no repo): versions + highlight from real files
    tid2, ws2 = seed_task()
    (ws2 / "_history" / "v1").mkdir(parents=True)
    (ws2 / "_history" / "v1" / "calc.py").write_text("x = 1\n")
    (ws2 / "calc.py").write_text("x = 1\ny = x + 41\n")
    r2 = owner.get(f"/api/tasks/{tid2}/review").json()
    f2 = next((f for f in r2.get("files", []) if f["path"] == "calc.py"), None)
    ok("workspace-mode review diffs against the snapshot",
       r2.get("mode") == "workspace" and f2 and f2["additions"] == 1, json.dumps(r2)[:150])
    ok("workspace-mode lines get numbers + highlight",
       f2 and any(l.get("n") == 2 and l.get("h") for h in f2["hunks"] for l in h["lines"]))

    # ═══ R2: galaxy memory editing ═══
    print("═══ R2: memory edit/merge/delete ═══")
    mine_a = seed_point("b2probe mine alpha", user="u_owner")
    mine_b = seed_point("b2probe mine beta", user="u_owner")
    foreign = seed_point("b2probe foreign", user="u_someone_else")
    shared = seed_point("b2probe shared knowledge")

    lst = owner.get("/api/memory").json()
    ids_seen = {str(m["id"]) for m in lst.get("memories", [])}
    ok("owner list: own + shared visible, foreign invisible",
       {mine_a, shared} <= ids_seen and foreign not in ids_seen)

    before_vec = dense(qpoint(mine_a, with_vector=True))
    er = owner.patch(f"/api/memory/{mine_a}", json={"text": "b2probe mine alpha REWRITTEN"})
    after = qpoint(mine_a, with_vector=True)
    ok("edit own point", er.status_code == 200, er.text[:120])
    ok("text rewritten in qdrant", after["payload"]["data"] == "b2probe mine alpha REWRITTEN")
    ok("user tag survived the edit", after["payload"].get("user") == "u_owner")
    ok("vector actually re-embedded", dense(after) != before_vec)
    ok("foreign point: edit 404",
       owner.patch(f"/api/memory/{foreign}", json={"text": "x"}).status_code == 404)
    ok("foreign point: delete 404", owner.delete(f"/api/memory/{foreign}").status_code == 404)
    ok("shared point: member is 403",
       other.patch(f"/api/memory/{shared}", json={"text": "member rewrite"}).status_code == 403)
    ok("shared point: admin may edit",
       owner.patch(f"/api/memory/{shared}", json={"text": "b2probe shared v2"}).status_code == 200)

    mr = owner.post("/api/memory/merge", json={"ids": [mine_a, foreign], "text": "x"})
    ok("merge with a foreign source refuses (404)", mr.status_code == 404)
    ok("refused merge deleted nothing", qpoint(mine_a) is not None)
    ok("merge needs ≥2 ids",
       owner.post("/api/memory/merge", json={"ids": [mine_a], "text": "x"}).status_code == 400)
    mr = owner.post("/api/memory/merge",
                    json={"ids": [mine_a, mine_b], "text": "b2probe merged alpha+beta"})
    ok("merge own points", mr.status_code == 200 and mr.json().get("failed") == [], mr.text[:150])
    merged_id = mr.json().get("id")
    if merged_id:
        CLEANUP.append(lambda: requests.post(QPTS + "/delete?wait=true",
                                             json={"points": [merged_id]}, timeout=15))
    mp = qpoint(merged_id) if merged_id else None
    ok("merged point stamped user + source=merge",
       mp and mp["payload"].get("user") == "u_owner" and mp["payload"].get("source") == "merge")
    ok("merge sources deleted AFTER the add",
       qpoint(mine_a) is None and qpoint(mine_b) is None)
    ok("delete own point", owner.delete(f"/api/memory/{merged_id}").status_code == 200
       and qpoint(merged_id) is None)

    # ═══ R3: PR creation (stubbed gh, real push to a local bare origin) ═══
    print("═══ R3: PR creation ═══")
    scratch = Path.home() / f".b2probe-repo-{uuid.uuid4().hex[:6]}"
    origin = Path.home() / f".b2probe-origin-{uuid.uuid4().hex[:6]}.git"
    CLEANUP.append(lambda: (shutil.rmtree(scratch, ignore_errors=True),
                            shutil.rmtree(origin, ignore_errors=True)))
    scratch.mkdir()
    git(scratch, "init", "-b", "main")
    (scratch / "README.md").write_text("# probe\n")
    (scratch / "main.py").write_text("print('probe')\n")
    git(scratch, "add", "-A")
    git(scratch, "-c", "user.name=nexus", "-c", "user.email=nexus@local", "commit", "-m", "init")

    tid3, ws3 = seed_task(repo_path=str(scratch))
    slug = tid3.replace("task-", "")
    pr_no_branch = owner.post(f"/api/tasks/{tid3}/pr")
    ok("no task branch → 409", pr_no_branch.status_code == 409, pr_no_branch.text[:120])
    git(scratch, "checkout", "-b", f"nexus/{slug}")
    (scratch / "main.py").write_text("print('probe v2')\n")
    git(scratch, "add", "-A")
    git(scratch, "-c", "user.name=nexus", "-c", "user.email=nexus@local", "commit", "-m", "task work")
    git(scratch, "checkout", "main")
    ok("no origin remote → 409 with publish hint",
       owner.post(f"/api/tasks/{tid3}/pr").status_code == 409)

    subprocess.run(["git", "init", "--bare", str(origin)], capture_output=True, timeout=30)
    git(scratch, "remote", "add", "origin", str(origin))
    stub = scratch / "gh-stub.sh"
    args_log = scratch / "gh-args.log"
    stub.write_text(f"#!/bin/bash\necho \"$@\" > {args_log}\n"
                    "echo 'https://github.com/probe/repo/pull/42'\n")
    stub.chmod(0o755)
    prev_cmd = db.get_setting("pr.cmd", None)
    db.set_setting("pr.cmd", f"{stub} {{branch}} {{base}} {{title}} {{bodyfile}}")
    CLEANUP.append(lambda: (db.set_setting("pr.cmd", prev_cmd) if prev_cmd
                            else db.execute("DELETE FROM settings WHERE key='pr.cmd'")))
    ok("foreign user: pr 404", other.post(f"/api/tasks/{tid3}/pr").status_code == 404)
    pr = owner.post(f"/api/tasks/{tid3}/pr")
    ok("PR created via stub", pr.status_code == 200
       and pr.json().get("url") == "https://github.com/probe/repo/pull/42", pr.text[:200])
    code, _ = git(scratch, "--git-dir", str(origin), "rev-parse", "--verify", f"nexus/{slug}")
    ok("branch really pushed to origin", code == 0)
    t3 = db.query_one("SELECT pr_url FROM tasks WHERE id=?", (tid3,))
    ok("pr_url persisted on the task", t3["pr_url"] == "https://github.com/probe/repo/pull/42")
    argv = args_log.read_text().strip() if args_log.exists() else ""
    ok("stub received branch/base + bodyfile", f"nexus/{slug} main" in argv and "_pr_body.md" in argv, argv)
    bodyfile = argv.split()[-1] if argv else ""
    body = Path(bodyfile).read_text() if bodyfile and Path(bodyfile).exists() else ""
    ok("PR body carries title + attribution",
       "b2 probe" in body and "Created by Nexus Agent OS" in body, body[:120])
    pr2 = owner.post(f"/api/tasks/{tid3}/pr")
    ok("second call reuses the stored PR", pr2.status_code == 200 and pr2.json().get("existing"))

    # ═══ R4: code map in the repo framing ═══
    print("═══ R4: code map ═══")
    import hermes_dispatch as hd
    cm = hd._code_map(str(scratch))
    ok("code map lists tracked files + counts", "tracked files" in cm and "main.py" in cm, cm[:120])
    t3full = db.query_one("SELECT * FROM tasks WHERE id=?", (tid3,))
    ctx = hd._repo_context(t3full)
    framing = hd.build_framing(t3full, ws3, repo_ctx=ctx)
    ok("framing injects CODE MAP block", "CODE MAP (repository layout):" in framing)
    ok("framing still names the worktree branch", f"nexus/{slug}" in framing)

    print(f"\n{'='*46}\n  BLOCK 2 E2E: {PASS} passed, {FAIL} failed\n{'='*46}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        for fn in reversed(CLEANUP):
            try:
                fn()
            except Exception as e:
                print(f"  (cleanup: {e})")
    sys.exit(rc)
