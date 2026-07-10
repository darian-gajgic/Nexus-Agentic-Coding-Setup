#!/usr/bin/env python3
"""Runtime gate for Quality Autopilot (QUALITY-AUTOPILOT-PLAN-2026-07-10 Part 5 + P4).

Self-cleaning, mostly deterministic (no live LLM): exercises the Q1–Q5, L1–L4,
Q7a/b/c levers and the binding guardrail rules end-to-end. A stubbed distillation
command covers the one model-shaped path. Run from the repo root:

    app/.venv/bin/python app/scripts/verify_autopilot_e2e.py
"""
import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "scripts"))
os.chdir(APP)

import database as db
db.init_db()
import autopilot as ap
import loop_engine as le
import hermes_dispatch as hd
import lessons as lessons_mod
import routing as routing_mod

import requests
from _gate_auth import owner_cookie
CK = owner_cookie()
BASE = "https://127.0.0.1:8777"

PASS = 0
FAIL = 0
_cleanup = []


def chk(name, cond):
    global PASS, FAIL
    if cond:
        print(f"  PASS  {name}"); PASS += 1
    else:
        print(f"  FAIL  {name}"); FAIL += 1


def get(p, **k): return requests.get(BASE + p, cookies=CK, verify=False, timeout=15, **k)
def post(p, **k): return requests.post(BASE + p, cookies=CK, verify=False, timeout=20, **k)
def patch(p, **k): return requests.patch(BASE + p, cookies=CK, verify=False, timeout=25, **k)


print("=== Q7a — preset derivation (rules 1/2/4/6) ===")
eco = ap.derive("manual", "eco", high_stakes=False, base_budget=1_000_000)
opt = ap.derive("assisted", "optimal", high_stakes=False, base_budget=1_000_000)
smart = ap.derive("full_auto", "smart", high_stakes=False, base_budget=1_000_000)
chk("rule1 preference derived (eco→speed, else quality)",
    eco["preference"] == "speed" and opt["preference"] == "quality" and smart["preference"] == "quality")
chk("Eco forces SR off + rounds 1", eco["super_result"] is False and eco["round_cap"] == 1)
chk("Smart forces SR on + max fan-out", smart["super_result"] is True and smart["fanout"] == "max")
chk("Optimal defers SR/fan-out to triage", opt["super_result"] is None and opt["fanout"] is None)
chk("rule6 Smart round cap == 3", smart["round_cap"] == 3)
chk("rule4 budget multiplier ×0.5/×1/×2",
    eco["budget"] == 500_000 and opt["budget"] == 1_000_000 and smart["budget"] == 2_000_000)
chk("involvement flips mode (full_auto/assisted closed, manual open)",
    smart["mode"] == "closed" and opt["sr_mode"] == "open" and eco["mode"] == "open")
chk("rule3 Eco model floor STAGED until Phase 7", "model_floor" in eco.get("staged", {}))
chk("P2 forward-deps staged (plan_recommend/escalation)",
    "plan_recommend" in eco.get("staged", {}) and "escalation" in eco.get("staged", {}))

print("=== Q7a — design_loop derivation (rule 2 hard floor) ===")
c_smart = le.design_loop("workflow", {"title": "Aud", "domain": "marketing", "super_result": True,
                                      "spend_profile": "smart", "autopilot": "full_auto"})
srt = [t for t in c_smart["triggers"] if t["id"] == "super_result"]
chk("design_loop Smart: quality/closed, SR cap≤3",
    c_smart["preference"] == "quality" and c_smart["mode"] == "closed" and srt and srt[0]["max_rounds"] <= 3)
c_eco_hs = le.design_loop("task", {"title": "T", "domain": "marketing", "high_stakes": True,
                                   "spend_profile": "eco", "autopilot": "full_auto"})
chk("rule2 Eco + high_stakes STILL auto-judges (risk floor beats speed)",
    c_eco_hs["auto_judge"] is True and c_eco_hs["preference"] == "speed")
chk("rule1 preference recorded, not independently set", c_smart.get("spend_profile") == "smart")

print("=== rule 8 / P6 — adaptive early-exit (respecified; no dead flag) ===")
# P4-required gate for rule-8 early-exit. Per the P6 respec, early-exit is NOT a
# derived preset flag (fan-out is planning-time; the reconciler cannot be skipped
# at runtime). It is realized by two mechanisms, and derive() emits no field:
#   P6(a) the SHIP quiet-stop (loop_engine._sweep_super_result), and
#   P6(b) the reconciler's own agreement-first framing (server._reconciler_gate_task).
chk("rule8 no dead early_exit flag emitted by derive() (2nd judge pass)",
    all("early_exit" not in ap.derive("assisted", sp) for sp in ("eco", "optimal", "smart")))
# P6(a): the SHIP quiet-stop IS the Optimal/Smart SR early-exit — design_loop
# surfaces it to the operator as the loop's stop condition ("Stops on SHIP").
c_opt_sr = le.design_loop("task", {"title": "X", "domain": "marketing", "super_result": True,
                                   "spend_profile": "optimal", "autopilot": "assisted"})
sr_opt = [t for t in c_opt_sr["triggers"] if t["id"] == "super_result"]
chk("rule8 P6(a) SHIP quiet-stop is the Optimal SR early-exit (surfaced as 'Stops on SHIP')",
    bool(sr_opt) and "Stops on SHIP" in (sr_opt[0].get("explain") or ""))
# P6(b): the reconciler's OWN framing computes agreement first and adversarially
# re-verifies only the DISAGREEMENTS. Drive the deterministic fan-out repair (the
# plan editor's revalidate) so the reconciler gate task is really produced.
try:
    fo = [{"title": "Lens A", "specialist": None, "domain": "marketing",
           "tags": ["investigation"], "depends_on_idx": []},
          {"title": "Lens B", "specialist": None, "domain": "marketing",
           "tags": ["investigation"], "depends_on_idx": []}]
    rf = post("/api/tasks/wizard/revalidate", json={"name": "Fanout early-exit", "tasks": fo})
    rtasks = rf.json().get("tasks", [])
    rec = next((t for t in rtasks if "reconciler" in (t.get("tags") or [])), None)
    desc = (rec or {}).get("description", "")
    chk("rule8 P6(b) reconciler framing = agreement-first, re-verify only DISAGREEMENTS",
        rec is not None and "AGREEMENT" in desc and "DISAGREEMENTS" in desc and "early-exit" in desc)
except Exception:
    chk("rule8 P6(b) reconciler revalidate reachable", False)

print("=== Q7a — default preset is a LIVE control (3rd judge finding 1) ===")
_ap_inv0 = db.get_setting("autopilot.default_involvement", "assisted")
_ap_sp0 = db.get_setting("autopilot.default_spend", "optimal")
_cleanup.append(lambda: (db.set_setting("autopilot.default_involvement", _ap_inv0 or "assisted"),
                         db.set_setting("autopilot.default_spend", _ap_sp0 or "optimal")))
db.set_setting("autopilot.default_involvement", "full_auto")
db.set_setting("autopilot.default_spend", "eco")
try:
    apd = get("/api/autopilot/defaults").json()
    chk("Q7a /api/autopilot/defaults reflects the configured setting (not a dead control)",
        apd.get("involvement") == "full_auto" and apd.get("spend") == "eco")
    db.set_setting("autopilot.default_involvement", "bogus-value")
    apd2 = get("/api/autopilot/defaults").json()
    chk("Q7a defaults normalize an invalid value to the built-in default",
        apd2.get("involvement") == "assisted")
except Exception:
    chk("Q7a /api/autopilot/defaults reachable", False)

print("=== Q4 — decision log harvest + injection ===")
wid = f"wf-t{int(time.time())}"
wsdir = hd.WORKSPACES / f"workflow-{wid}"
_cleanup.append(lambda: shutil.rmtree(wsdir, ignore_errors=True))
hd.harvest_decisions({"id": "t1", "title": "Stage One", "workflow_id": wid},
                     "# Report\n\n## Decisions\n- Chose Postgres because scale.\n- Named module foo.\n")
dpath = wsdir / "DECISIONS.md"
chk("Q4 harvest wrote DECISIONS.md with the lines",
    dpath.is_file() and "Chose Postgres" in dpath.read_text())
tws = hd.WORKSPACES / "t2ws"; tws.mkdir(parents=True, exist_ok=True)
_cleanup.append(lambda: shutil.rmtree(tws, ignore_errors=True))
fr = hd.build_framing({"id": "t2", "title": "Stage Two", "workflow_id": wid,
                       "deliverable_type": "content"}, tws)
chk("Q4 DECISIONS.md injected into a member's framing", str(dpath) in fr)
chk("Q4 ## Decisions contract present in framing", "## Decisions" in fr and "END your deliverable" in fr)

print("=== P10(a) — attachments AFTER DECISIONS/predecessors, BEFORE retry (framing order) ===")
# Judge finding 3: operator attachments were injected before DECISIONS/exemplars/
# predecessors, inverting the later-wins precedence P10(a) mandates. Build a framing
# that carries all three sections and assert the order DECISIONS < attachments < retry.
p10ws = hd.WORKSPACES / "p10-ws"; (p10ws / "attachments").mkdir(parents=True, exist_ok=True)
(p10ws / "attachments" / "brief.txt").write_text("operator brief")
_cleanup.append(lambda: shutil.rmtree(p10ws, ignore_errors=True))
p10fr = hd.build_framing({"id": "p10", "title": "Ordered stage", "workflow_id": wid,
                          "deliverable_type": "content",
                          "retry_feedback": "address the prior gap"}, p10ws)
i_dec, i_att, i_ret = (p10fr.find("PROJECT DECISION LOG"),
                       p10fr.find("ATTACHED input files"),
                       p10fr.find("This is a RETRY"))
chk("P10a all three framing sections present", i_dec >= 0 and i_att >= 0 and i_ret >= 0)
chk("P10a attachments come AFTER the DECISIONS log", i_dec >= 0 and i_att > i_dec)
chk("P10a retry feedback is the FINAL word (after attachments)", i_att >= 0 and i_ret > i_att)

print("=== Q5 — uncertainty tagging in framing + tools ===")
chk("Q5 framing tells executor to mark [UNSURE: reason]", "[UNSURE: reason]" in fr)
chk("Q5 cverify/cjudge check UNSURE (live copies)",
    "UNSURE" in open(os.path.expanduser("~/.local/bin/cverify")).read()
    and "UNSURE" in open(os.path.expanduser("~/.local/bin/cjudge")).read())

print("=== Q1 — golden-exemplar selection (SQL guards + L3 age-out + own-work reservation) ===")
uid = "u_owner"
ex_ws = hd.WORKSPACES / "exmpl-ws"; ex_ws.mkdir(parents=True, exist_ok=True)
(ex_ws / "deliverable.md").write_text("An excellent past marketing deliverable.")
_cleanup.append(lambda: shutil.rmtree(ex_ws, ignore_errors=True))
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, domain, user_id, judge_verdict, "
           "rubric_score, completed_at, workspace_path, deliverable_type) "
           "VALUES ('ex-good','Good past','done','marketing',?, 'SHIP','Rubric self-score: 3.9/4',?,?, 'content')",
           (uid, time.time(), str(ex_ws)))
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, domain, user_id, judge_verdict, "
           "rubric_score, completed_at, workspace_path, deliverable_type) "
           "VALUES ('ex-low','Low past','done','marketing',?, 'SHIP','score 2.0/4',?,?, 'content')",
           (uid, time.time(), str(ex_ws)))
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, domain, user_id, judge_verdict, "
           "rubric_score, completed_at, workspace_path, deliverable_type) "
           "VALUES ('ex-old','Old past','done','marketing',?, 'SHIP','4/4',?,?, 'content')",
           (uid, time.time() - 400 * 86400, str(ex_ws)))
_cleanup.append(lambda: db.execute("DELETE FROM tasks WHERE id IN ('ex-good','ex-low','ex-old')"))
# Scratch knowledge root with TWO curated marketing files — the live-default shape
# (2-3 curated exemplars per domain). finding-2 regression: at the DEFAULT
# exemplars.max=2 these must NOT crowd the operator's own SHIP'd work out (a slot
# is reserved), and curated files must be labelled own=False. onboarding.root is
# restored at the END of this block so the Q2 section still saves the true default.
q1root = tempfile.mkdtemp(prefix="q1-know-")
_cleanup.append(lambda: shutil.rmtree(q1root, ignore_errors=True))
os.makedirs(os.path.join(q1root, "domains", "marketing", "examples"), exist_ok=True)
open(os.path.join(q1root, "domains", "marketing", "RUBRIC.md"), "w").write("# R\n")
open(os.path.join(q1root, "domains", "marketing", "examples", "curated_a.md"), "w").write("curated A")
open(os.path.join(q1root, "domains", "marketing", "examples", "curated_b.md"), "w").write("curated B")
_q1_old_root = db.get_setting("onboarding.root", "")
_q1_old_max = db.get_setting("exemplars.max", "2")
db.set_setting("onboarding.root", q1root)
db.set_setting("exemplars.max", "2")  # DEFAULT — no room-making workaround
ex = hd.golden_exemplars({"id": "cur", "domain": "marketing", "user_id": uid,
                          "deliverable_type": "content"})
paths = [e["path"] for e in ex]
chk("Q1 selects the SHIP'd high-score exemplar", any("exmpl-ws" in p for p in paths))
chk("Q1 finding-2: own work survives at DEFAULT max=2 despite 2 curated files (reserved slot)",
    any(e.get("own") and "exmpl-ws" in e["path"] for e in ex))
chk("Q1 curated files labeled own=False (not the operator's own work)",
    any("curated_" in p for p in paths) and all(not e.get("own") for e in ex if "curated_" in e["path"]))
chk("Q1 excludes below-min-score + aged-out (L3) + code_change guard",
    hd.golden_exemplars({"id": "cur", "domain": "marketing", "user_id": uid,
                         "deliverable_type": "code_change"}) == [])
chk("Q1 skips a retry round", hd.golden_exemplars(
    {"id": "cur", "domain": "marketing", "user_id": uid, "deliverable_type": "content",
     "retry_feedback": "fix"}) == [])
# Honest framing labels: own work under the OWN header, curated under the reference header.
q1ws = hd.WORKSPACES / "q1fr-ws"; q1ws.mkdir(parents=True, exist_ok=True)
_cleanup.append(lambda: shutil.rmtree(q1ws, ignore_errors=True))
q1fr = hd.build_framing({"id": "q1fr", "title": "New marketing task", "domain": "marketing",
                         "user_id": uid, "deliverable_type": "content"}, q1ws)
chk("Q1 framing labels own past work honestly (own vs curated split, no false 'OWN' claim on curated)",
    "operator's OWN past deliverables" in q1fr and "Curated reference exemplars" in q1fr
    and str(ex_ws / "deliverable.md") in q1fr)
db.set_setting("onboarding.root", _q1_old_root or "")
db.set_setting("exemplars.max", _q1_old_max or "2")

print("=== Q2 — edit distillation (stubbed) → admin card → apply (L2) ===")
scratch = tempfile.mkdtemp(prefix="apqa-know-")
_cleanup.append(lambda: shutil.rmtree(scratch, ignore_errors=True))
os.makedirs(os.path.join(scratch, "domains", "marketing"), exist_ok=True)
open(os.path.join(scratch, "domains", "marketing", "PLAYBOOK.md"), "w").write("# PB\n- rule\n")
open(os.path.join(scratch, "domains", "marketing", "RUBRIC.md"), "w").write("# R\n")
open(os.path.join(scratch, "STYLE-VOICE.md"), "w").write("# V\n")
subprocess.run(["git", "init", "-q"], cwd=scratch)
subprocess.run(["git", "add", "-A"], cwd=scratch)
subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "i"], cwd=scratch)
stub = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
stub.write("#!/usr/bin/env bash\ncat <<'EOF'\nNEXUS_LESSONS_JSON_BEGIN\n"
           '{"deltas":[{"file":"PLAYBOOK.md","target":"canonical","kind":"add",'
           '"before":"","after":"- Always add a CTA.","rationale":"3 rejections"},'
           '{"file":"STYLE-VOICE.md","target":"user_overlay","kind":"add",'
           '"before":"","after":"- Warmer tone for this operator.","rationale":"their edits"}]}\n'
           "NEXUS_LESSONS_JSON_END\nEOF\n")
stub.close(); os.chmod(stub.name, 0o755)
_cleanup.append(lambda: os.unlink(stub.name))
_old_root = db.get_setting("onboarding.root", "")
_old_cmd = db.get_setting("lessons.cmd", "")
db.set_setting("onboarding.root", scratch)
db.set_setting("lessons.cmd", stub.name + " {domain} {evidence}")
_cleanup.append(lambda: (db.set_setting("onboarding.root", _old_root or ""),
                         db.set_setting("lessons.cmd", _old_cmd or "")))
for i in range(6):
    lessons_mod.record_evidence({"id": f"qat{i}", "domain": "marketing", "user_id": uid},
                                "feedback", f"add a CTA #{i}")
res = lessons_mod.run_distillation("marketing", uid, min_evidence=5)
_cleanup.append(lambda: db.execute("DELETE FROM edit_evidence WHERE domain='marketing'"))
appr = db.query_one("SELECT * FROM approvals WHERE id=?", (res.get("approval_id"),)) if res.get("approval_id") else None
_cleanup.append(lambda: db.execute("DELETE FROM approvals WHERE agent_id IN ('lessons-distiller','routing-stats')"))
chk("Q2 distillation filed an admin-scoped lesson_deltas card",
    bool(appr) and appr["action_type"] == "lesson_deltas" and appr["scope"] == "admin")
# apply as a MEMBER user — overlays exist only for non-owner users (the owner's
# canonical files ARE their voice; matches _knowledge_paths).
apres = lessons_mod.apply_deltas("marketing", res.get("deltas") or [], "u_member", "tester")
chk("Q2 apply committed the delta to the knowledge base (git)",
    (apres or {}).get("git_committed") is True)
chk("L2 canonical delta → shared domain file",
    "Always add a CTA" in open(os.path.join(scratch, "domains", "marketing", "PLAYBOOK.md")).read())
chk("L2 user_overlay delta routed to the user's overlay dir",
    os.path.isfile(os.path.join(scratch, "users", "u_member", "STYLE-VOICE.md"))
    and "Warmer tone" in open(os.path.join(scratch, "users", "u_member", "STYLE-VOICE.md")).read())
chk("Q2 consumed evidence marked distilled", lessons_mod.count_new_evidence("marketing") == 0)

print("=== L1/L4 — routing outcomes + fingerprint invalidation + rule 9 ===")
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, user_id, domain, spend_profile, "
           "autopilot, judge_verdict) VALUES ('ro-t','RO','done',?, 'marketing','optimal','assisted','SHIP')", (uid,))
_cleanup.append(lambda: db.execute("DELETE FROM tasks WHERE id='ro-t'"))
routing_mod.record_outcome("ro-t")
row = db.query_one("SELECT * FROM routing_outcomes WHERE task_id='ro-t'")
_cleanup.append(lambda: db.execute("DELETE FROM routing_outcomes WHERE task_id LIKE 'ro-%' OR task_id LIKE 'rc-%'"))
chk("L1 routing_outcomes row written at terminal state", bool(row) and row["spend_profile"] == "optimal")
routing_mod.set_learned_param("qa_test_thr", 7)
chk("L4 learned_param readable under current fingerprint", routing_mod.learned_param("qa_test_thr") == 7)
db.execute("UPDATE learned_params SET fingerprint='rotated' WHERE key='qa_test_thr'")
chk("L4 learned_param invalidated on tier rotation → default",
    routing_mod.learned_param("qa_test_thr", "DEF") == "DEF")
_cleanup.append(lambda: db.execute("DELETE FROM learned_params WHERE key='qa_test_thr'"))
# rule 9: the stats guard fires once per STATS_EVERY_TASKS outcomes — seed that
# many saturated Optimal rows so the collapse monitor actually runs.
for i in range(routing_mod.STATS_EVERY_TASKS + 5):
    db.execute("INSERT OR REPLACE INTO routing_outcomes (id, task_id, user_id, spend_profile, "
               "fanout_used, rounds_used, created_at) VALUES (?,?,?,?,?,?,?)",
               (f"rc-{i}", f"rc-{i}", uid, "optimal", 1, 3, time.time()))
db.set_setting("routing.stats_last_n", "0")
_before = db.query_one("SELECT COUNT(*) n FROM activity WHERE message LIKE '%ROUTER COLLAPSE%'")["n"]
routing_mod.sweep_stats()
_after = db.query_one("SELECT COUNT(*) n FROM activity WHERE message LIKE '%ROUTER COLLAPSE%'")["n"]
chk("rule9 collapse-monitor activity line fires on saturation", _after > _before)

print("=== Q7b — auto-approve-ship guard (rule 2), HTTP decisions ===")
_old_hours = db.get_setting("autopilot.auto_approve_ship_hours", "0")
db.set_setting("autopilot.auto_approve_ship_hours", "1")
_cleanup.append(lambda: db.set_setting("autopilot.auto_approve_ship_hours", _old_hours or "0"))
old_ts = time.time() - 2 * 3600
# eligible: full_auto, SHIP, NOT high-stakes → auto-approves
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, user_id, autopilot, high_stakes, "
           "judge_verdict) VALUES ('aa-ok','AA','review',?, 'full_auto',0,'SHIP')", (uid,))
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, user_id, autopilot, high_stakes, "
           "judge_verdict) VALUES ('aa-hs','AA-HS','review',?, 'full_auto',1,'SHIP')", (uid,))
db.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
           "risk_level, requested_at, user_id) VALUES ('aa-appr-ok','a','deliverable','d',?,'pending','high',?,?)",
           (json.dumps({"task_id": "aa-ok"}), old_ts, uid))
db.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
           "risk_level, requested_at, user_id) VALUES ('aa-appr-hs','a','deliverable','d',?,'pending','high',?,?)",
           (json.dumps({"task_id": "aa-hs"}), old_ts, uid))
_cleanup.append(lambda: db.execute("DELETE FROM tasks WHERE id IN ('aa-ok','aa-hs')"))
_cleanup.append(lambda: db.execute("DELETE FROM approvals WHERE id IN ('aa-appr-ok','aa-appr-hs')"))
le._sweep_auto_approve_ship()
ok = db.query_one("SELECT status FROM approvals WHERE id='aa-appr-ok'")["status"]
hs = db.query_one("SELECT status FROM approvals WHERE id='aa-appr-hs'")["status"]
chk("Q7b Full-Auto SHIP non-high-stakes auto-approved after hours", ok == "approved")
chk("rule2 high-stakes NEVER auto-approved (still pending)", hs == "pending")
try:
    dd = get("/api/decisions")
    body = dd.json()
    chk("Q7b /api/decisions returns {decisions,blocking,total}",
        dd.status_code == 200 and set(["decisions", "blocking", "total"]) <= set(body.keys()))
    chk("Q7b decision cards carry headline+recommendation",
        all(("headline" in c and "recommendation" in c) for c in body.get("decisions", [])) if body.get("decisions") else True)
except Exception as e:
    chk("Q7b /api/decisions reachable", False)

print("=== rule 5 — Eco pipeline collapse + high-stakes re-insertion (HTTP) ===")
coding = [{"title": "Spec", "specialist": "tech-lead-orchestrator", "domain": "software-engineering",
           "depends_on_idx": [], "spend_profile": "eco"},
          {"title": "Impl", "specialist": "code-implementer", "domain": "software-engineering",
           "depends_on_idx": [0], "spend_profile": "eco"}]
# REALISTIC-SHAPE fixture (regression, finding 1): the wizard's own coding
# template ALWAYS emits an acceptance-verifier with high_stakes TRUE, so the
# risk-floor scan must EXCLUDE gate stages — otherwise the mandatory verifier
# defeats the Eco collapse on every real plan. The thin fixture above (no
# verifier in the input) masked this, so exercise the realistic shape too.
coding_real = coding + [{"title": "Acceptance verification", "specialist": "acceptance-verifier",
                         "domain": "software-engineering", "high_stakes": True,
                         "depends_on_idx": [0, 1], "spend_profile": "eco"}]
try:
    r = post("/api/tasks/wizard/revalidate", json={"name": "Eco proj", "spend_profile": "eco", "tasks": coding})
    tasks = r.json().get("tasks", [])
    specs = [t.get("specialist") for t in tasks]
    chk("rule5 Eco collapses: no code-reviewer auto-inserted",
        "code-reviewer" not in specs and "acceptance-verifier" in specs)
    rr = post("/api/tasks/wizard/revalidate", json={"name": "Eco real", "spend_profile": "eco", "tasks": coding_real})
    specs_r = [t.get("specialist") for t in rr.json().get("tasks", [])]
    chk("rule5 Eco STILL collapses when the always-high-stakes verifier is already in the plan",
        "code-reviewer" not in specs_r and specs_r.count("acceptance-verifier") == 1)
    coding_hs = [dict(coding[0], high_stakes=True), dict(coding[1])] + coding_real[2:]
    r2 = post("/api/tasks/wizard/revalidate", json={"name": "Eco HS", "spend_profile": "eco", "tasks": coding_hs})
    specs2 = [t.get("specialist") for t in r2.json().get("tasks", [])]
    chk("rule2+5 a high-stakes WORK stage re-inserts the review gate even under Eco", "code-reviewer" in specs2)
except Exception:
    chk("rule5 revalidate reachable", False)

print("=== rule 7 — scheduler template passthrough (HTTP) ===")
try:
    jr = post("/api/scheduler", json={"name": "QA weekly", "cron_expr": "0 4 * * 1",
                                      "action": "weekly audit", "super_result": True, "spend_profile": "smart"})
    jid = jr.json().get("id")
    job = db.query_one("SELECT task_template FROM scheduled_jobs WHERE id=?", (jid,)) if jid else None
    tmpl = json.loads((job or {}).get("task_template") or "{}")
    chk("rule7 scheduled job stores the SR + spend template",
        tmpl.get("super_result") is True and tmpl.get("spend_profile") == "smart")
    if jid:
        _cleanup.append(lambda: db.execute("DELETE FROM scheduled_jobs WHERE id=?", (jid,)))
except Exception:
    chk("rule7 scheduler create reachable", False)

print("=== Q7a — workflow PATCH cascade of BOTH preset axes → member tasks (HTTP) ===")
# Part-5 gate: "workflow cascade of both fields". PATCH a workflow's two axes and
# assert every member task inherits BOTH autopilot AND spend_profile (mirrors the
# high_stakes cascade). Runs against the live server so the real cascade fires.
try:
    wc = post("/api/workflows", json={"name": "QA cascade proj"})
    wcid = wc.json().get("id")
    if wcid:
        _cleanup.append(lambda: db.execute("DELETE FROM workflows WHERE id=?", (wcid,)))
        for i in range(2):
            db.execute("INSERT OR REPLACE INTO tasks (id, title, status, user_id, workflow_id, "
                       "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                       (f"wc-m{i}", f"Member {i}", "backlog", uid, wcid, time.time(), time.time()))
        _cleanup.append(lambda: db.execute("DELETE FROM tasks WHERE workflow_id=?", (wcid,)))
        pr = patch(f"/api/workflows/{wcid}", json={"autopilot": "full_auto", "spend_profile": "smart"})
        mem = db.query_all("SELECT autopilot, spend_profile FROM tasks WHERE workflow_id=?", (wcid,))
        chk("Q7a workflow PATCH cascades BOTH axes to every member task",
            pr.status_code == 200 and len(mem) == 2
            and all(m["autopilot"] == "full_auto" and m["spend_profile"] == "smart" for m in mem))
        wrow = db.query_one("SELECT autopilot, spend_profile FROM workflows WHERE id=?", (wcid,))
        chk("Q7a workflow row itself carries both axes after PATCH",
            wrow and wrow["autopilot"] == "full_auto" and wrow["spend_profile"] == "smart")
    else:
        chk("Q7a workflow create for cascade reachable", False)
except Exception:
    chk("Q7a workflow cascade reachable", False)

print("=== Q2 — edit-evidence capture through a REAL reject→accept cycle (_capture_accept_diff) ===")
# Part-5 gate: "edit-evidence capture on reject→accept cycle". Exercise the ACTUAL
# approval endpoint (not record_evidence directly): a rejection versions the
# deliverable + captures feedback, then an accept of the reworked version drives
# server._capture_accept_diff → an 'accept_diff' evidence row. A dangling dependency
# parks the task so no live worker ever claims/dispatches it (deps_satisfied is
# fail-closed), keeping the cycle deterministic and LLM-free.
ev_ws = hd.WORKSPACES / f"qa-edit-{int(time.time())}"
ev_ws.mkdir(parents=True, exist_ok=True)
_cleanup.append(lambda: shutil.rmtree(ev_ws, ignore_errors=True))
(ev_ws / "deliverable.md").write_text("Draft one.\nNo call to action.\nHedged, unsure phrasing.\n")
etid = f"qa-edit-{int(time.time())}"
db.execute("INSERT OR REPLACE INTO tasks (id, title, status, user_id, domain, workspace_path, "
           "dispatch_state, depends_on, created_at, updated_at) "
           "VALUES (?,?,?,?,?,?,?,?,?,?)",
           (etid, "Edit-evidence task", "review", uid, "ecommerce", str(ev_ws),
            "completed", json.dumps(["qa-missing-blocker"]), time.time(), time.time()))
_cleanup.append(lambda: db.execute("DELETE FROM tasks WHERE id=?", (etid,)))
_cleanup.append(lambda: db.execute("DELETE FROM edit_evidence WHERE domain='ecommerce' AND task_id=?", (etid,)))
_cleanup.append(lambda: db.execute("DELETE FROM routing_outcomes WHERE task_id=?", (etid,)))
_cleanup.append(lambda: db.execute("DELETE FROM approvals WHERE id IN ('qa-appr-rej','qa-appr-acc')"))
db.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
           "risk_level, requested_at, user_id) VALUES ('qa-appr-rej','a','deliverable','d',?,'pending','low',?,?)",
           (json.dumps({"task_id": etid}), time.time(), uid))
try:
    rj = patch("/api/approvals/qa-appr-rej",
               json={"status": "rejected", "feedback": "Add a strong CTA; cut the hedging."})
    v1 = ev_ws / "deliverable.v1.md"
    chk("Q2 reject versioned the rejected deliverable (deliverable.v1.md)",
        rj.status_code == 200 and v1.is_file())
    fb_ev = db.query_one("SELECT * FROM edit_evidence WHERE task_id=? AND kind='feedback'", (etid,))
    chk("Q2 reject captured the operator feedback as evidence",
        bool(fb_ev) and "CTA" in (fb_ev["content"] or ""))
    # simulate the rework: a new accepted deliverable, task back in review for sign-off
    (ev_ws / "deliverable.md").write_text("Final draft.\nStrong call to action: Buy now.\nConfident, verified claims.\n")
    db.execute("UPDATE tasks SET status='review', dispatch_state='completed', claimed_by=NULL WHERE id=?", (etid,))
    db.execute("INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
               "risk_level, requested_at, user_id) VALUES ('qa-appr-acc','a','deliverable','d',?,'pending','low',?,?)",
               (json.dumps({"task_id": etid}), time.time(), uid))
    ac = patch("/api/approvals/qa-appr-acc", json={"status": "approved"})
    diff_ev = db.query_one("SELECT * FROM edit_evidence WHERE task_id=? AND kind='accept_diff'", (etid,))
    chk("Q2 accept drove _capture_accept_diff → an accept_diff evidence row",
        ac.status_code == 200 and bool(diff_ev)
        and "Buy now" in (diff_ev["content"] or "") and "call to action" in (diff_ev["content"] or ""))
except Exception as _e:
    chk("Q2 reject→accept approval cycle reachable", False)

print("=== P9 — ops hardening (busy_timeout + critic-sandbox age-out) ===")
import evals as _evals
chk("P9 PRAGMA busy_timeout is set explicitly (10s)",
    int(db.get_conn().execute("PRAGMA busy_timeout").fetchone()[0]) == 10000)
# critic-sandbox age-out is now a shared helper run at startup + on the scheduler,
# not lazy-only: a stale (>24h) sandbox is reclaimed while a fresh one survives.
_evals.CRITIC_SANDBOXES.mkdir(parents=True, exist_ok=True)
_stale = _evals.CRITIC_SANDBOXES / "qa-stale-sbx"
_fresh = _evals.CRITIC_SANDBOXES / "qa-fresh-sbx"
_stale.mkdir(exist_ok=True)
_fresh.mkdir(exist_ok=True)
_cleanup.append(lambda: shutil.rmtree(_stale, ignore_errors=True))
_cleanup.append(lambda: shutil.rmtree(_fresh, ignore_errors=True))
os.utime(_stale, (time.time() - 48 * 3600, time.time() - 48 * 3600))
_removed = _evals.sweep_critic_sandboxes(24.0)
chk("P9 sweep reclaims stale (>24h) sandboxes, keeps fresh ones (startup/scheduler-driven)",
    _removed >= 1 and not _stale.exists() and _fresh.exists())

for fn in _cleanup:
    try:
        fn()
    except Exception:
        pass

print(f"\n{'='*40}")
print(f"  {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
