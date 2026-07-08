#!/usr/bin/env python
"""Block 3 runtime gate (docs/SPEC-BLOCK3.md) — revalidate, replanning, evals.

Self-cleaning probe against the LIVE server:
  R1  /api/tasks/wizard/revalidate — gate re-insertion, idempotency, clamps
  R2  replan detect → dismiss → re-arm → apply (archival, rewiring, loop
      reset, approval expiry, running-stage 409) — drafting is NOT exercised
      (it needs a live GLM; the sync path is the same wizard call the task
      wizard gate covers)
  R3  eval run lifecycle on a SCRATCH corpus with stubbed generation + judge
      (settings evals.corpus_root / evals.stub / judge.cmd — restored), score
      parsing, file endpoint, per-user isolation, cancel semantics

Run: .venv/bin/python scripts/verify_block3_e2e.py
"""
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import auth  # noqa: E402
import database as db  # noqa: E402

BASE = "https://127.0.0.1:8777"
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
    token = auth.create_session(user_id, "block3-gate")
    CLEANUP.append(lambda t=token: auth.destroy_session(t))
    c = httpx.Client(base_url=BASE, verify=False, timeout=30)
    c.cookies.set("nexus_session", token)
    return c


def main():
    owner = client_for("u_owner")

    # ═══ R1: revalidate ═══
    print("═══ R1: plan revalidate ═══")
    r = owner.post("/api/tasks/wizard/revalidate", json={"name": "b3-probe", "tasks": [
        {"title": "Spec it", "description": "d", "specialist": "tech-lead-orchestrator",
         "domain": "software-engineering"},
        {"title": "Build it", "description": "d", "specialist": "code-implementer",
         "domain": "software-engineering", "model": "glm-4.5-air", "depends_on_idx": [0]},
    ]})
    d = r.json()
    ok("coding plan gains all three gates", r.status_code == 200 and len(d["tasks"]) == 5,
       f"{r.status_code} {len(d.get('tasks', []))}")
    ok("dev-stage model floor enforced",
       all(t["model"] is None for t in d["tasks"] if t["specialist"] == "code-implementer"))
    ok("verifier is final high-stakes sink",
       d["tasks"][-1]["specialist"] == "acceptance-verifier" and d["tasks"][-1]["high_stakes"])
    r2 = owner.post("/api/tasks/wizard/revalidate",
                    json={"name": "b3-probe", "tasks": d["tasks"]})
    d2 = r2.json()
    ok("revalidate is idempotent (repaired plan passes clean)",
       r2.status_code == 200 and d2["repairs"] == [] and len(d2["tasks"]) == 5,
       json.dumps(d2.get("repairs", []))[:120])
    r3 = owner.post("/api/tasks/wizard/revalidate", json={"name": "x", "tasks": [
        {"title": "T", "description": "d", "specialist": "invented-specialist-xyz"}]})
    ok("unknown specialist cleared with repair note",
       r3.json()["tasks"][0]["specialist"] is None and r3.json()["repairs"])
    ok("empty plan is 400",
       owner.post("/api/tasks/wizard/revalidate", json={"tasks": []}).status_code == 400)

    # ═══ R2: replanning ═══
    print("═══ R2: mid-run replanning ═══")
    wf = owner.post("/api/workflows", json={"name": "b3-probe replan wf",
                                            "goal": "probe"}).json()
    wid = wf["id"]
    CLEANUP.append(lambda: (db.execute("DELETE FROM tasks WHERE workflow_id=?", (wid,)),
                            db.execute("DELETE FROM workflows WHERE id=?", (wid,))))
    ta = owner.post("/api/tasks", json={"title": "b3-probe done stage",
                                        "workflow_id": wid}).json()
    tb = owner.post("/api/tasks", json={"title": "b3-probe failing stage",
                                        "workflow_id": wid,
                                        "depends_on": [ta["id"]]}).json()
    now = time.time()
    db.execute("UPDATE tasks SET status='done', dispatch_state='completed', completed_at=? "
               "WHERE id=?", (now, ta["id"]))
    db.execute("UPDATE tasks SET status='in_progress', dispatch_state='failed', "
               "dispatch_error='probe: model exploded', claimed_by='b3-lane' WHERE id=?",
               (tb["id"],))
    # loop config with used rounds — apply must reset it
    db.execute("UPDATE workflows SET loop_config=? WHERE id=?",
               (json.dumps({"enabled": True, "mode": "closed", "triggers": [
                   {"id": "verify_fail", "enabled": True, "max_rounds": 2, "used": 2,
                    "used_tasks": {tb["id"]: 1}}]}), wid))
    # pending approval hanging off the failing task — apply must expire it
    appr_id = f"appr-b3-{uuid.uuid4().hex[:8]}"
    db.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, "
               "status, risk_level, requested_at, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
               (appr_id, "b3-lane", "deliverable", "b3 probe",
                json.dumps({"task_id": tb["id"]}), "pending", "high", now, "u_owner"))
    CLEANUP.append(lambda: db.execute("DELETE FROM approvals WHERE id=?", (appr_id,)))

    import loop_engine
    loop_engine._sweep_replan_detection()
    rp = json.loads(db.query_one("SELECT replan FROM workflows WHERE id=?", (wid,))["replan"]
                    or "null")
    ok("detection flags the failed stage",
       rp and rp["status"] == "needed" and rp["failed_task_id"] == tb["id"],
       json.dumps(rp)[:150])

    ok("dismiss works", owner.post(f"/api/workflows/{wid}/replan/dismiss").json().get("ok"))
    loop_engine._sweep_replan_detection()
    rp = json.loads(db.query_one("SELECT replan FROM workflows WHERE id=?", (wid,))["replan"])
    ok("dismissed failure is not re-flagged", rp["status"] == "dismissed")

    tc = owner.post("/api/tasks", json={"title": "b3-probe second failure",
                                        "workflow_id": wid}).json()
    db.execute("UPDATE tasks SET dispatch_state='failed', dispatch_error='probe 2' WHERE id=?",
               (tc["id"],))
    loop_engine._sweep_replan_detection()
    rp = json.loads(db.query_one("SELECT replan FROM workflows WHERE id=?", (wid,))["replan"])
    ok("a NEW failure re-arms detection",
       rp["status"] == "needed" and rp["failed_task_id"] == tc["id"], json.dumps(rp)[:150])

    # apply refused while a stage is executing
    db.execute("UPDATE tasks SET dispatch_state='streaming' WHERE id=?", (tc["id"],))
    r = owner.post(f"/api/workflows/{wid}/replan/apply",
                   json={"tasks": [{"title": "R", "description": "d"}]})
    ok("apply 409s while a stage is executing", r.status_code == 409, f"{r.status_code}")
    db.execute("UPDATE tasks SET dispatch_state='failed' WHERE id=?", (tc["id"],))

    r = owner.post(f"/api/workflows/{wid}/replan/apply", json={"tasks": [
        {"title": "b3 recovery step 1", "description": "retry differently"},
        {"title": "b3 recovery step 2", "description": "verify it", "depends_on_idx": [0]},
    ]})
    d = r.json()
    ok("apply succeeds", r.status_code == 200 and d.get("ok"), r.text[:150])
    new_ids = d.get("created_task_ids") or []
    rowb = db.query_one("SELECT * FROM tasks WHERE id=?", (tb["id"],))
    ok("failed stages archived + claim released",
       rowb["status"] == "archived" and rowb["claimed_by"] is None)
    ok("done stage untouched",
       db.query_one("SELECT status FROM tasks WHERE id=?", (ta["id"],))["status"] == "done")
    t1 = db.query_one("SELECT * FROM tasks WHERE id=?", (new_ids[0],))
    t2 = db.query_one("SELECT * FROM tasks WHERE id=?", (new_ids[1],))
    ok("recovery root inherits DONE deliverables as input",
       json.loads(t1["depends_on"] or "[]") == [ta["id"]], t1["depends_on"])
    ok("recovery chain wired by index",
       json.loads(t2["depends_on"] or "[]") == [new_ids[0]], t2["depends_on"])
    ok("pending approval on superseded work expired",
       db.query_one("SELECT status FROM approvals WHERE id=?", (appr_id,))["status"] == "expired")
    cfg = json.loads(db.query_one("SELECT loop_config FROM workflows WHERE id=?",
                                  (wid,))["loop_config"])
    ok("loop rounds reset by apply",
       cfg["triggers"][0]["used"] == 0 and "used_tasks" not in cfg["triggers"][0])
    wfd = owner.get(f"/api/workflows/{wid}").json()
    ok("rollup excludes archived tasks", wfd["tasks_total"] == 3,  # done + 2 recovery
       f"total={wfd['tasks_total']}")
    ok("replan recorded as applied", parse_status(wid) == "applied")

    # ═══ R3: evals ═══
    print("═══ R3: eval corpus ═══")
    real_corpus_domains = owner.get("/api/evals").json()["domains"]
    ok("real corpus discovered (≥ 9 domains, ≥ 20 cases)",
       len(real_corpus_domains) >= 9
       and sum(len(x["cases"]) for x in real_corpus_domains) >= 20)

    scratch = Path(tempfile.mkdtemp(prefix="b3-evals-"))
    CLEANUP.append(lambda: shutil.rmtree(scratch, ignore_errors=True))
    ddir = scratch / "probe-domain"
    (ddir / "evals").mkdir(parents=True)
    (ddir / "RUBRIC.md").write_text("# probe rubric\n")
    (ddir / "PLAYBOOK.md").write_text("# probe playbook\n")
    (ddir / "evals" / "case-one.md").write_text(
        "---\ntitle: Probe case one\nnotes: gate\n---\nWrite the thing.\n")
    (ddir / "evals" / "case-two.md").write_text(
        "---\ntitle: Probe case two\n---\nWrite the other thing.\n")
    judge_stub = scratch / "judge-stub.sh"
    judge_stub.write_text("#!/bin/bash\n"
                          "echo 'G1 PASS · G2 FAIL (probe)'\n"
                          "echo 'SCORES: a 3 · b 2 -> 21/28'\n"
                          "echo 'VERDICT: REVISE (probe)'\n")
    judge_stub.chmod(0o755)

    prev_judge = db.get_setting("judge.cmd", "cjudge {file} {domain}")
    db.set_setting("evals.corpus_root", str(scratch))
    db.set_setting("evals.stub", "1")
    db.set_setting("judge.cmd", f"{judge_stub} {{file}} {{domain}}")

    def restore_settings():
        db.execute("DELETE FROM settings WHERE key IN ('evals.corpus_root','evals.stub')")
        db.set_setting("judge.cmd", prev_judge)
    CLEANUP.append(restore_settings)

    r = owner.post("/api/evals/run", json={"domain": "probe-domain",
                                           "notes": "b3 gate run"})
    ok("run starts on scratch corpus", r.status_code == 200, r.text[:150])
    run_id = r.json().get("run_id")
    CLEANUP.append(lambda: (db.execute("DELETE FROM eval_results WHERE run_id=?", (run_id,)),
                            db.execute("DELETE FROM eval_runs WHERE id=?", (run_id,))))
    CLEANUP.append(lambda: shutil.rmtree(ROOT / "workspaces" / "evals" / run_id,
                                         ignore_errors=True))
    run = None
    for _ in range(40):
        time.sleep(1)
        run = owner.get(f"/api/evals/runs/{run_id}").json().get("run")
        if run and run["status"] not in ("running", "cancelling"):
            break
    ok("run completes", run and run["status"] == "completed", json.dumps(run or {})[:150])
    ok("both cases scored", run["cases_done"] == 2 and run["cases_total"] == 2)
    ok("scores aggregated (21+21 / 28+28)",
       run["score_total"] == 42 and run["score_max"] == 56,
       f"{run['score_total']}/{run['score_max']}")
    ok("fingerprint recorded", (run.get("fingerprint") or {}).get("combined"))
    det = owner.get(f"/api/evals/runs/{run_id}").json()
    res = det["results"]
    ok("per-case verdict + gates parsed",
       all(x["verdict"] == "REVISE" and x["gates_failed"] == 1 and x["gates_passed"] == 1
           for x in res), json.dumps(res)[:200])
    r = owner.get(f"/api/evals/runs/{run_id}/file", params={"case": "case-one"})
    ok("deliverable file served", r.status_code == 200 and "EVAL STUB" in r.text,
       f"{r.status_code}")
    ok("cancel on finished run is 409",
       owner.post(f"/api/evals/runs/{run_id}/cancel").status_code == 409)

    # isolation: another user sees nothing of the owner's runs
    probe_uid = f"u_b3_{uuid.uuid4().hex[:6]}"
    # active=1 is required for the session to authenticate; on an otherwise
    # single-user machine this flips the login wall on for a few seconds —
    # the owner client keeps working (direct token) and cleanup restores it
    # (same transient the multiuser probe accepts).
    db.execute("INSERT INTO users (id, username, display_name, password_hash, role, active, "
               "created_at) VALUES (?,?,?,?,?,1,?)",
               (probe_uid, f"b3-probe-{probe_uid[-4:]}", "B3 Probe", "", "member", time.time()))
    CLEANUP.append(lambda: (db.execute("DELETE FROM auth_sessions WHERE user_id=?", (probe_uid,)),
                            db.execute("DELETE FROM users WHERE id=?", (probe_uid,))))
    other = client_for(probe_uid)
    ok("other user sees no runs", other.get("/api/evals/runs").json()["runs"] == [])
    ok("other user's run detail is 404",
       other.get(f"/api/evals/runs/{run_id}").status_code == 404)
    ok("other user cannot cancel",
       other.post(f"/api/evals/runs/{run_id}/cancel").status_code == 404)
    ok("other user cannot replan-apply owner wf",
       other.post(f"/api/workflows/{wid}/replan/apply",
                  json={"tasks": [{"title": "x", "description": "d"}]}).status_code == 404)


def parse_status(wid):
    row = db.query_one("SELECT replan FROM workflows WHERE id=?", (wid,))
    try:
        return (json.loads(row["replan"] or "null") or {}).get("status")
    except Exception:
        return None


if __name__ == "__main__":
    try:
        main()
    finally:
        for fn in reversed(CLEANUP):
            try:
                fn()
            except Exception as e:
                print(f"  (cleanup: {e})")
    print(f"\n{'ALL PASSED' if FAIL == 0 else 'FAILURES'}: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
