#!/usr/bin/env python3
"""Mode-coherence gate (2026-07-12b audit): rule-4 budgets scale the per-type
baseline; routing composes with the spend profile; the judge-REVISE tier
escalation completes the cascade; triage suggests a spend profile.

Run:  .venv/bin/python scripts/verify_mode_coherence_e2e.py
Self-cleaning (probe rows + settings restored). No LLM calls.
"""
import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import database as db          # noqa: E402
import autopilot as ap         # noqa: E402
import routing                 # noqa: E402
import plan_engine as pe       # noqa: E402

PASS = FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


saved = {k: db.get_setting(k) for k in
         ("dispatch.default_budget.content", "dispatch.default_task_budget",
          "models.auto_route", "dispatch.escalate_on_revise",
          "dispatch.session_effort")}
created_tasks, created_models = [], []

try:
    # ── 1. preset_fields: mode × type budget matrix ──
    print("=== I-1: rule-4 multiplier scales the per-type baseline ===")
    matrix = {}
    for sp in ("eco", "optimal", "smart"):
        for dtype in ("content", "code_change", None):
            _inv, _sp, budget = ap.preset_fields("assisted", sp, False, None, dtype)
            matrix[(sp, dtype)] = budget
    ok("eco content = 1M (was 2.5M pre-fix)", matrix[("eco", "content")] == 1_000_000,
       str(matrix[("eco", "content")]))
    ok("Balanced content = 2M (was 5M)", matrix[("optimal", "content")] == 2_000_000)
    ok("smart content = 4M (was 10M)", matrix[("smart", "content")] == 4_000_000)
    ok("untyped keeps global base: 2.5M/5M/10M",
       matrix[("eco", None)] == 2_500_000 and matrix[("optimal", None)] == 5_000_000
       and matrix[("smart", None)] == 10_000_000)
    ok("code_change (no type default registered) = global base",
       matrix[("optimal", "code_change")] == 5_000_000)
    _inv, _sp, explicit = ap.preset_fields("assisted", "eco", False, 777_000, "content")
    ok("explicit budget always wins", explicit == 777_000)

    # ── 2. routing × spend profile ──
    print("=== I-2: routing composes with the mode ===")
    db.set_setting("models.auto_route", "1")
    base = {"title": "Write a launch blog post for the product",
            "description": "a substantial marketing article about the launch and its features",
            "domain": "marketing", "specialist": None, "deliverable_type": "content",
            "high_stakes": 0, "model": None}
    easy_model = (db.resolve_assignment("u_owner", "easy") or {}).get("model_id")
    m_eco, r_eco = routing.select_model_for_task({**base, "spend_profile": "eco"}, "u_owner")
    ok("eco floors a non-trivial task to the light tier",
       m_eco == easy_model and r_eco and "Eco profile" in r_eco, f"{m_eco} / {r_eco}")
    m_opt, _ = routing.select_model_for_task({**base, "spend_profile": "optimal"}, "u_owner")
    ok("Balanced leaves the same task on the strong default (NULL)", m_opt is None)
    # a description that would upgrade — smart must refuse anything below default
    now = time.time()
    rid = f"mdl-{uuid.uuid4().hex[:10]}"
    created_models.append(rid)
    db.execute("INSERT INTO user_models (id, user_id, provider, model_id, label, route, "
               "enabled, config, description, created_at, updated_at) "
               "VALUES (?,NULL,'zai','probe-mid-model','probe','hermes',1,'{}',?,?,?)",
               (rid, "Best for: launch blog post marketing article", now, now))
    m_sm, _ = routing.select_model_for_task({**base, "spend_profile": "smart"}, "u_owner")
    ok("smart never routes below the strong default", m_sm is None, str(m_sm))
    m_ecodesc, _ = routing.select_model_for_task({**base, "spend_profile": "eco"}, "u_owner")
    ok("eco suppresses description-upgrades", m_ecodesc == easy_model, str(m_ecodesc))
    m_hs, _ = routing.select_model_for_task({**base, "spend_profile": "eco",
                                             "high_stakes": 1}, "u_owner")
    ok("high-stakes ignores the eco floor", m_hs is None, str(m_hs))
    m_dev, _ = routing.select_model_for_task({**base, "spend_profile": "eco",
                                              "specialist": "code-implementer"}, "u_owner")
    ok("dev specialist ignores the eco floor", m_dev is None)

    # ── 3. recommend_spend matrix ──
    print("=== I-4: deterministic per-task spend suggestion ===")
    sp1, why1 = pe.recommend_spend(pe.triage_heuristics("Reformat the csv export"))
    ok("trivial mechanical goal → eco", sp1 == "eco", f"{sp1} / {why1}")
    goal_hard = ("Build and deploy the complete multi-tenant webshop with payments, "
                 "email campaigns and a full admin dashboard, then send the launch "
                 "newsletter to all customers. First research competitors, then design "
                 "the data model based on that, then implement the frontend and backend.")
    sp2, why2 = pe.recommend_spend(pe.triage_heuristics(goal_hard))
    ok("complex/blast-radius goal → smart", sp2 == "smart", f"{sp2} / {why2}")
    sp3, _ = pe.recommend_spend(pe.triage_heuristics(
        "Write a landing page draft for our new consulting offer with three sections"))
    ok("moderate goal → optimal (Balanced)", sp3 == "optimal", str(sp3))
    tri = pe.recommend(pe.triage_heuristics(goal_hard), None)
    ok("triage payload carries recommend_spend + reasons",
       tri.get("recommend_spend") == "smart" and tri.get("spend_reasons"))

    # ── 4. cascade: judge-REVISE tier escalation in _retry_task ──
    print("=== gap a: light-tier attempt escalates on judge REVISE ===")
    import server as srv
    db.set_setting("dispatch.escalate_on_revise", "1")
    hard_model = (db.resolve_assignment("u_owner", "complicated") or {}).get("model_id")

    def mk(**kw):
        tid = f"task-{uuid.uuid4().hex[:8]}"
        created_tasks.append(tid)
        f = {"id": tid, "title": "probe escalation", "description": "p", "status": "review",
             "priority": 2, "created_at": time.time(), "updated_at": time.time(),
             "user_id": "u_owner", "dispatch_state": "completed",
             "deliverable_type": "content", "judge_verdict": "REVISE",
             "judge_output": "Verdict: REVISE\nfix the hook", "model": easy_model}
        f.update(kw)
        db.execute(f"INSERT INTO tasks ({', '.join(f)}) VALUES ({','.join('?' * len(f))})",
                   tuple(f.values()))
        return tid

    t1 = mk()
    srv._retry_task(t1, "probe feedback")
    row = db.query_one("SELECT model, model_reason FROM tasks WHERE id=?", (t1,))
    ok("light-tier REVISE retry escalates to the strong tier",
       row["model"] == hard_model and "escalated" in (row["model_reason"] or ""),
       str(dict(row)))
    t2 = mk(high_stakes=1)
    srv._retry_task(t2, "probe feedback")
    ok("high-stakes never escalates via this path",
       db.query_one("SELECT model FROM tasks WHERE id=?", (t2,))["model"] == easy_model)
    t3 = mk(specialist="code-implementer")
    srv._retry_task(t3, "probe feedback")
    ok("dev-pipeline task keeps its model",
       db.query_one("SELECT model FROM tasks WHERE id=?", (t3,))["model"] == easy_model)
    t4 = mk(model=hard_model)
    srv._retry_task(t4, "probe feedback")
    ok("already-strong model untouched",
       db.query_one("SELECT model FROM tasks WHERE id=?", (t4,))["model"] == hard_model)
    db.set_setting("dispatch.escalate_on_revise", "0")
    t5 = mk()
    srv._retry_task(t5, "probe feedback")
    ok("kill switch respected",
       db.query_one("SELECT model FROM tasks WHERE id=?", (t5,))["model"] == easy_model)
    db.set_setting("dispatch.escalate_on_revise", "1")

    # ── 4b. per-task reasoning effort (I-3 follow-up) ──
    print("=== I-3: per-task reasoning effort (session bridge) ===")
    import hermes_dispatch as hd_mod
    db.set_setting("dispatch.session_effort", "1")
    eff = hd_mod.session_effort_for_task
    ok("smart → xhigh", eff({"spend_profile": "smart", "deliverable_type": "content",
                             "high_stakes": 0}, "glm-5.2") == "xhigh")
    ok("high-stakes → xhigh regardless of mode",
       eff({"spend_profile": "eco", "deliverable_type": None, "high_stakes": 1},
           "glm-5.2") == "xhigh")
    ok("Balanced content → high (creative work: judge gates quality)",
       eff({"spend_profile": "optimal", "deliverable_type": "content",
            "high_stakes": 0}, "glm-5.2") == "high")
    ok("Balanced analysis/code → None (xhigh default, reasoning-heavy)",
       eff({"spend_profile": "optimal", "deliverable_type": "analysis",
            "high_stakes": 0}, "glm-5.2") is None
       and eff({"spend_profile": "optimal", "deliverable_type": "code_change",
                "high_stakes": 0}, "glm-5.2") is None)
    ok("eco light tier → medium / eco escalated to strong tier → high",
       eff({"spend_profile": "eco", "deliverable_type": "content", "high_stakes": 0},
           "glm-4.5-air") == "medium"
       and eff({"spend_profile": "eco", "deliverable_type": "content",
                "high_stakes": 0}, "glm-5.2") == "high")
    db.set_setting("dispatch.session_effort", "0")
    ok("kill switch → None", eff({"spend_profile": "smart", "deliverable_type": None,
                                  "high_stakes": 0}, "glm-5.2") is None)
    db.set_setting("dispatch.session_effort", "1")
    # bridge round-trip: publish merges next to an existing api_key entry
    sid_probe = f"probe-effort-{uuid.uuid4().hex[:8]}"
    hd_mod._rewrite_session_keys(lambda s: s.__setitem__(
        sid_probe, {"api_key": "probe-key", "ts": time.time()}))
    hd_mod.publish_session_effort(sid_probe, {"spend_profile": "optimal",
                                              "deliverable_type": "content",
                                              "high_stakes": 0}, "glm-5.2")
    data = json.load(open(os.path.expanduser("~/.hermes/session-keys.json")))
    entry = (data.get("sessions") or {}).get(sid_probe) or {}
    ok("bridge entry merges effort next to api_key",
       entry.get("effort") == "high" and entry.get("api_key") == "probe-key", str(entry))
    hd_mod.remove_session_key(sid_probe)

    # ── 5. retry slice honors the per-type baseline ──
    print("=== I-1b: retry budget slice per type ===")
    t6 = mk(model=None, judge_verdict=None, tokens_used=2_500_000, budget_tokens=None)
    srv._retry_task(t6, "probe feedback")
    b6 = db.query_one("SELECT budget_tokens FROM tasks WHERE id=?", (t6,))["budget_tokens"]
    ok("NULL-budget content task extends by the 2M content slice (used+2M)",
       b6 == 4_500_000, str(b6))

finally:
    for k, v in saved.items():
        if v is None:
            db.execute("DELETE FROM settings WHERE key=?", (k,))
        else:
            db.set_setting(k, v)
    for tid in created_tasks:
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))
        db.execute("DELETE FROM approvals WHERE payload LIKE ?", (f'%"{tid}"%',))
    for rid in created_models:
        db.execute("DELETE FROM user_models WHERE id=?", (rid,))
    db.execute("DELETE FROM activity WHERE message LIKE '%probe escalation%'")

print(f"\n{'ALL PASS' if not FAIL else 'FAILURES'}: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
