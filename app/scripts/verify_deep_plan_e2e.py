#!/usr/bin/env python3
"""Runtime gate — Deep Plan mode (DEEP-PLAN-MODE-PLAN-2026-07-10).

Drives the conversational planning phase end to end against the LIVE server with
the PLANNING model stubbed via `plan.stub` (C-5: mirrors evals.stub — the
judge/critic command stubs do NOT reach session turns, so this flips plan.stub
instead). Deterministic parts (triage heuristics, structural validators,
family→deliverable_type, sweep) are exercised directly.

Run from app/:  .venv/bin/python scripts/verify_deep_plan_e2e.py
"""
import os
import sys
import time
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
import plan_engine as pe
import evals as ev
import server as srv

import requests
import urllib3
urllib3.disable_warnings()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _gate_auth import owner_cookie

CK = owner_cookie()
BASE = "https://127.0.0.1:8777"
PASS = 0
FAIL = 0
_created_wf = []


def chk(name, cond):
    global PASS, FAIL
    if cond:
        print(f"  PASS  {name}"); PASS += 1
    else:
        print(f"  FAIL  {name}"); FAIL += 1


def post(p, **k): return requests.post(BASE + p, cookies=CK, verify=False, timeout=40, **k)
def get(p, **k): return requests.get(BASE + p, cookies=CK, verify=False, timeout=15, **k)
def patch(p, **k): return requests.patch(BASE + p, cookies=CK, verify=False, timeout=15, **k)
def delete(p, **k): return requests.delete(BASE + p, cookies=CK, verify=False, timeout=15, **k)


# ── clean slate + stub the planning model ──
# Fable-5 checker finding N1: NEVER wipe the whole table — that destroys the
# operator's real planning history and orphans live Hermes sessions. Scope every
# delete to THIS gate's known goals, and free a linked Hermes session first.
GATE_GOALS = ("Build a login API", "another goal", "drafted goal",
              "repo grounding probe goal")


def _wipe_gate_sessions():
    ph = ",".join("?" * len(GATE_GOALS))
    for r in db.query_all(f"SELECT id, hermes_session_id FROM plan_sessions WHERE goal IN ({ph})",
                          GATE_GOALS):
        if r.get("hermes_session_id"):
            try:
                import hermes_dispatch as hd
                hd.delete_session(r["hermes_session_id"])
            except Exception:
                pass
    db.execute(f"DELETE FROM plan_sessions WHERE goal IN ({ph})", GATE_GOALS)


_wipe_gate_sessions()
_stub0 = db.get_setting("plan.stub", "0")
db.set_setting("plan.stub", "1")

print("=== Step 2 — triage heuristics (deterministic, no model) ===")
simple = pe.triage_heuristics("Fix the typo in the footer link")
complex_ = pe.triage_heuristics(
    "Audit the whole system, then build a marketing site and an email campaign "
    "based on the findings and deploy it to production")
chk("simple goal → low complexity, no recommend",
    simple["complexity"] < 3 and pe.recommend(simple)["recommend_deep_plan"] is False)
chk("complex goal → high complexity + recommend + blast radius",
    complex_["complexity"] >= 5 and pe.recommend(complex_)["recommend_deep_plan"] is True
    and complex_["blast_radius"] is True)
chk("recommendation payload shape",
    set(pe.recommend(complex_)) >= {"complexity", "ambiguity", "recommend_deep_plan",
                                    "recommend_super_result", "reasons", "family"})
chk("spend profile overrides setting (eco→never, smart→always)",
    pe.recommend(complex_, spend_profile="eco")["recommend_deep_plan"] is False
    and pe.recommend(simple, spend_profile="smart")["recommend_deep_plan"] is True)
chk("divergence math flags disagreement",
    pe.divergence([{"task_count": 1, "tokens": {"login"}, "shape": "single"},
                   {"task_count": 4, "tokens": {"db", "email"}, "shape": "dag"}])["score"] > 0.5)

print("=== Step 4 — session CRUD + resume + slot-fill READY stop rule ===")
r = post("/api/plan/sessions", json={"goal": "Build a login API", "family": "software"})
chk("start session (200)", r.status_code == 200)
s = r.json(); sid = s["id"]
chk("family + first questions + spec slots",
    s["family"] == "software" and len(s["spec"]) >= 3 and s["turns"] == 1)
chk("resume: GET one + list", get(f"/api/plan/sessions/{sid}").status_code == 200
    and any(x["id"] == sid for x in get("/api/plan/sessions").json()["sessions"]))
# fill required slots turn by turn until READY
for msg in ("FastAPI + SQLite", "returns 401 on expired token", "logs each failed login"):
    if s.get("ready"):
        break
    s = post(f"/api/plan/sessions/{sid}/turn", json={"message": msg}).json()
chk("required slots fill → READY stop rule", s["required_filled"] and s["ready"])
chk("direct slot edit (PATCH spec)",
    [x for x in patch(f"/api/plan/sessions/{sid}/spec",
                      json={"updates": {"out_of_scope": "no OAuth"}}).json()["spec"]
     if x["key"] == "out_of_scope"][0]["filled"])

print("=== Step 6 — draft seeds phase-2 + criteria distribution + family type ===")
# add a 2nd acceptance criterion so distribution is observable
patch(f"/api/plan/sessions/{sid}/spec",
      json={"updates": {"acceptance_criteria": ["returns 401 on expired token",
                                                "returns 200 on valid login"]}})
d = post(f"/api/plan/sessions/{sid}/draft", json={"super_result": False}).json()
chk("draft returns a workflow proposal + session id",
    d["type"] == "workflow" and d.get("plan_session_id") == sid)
tks = d["workflow"]["tasks"]
chk("family→deliverable_type on every task (software→code_change)",
    all(t.get("deliverable_type") == "code_change" for t in tks))
chk("acceptance criteria distributed as 'Done when:' lines",
    sum(ln.startswith("Done when:") for t in tks for ln in t["description"].splitlines()) >= 2)
chk("draft flips session status to drafted",
    get(f"/api/plan/sessions/{sid}").json()["status"] == "drafted")

print("=== Step 7 — structural validators + premortem stub → annotations ===")
orphan_spec = {"acceptance_criteria": ["returns 401 on expired token",
                                       "an orphan criterion covered nowhere zzz"],
               "stack_platform": "FastAPI"}
orphan_plan = [{"title": "Implement login", "depends_on_idx": [],
                "description": "implement. Done when: returns 401 on expired token"}]
w = srv._validate_plan(orphan_plan, "software", orphan_spec)
chk("orphan-criterion validator fires",
    any("not covered by any task" in x["message"] for x in w))
c = post(f"/api/plan/sessions/{sid}/critique", json={"tasks": tks}).json()
chk("premortem stub → findings annotations payload",
    isinstance(c.get("findings"), list) and len(c["findings"]) >= 1
    and c["findings"][0].get("task_idx") is not None)
chk("critique returns structural warnings + advisory flag",
    isinstance(c.get("warnings"), list) and c.get("critique_enabled") is True)

print("=== Step 7 — validator false-positive regressions (2026-07-12 fix) ===")
# the standard coding template: 5 stage titles all repeating the goal name —
# these mass-false-positived near-duplicate + cross-reference before the fix.
goal5 = "voice-first restaurant assistant MVP"
stages5 = [("Spec & plan", []), ("Implement + tests", [0]), ("Code review", [0, 1]),
           ("Fix review findings", [1, 2]), ("Acceptance verification", [0, 2, 3])]
five = [{"title": f"{p}: {goal5}", "depends_on_idx": dp,
         "description": f"{p} for the {goal5} against the SPEC."} for p, dp in stages5]
w5 = srv._validate_plan(five, "software", {"acceptance_criteria": []}, goal=goal5)
chk("standard 5-stage template → zero near-dup/cross-ref false positives",
    not any(("near-duplicate" in x["message"] or "seems to reference" in x["message"])
            for x in w5))
# a PARAPHRASED criterion (the draft model rewords) must count as covered now
para = srv._validate_plan(
    [{"title": "Implement dashboard", "depends_on_idx": [],
      "description": "Build the dashboard: render the shopping list sorted by day, "
                     "visible on page load."}],
    "software",
    {"acceptance_criteria": ["The shopping list is visible on the dashboard, sorted by day"]})
chk("paraphrased criterion counts as covered (fuzzy match)",
    not any("not covered" in x["message"] for x in para))
chk("draft output itself carries zero orphan-criterion warnings",
    not any("not covered" in x["message"] for x in (d.get("warnings") or [])))
# deterministic coverage guarantee: uncovered criteria land verbatim on a task
dist_tasks = [{"title": "Implement login", "specialist": "code-implementer",
               "depends_on_idx": [], "description": "Implement the login flow."},
              {"title": "Acceptance verification", "specialist": "acceptance-verifier",
               "depends_on_idx": [0], "description": "Verify acceptance."}]
notes = srv._distribute_criteria(
    dist_tasks, "software", {"acceptance_criteria": ["Exports a weekly totals report"]})
chk("_distribute_criteria appends the criterion verbatim (verifier fallback)",
    len(notes) == 1 and "Done when: Exports a weekly totals report"
    in dist_tasks[1]["description"])
chk("_distribute_criteria is idempotent",
    srv._distribute_criteria(dist_tasks, "software",
                             {"acceptance_criteria": ["Exports a weekly totals report"]}) == [])
chk("_plan_text marks any cut explicitly (no silent mid-sentence slice)",
    "…[truncated]" in srv._plan_text([{"title": "t", "description": "x" * 9000,
                                       "depends_on_idx": []}]))

print("=== Step 7b — revise loop (findings → corrected plan, stub) ===")
_ar0 = db.get_setting("plan.auto_revise", "1")
db.set_setting("plan.auto_revise", "1")
c1 = post(f"/api/plan/sessions/{sid}/critique", json={"tasks": tks}).json()
chk("auto_revise flag plumbed on draft + critique responses",
    d.get("auto_revise") is True and c1.get("auto_revise") is True)
db.set_setting("plan.auto_revise", "0")
chk("plan.auto_revise=0 → flag off",
    post(f"/api/plan/sessions/{sid}/critique", json={"tasks": tks}).json()
    .get("auto_revise") is False)
db.set_setting("plan.auto_revise", _ar0)
rv = post(f"/api/plan/sessions/{sid}/revise",
          json={"tasks": tks, "findings": c["findings"], "warnings": []})
rvj = rv.json() if rv.status_code == 200 else {}
chk("revise 200 + repaired tasks returned",
    rv.status_code == 200 and isinstance(rvj.get("tasks"), list) and rvj["tasks"])
chk("revision addressed the findings in task descriptions",
    any("Addressed finding" in (t.get("description") or "") for t in rvj.get("tasks", [])))
chk("revise returns warnings + repairs lists",
    isinstance(rvj.get("warnings"), list) and isinstance(rvj.get("repairs"), list))
chk("stub revision asks ONE operator question on a notes-free round",
    len(rvj.get("questions") or []) == 1 and (rvj["questions"][0].get("options")))
rv2 = post(f"/api/plan/sessions/{sid}/revise",
           json={"tasks": tks, "findings": c["findings"], "warnings": [],
                 "notes": "keep the current scope"}).json()
chk("operator notes (answers) → no further questions",
    (rv2.get("questions") or []) == [])
chk("revise keeps the session status drafted",
    get(f"/api/plan/sessions/{sid}").json()["status"] == "drafted")
chk("revise preserves operational task fields (deliverable_type survives)",
    all(t.get("deliverable_type") == "code_change" for t in rvj.get("tasks", [])))
# operator-owned fields must win over model CHANGES (not just drops): the plan
# editor's dials would otherwise be silently rewritten by a revision turn.
pf_new = [{"title": "Implement + tests: X", "deliverable_type": "analysis",
           "model": None, "high_stakes": False, "budget_tokens": None}]
pf_old = [{"title": "Implement + tests: X", "deliverable_type": "code_change",
           "model": "glm-5.1", "high_stakes": True, "budget_tokens": 2000000}]
srv._preserve_task_fields(pf_new, pf_old)
chk("_preserve_task_fields: operator-owned fields win over model CHANGES",
    pf_new[0]["deliverable_type"] == "code_change" and pf_new[0]["model"] == "glm-5.1"
    and pf_new[0]["high_stakes"] is True and pf_new[0]["budget_tokens"] == 2000000)

print("=== repo grounding — the plan is a CHANGE to existing work (2026-07-12) ===")
repos = [p for p in get("/api/projects").json().get("projects", []) if p.get("is_repo")]
chk("at least one visible git repo to ground on", bool(repos))
_rp = repos[0]["path"] if repos else ""
rg = post("/api/plan/sessions", json={"goal": "repo grounding probe goal",
                                      "family": "software", "repo_path": _rp}).json()
chk("session start accepts + persists repo_path",
    rg.get("repo_path") == _rp and
    (db.query_one("SELECT repo_path FROM plan_sessions WHERE id=?", (rg["id"],)) or {})
    .get("repo_path") == _rp)
rgd = post(f"/api/plan/sessions/{rg['id']}/draft", json={}).json()
chk("draft echoes repo_path for the proposal-modal 🧬 preselect",
    rgd.get("repo_path") == _rp)
blk = srv._plan_repo_block(_rp)
chk("_plan_repo_block reads the real project state (tree + languages)",
    "EXISTING PROJECT" in blk and "[tree]" in blk and "[languages]" in blk)
chk("invalid repo_path is rejected (400)",
    post("/api/plan/sessions", json={"goal": "repo grounding probe goal",
                                     "family": "software",
                                     "repo_path": "/etc"}).status_code == 400)

print("=== Step 8 — spec travels: attachment + critic context ===")
wf = post("/api/workflows", json={"name": "Login API DP", "goal": "Build a login API"}).json()
_created_wf.append(wf["id"])
a = post(f"/api/plan/sessions/{sid}/attach", json={"kind": "workflow", "id": wf["id"]})
adir = f"workspaces/workflow-{wf['id']}/attachments"
chk("attach writes SPEC.md + spec.json + status=created",
    a.status_code == 200 and os.path.isfile(f"{adir}/SPEC.md")
    and os.path.isfile(f"{adir}/spec.json")
    and get(f"/api/plan/sessions/{sid}").json()["status"] == "created")
# build_critic_sandbox copies spec.json into the critic context
tw = f"workspaces/dp-critic-{wf['id']}"
os.makedirs(tw, exist_ok=True)
open(f"{tw}/deliverable.md", "w").write("# d")
sb, _rel = ev.build_critic_sandbox(
    {"id": f"dt-{wf['id']}", "title": "t", "workspace_path": os.path.abspath(tw),
     "workflow_id": wf["id"], "description": "x"})
ctx = json.load(open(sb / "_critic_context" / "context.json"))
chk("spec.json reaches the critic context",
    ctx.get("spec") == "_critic_context/spec.json"
    and (sb / "_critic_context" / "spec.json").is_file())
import shutil
shutil.rmtree(sb, ignore_errors=True)
shutil.rmtree(tw, ignore_errors=True)

print("=== Step 4 — session hygiene sweep (abandon stale actives) ===")
r2 = post("/api/plan/sessions", json={"goal": "another goal", "family": "content"}).json()
db.execute("UPDATE plan_sessions SET updated_at=? WHERE id=?",
           (time.time() - 8 * 86400, r2["id"]))
srv.sweep_stale_plan_sessions()
chk("stale active session swept → abandoned",
    (db.query_one("SELECT status FROM plan_sessions WHERE id=?", (r2["id"],)) or {})
    .get("status") == "abandoned")
# 'drafted' hygiene: a drafted-but-never-attached session (the JARVIS voice/API
# path never calls /attach) must also be swept — else it strands with a live
# Hermes session forever (attach is the only path to 'created').
r3 = post("/api/plan/sessions", json={"goal": "drafted goal", "family": "content"}).json()
db.execute("UPDATE plan_sessions SET status='drafted', updated_at=? WHERE id=?",
           (time.time() - 8 * 86400, r3["id"]))
srv.sweep_stale_plan_sessions()
chk("stale drafted session swept → abandoned",
    (db.query_one("SELECT status FROM plan_sessions WHERE id=?", (r3["id"],)) or {})
    .get("status") == "abandoned")

# ── cleanup ──
for wid in _created_wf:
    delete(f"/api/workflows/{wid}")
    shutil.rmtree(f"workspaces/workflow-{wid}", ignore_errors=True)
_wipe_gate_sessions()
db.set_setting("plan.stub", _stub0)

print(f"\n{'='*44}")
if FAIL == 0:
    print(f"  ALL DEEP PLAN CHECKS PASSED: {PASS}/{PASS}")
    sys.exit(0)
print(f"  {FAIL} FAILED, {PASS} passed")
sys.exit(1)
