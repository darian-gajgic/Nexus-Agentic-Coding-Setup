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

db.init_db()  # idempotent — the gate may run before the service migrated new columns

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
    ok("smart/high-stakes on a pinned LIGHT model caps at medium (never xhigh burn)",
       eff({"spend_profile": "smart", "deliverable_type": "content",
            "high_stakes": 0}, "glm-4.5-air") == "medium"
       and eff({"spend_profile": "optimal", "deliverable_type": None,
                "high_stakes": 1}, "glm-4.5-air") == "medium")
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
    # a None effort on a REUSED session clears the stale published one
    # (turn-cut park → mode switch → resume must not keep the old tier's effort)
    hd_mod.publish_session_effort(sid_probe, {"spend_profile": "optimal",
                                              "deliverable_type": "analysis",
                                              "high_stakes": 0}, "glm-5.2")
    data = json.load(open(os.path.expanduser("~/.hermes/session-keys.json")))
    entry = (data.get("sessions") or {}).get(sid_probe) or {}
    ok("stale effort cleared on mode switch (api_key survives)",
       "effort" not in entry and entry.get("api_key") == "probe-key", str(entry))
    hd_mod.remove_session_key(sid_probe)

    # ── 5. retry slice honors the per-type baseline × slice fraction ──
    print("=== I-1b: retry budget slice per type (0.5× original, 2026-07-13) ===")
    t6 = mk(model=None, judge_verdict=None, tokens_used=2_500_000, budget_tokens=None)
    srv._retry_task(t6, "probe feedback")
    row6 = db.query_one("SELECT budget_tokens, budget_original FROM tasks WHERE id=?", (t6,))
    ok("NULL-budget content task extends by HALF the 2M content baseline (used+1M)",
       row6["budget_tokens"] == 3_500_000, str(dict(row6)))
    ok("first retry pins budget_original to the type baseline",
       row6["budget_original"] == 2_000_000, str(row6["budget_original"]))
    # ceiling: past rework_ceiling_mult × original the retry files ONE budget
    # card instead of extending
    t6b = mk(model=None, judge_verdict=None, tokens_used=4_100_000,
             budget_tokens=4_000_000, budget_original=2_000_000)
    srv._retry_task(t6b, "probe feedback")
    row6b = db.query_one("SELECT budget_tokens FROM tasks WHERE id=?", (t6b,))
    card = db.query_one(
        "SELECT id FROM approvals WHERE status='pending' AND action_type='budget' "
        "AND payload LIKE ?", (f'%"task_id": "{t6b}"%',))
    ok("at the 2× ceiling: budget NOT extended", row6b["budget_tokens"] == 4_000_000,
       str(row6b["budget_tokens"]))
    ok("at the 2× ceiling: ONE pending 'budget' decision card filed", bool(card))
    srv._retry_task(t6b, "probe feedback again")
    n_cards = db.query_one(
        "SELECT COUNT(*) AS n FROM approvals WHERE status='pending' AND "
        "action_type='budget' AND payload LIKE ?", (f'%"task_id": "{t6b}"%',))["n"]
    ok("budget card is idempotent (second retry files no duplicate)", n_cards == 1)

    # ── 6. derive matrix (2026-07-13 mode-ladder) ──
    print("=== mode ladder: derive() matrix ===")
    d_eco = ap.derive("assisted", "eco")
    d_opt = ap.derive("assisted", "optimal")
    d_sm = ap.derive("full_auto", "smart")
    ok("judge_scope: eco=high_stakes / optimal=sinks / smart=all_quality",
       d_eco["judge_scope"] == "high_stakes" and d_opt["judge_scope"] == "sinks"
       and d_sm["judge_scope"] == "all_quality",
       f"{d_eco['judge_scope']}/{d_opt['judge_scope']}/{d_sm['judge_scope']}")
    ok("assisted sr_mode=closed (terminal checkpoints only), manual stays open",
       d_opt["sr_mode"] == "closed" and ap.derive("manual", "optimal")["sr_mode"] == "open")
    ok("escalation thresholds derive (armed): eco off / optimal rewrite / smart rewrite_or_cap",
       d_eco.get("escalation") == "off" and d_opt.get("escalation") == "rewrite"
       and d_sm.get("escalation") == "rewrite_or_cap",
       f"{d_eco.get('escalation')}/{d_opt.get('escalation')}/{d_sm.get('escalation')}")
    ok("plan_recommend derives (dead deep_plan.enabled key fixed)",
       d_opt.get("plan_recommend") == "triage" and d_sm.get("plan_recommend") == "always",
       f"{d_opt.get('plan_recommend')}/{d_sm.get('plan_recommend')}")

    # ── 7. judge tier + sink + frontier cost cap (loop engine) ──
    print("=== mode ladder: _judge_tier / _is_sink / cost cap ===")
    import loop_engine as le
    saved["judge.screen"] = db.get_setting("judge.screen")
    saved["frontier.task_cost_cap_usd"] = db.get_setting("frontier.task_cost_cap_usd")
    db.set_setting("judge.screen", "interior")
    wf_probe = f"wf-{uuid.uuid4().hex[:8]}"
    db.execute("INSERT INTO workflows (id, name, status, created_at, updated_at, user_id) "
               "VALUES (?,?,?,?,?,?)",
               (wf_probe, "probe wf", "active", time.time(), time.time(), "u_owner"))
    t_int = mk(judge_verdict=None, workflow_id=wf_probe, spend_profile="optimal")
    t_snk = mk(judge_verdict=None, workflow_id=wf_probe, spend_profile="optimal",
               depends_on=json.dumps([t_int]))
    ok("_is_sink: member with a dependent is interior, last member is the sink",
       not le._is_sink(db.query_one("SELECT * FROM tasks WHERE id=?", (t_int,)))
       and le._is_sink(db.query_one("SELECT * FROM tasks WHERE id=?", (t_snk,))))
    row_int = db.query_one("SELECT * FROM tasks WHERE id=?", (t_int,))
    row_snk = db.query_one("SELECT * FROM tasks WHERE id=?", (t_snk,))
    ok("optimal: interior member → screen, sink → frontier",
       le._judge_tier(row_int, "high_stakes") == "screen"
       and le._judge_tier(row_snk, "high_stakes") == "frontier",
       f"{le._judge_tier(row_int, 'high_stakes')}/{le._judge_tier(row_snk, 'high_stakes')}")
    ok("high-stakes forces frontier on any profile (rule-2 floor)",
       le._judge_tier({**row_int, "high_stakes": 1}, "high_stakes") == "frontier")
    ok("eco → none; smart → frontier",
       le._judge_tier({**row_int, "spend_profile": "eco"}, "high_stakes") == "none"
       and le._judge_tier({**row_int, "spend_profile": "smart"}, "high_stakes") == "frontier")
    db.set_setting("judge.screen", "off")
    ok("judge.screen=off: interior member gets no verdict tier",
       le._judge_tier(db.query_one("SELECT * FROM tasks WHERE id=?", (t_int,)),
                      "high_stakes") == "none")
    db.set_setting("judge.screen", "interior")
    ok("profile-less task follows judge.auto_scope ('sinks' screens interiors, "
       "'all_quality' fronts everything)",
       le._judge_tier({**row_int, "spend_profile": None}, "sinks") == "screen"
       and le._judge_tier({**row_int, "spend_profile": None}, "all_quality") == "frontier"
       and le._judge_tier({**row_int, "spend_profile": None}, "high_stakes") == "none")
    db.set_setting("frontier.task_cost_cap_usd", "3.0")
    ok("frontier cost cap scales with the profile multiplier",
       le._frontier_cost_capped({"spend_profile": "optimal", "frontier_cost_usd": 3.1})
       and not le._frontier_cost_capped({"spend_profile": "optimal", "frontier_cost_usd": 2.9})
       and not le._frontier_cost_capped({"spend_profile": "smart", "frontier_cost_usd": 5.9})
       and le._frontier_cost_capped({"spend_profile": "eco", "frontier_cost_usd": 1.6}))
    db.set_setting("frontier.task_cost_cap_usd", "0")
    ok("cost cap 0 = uncapped",
       not le._frontier_cost_capped({"spend_profile": "optimal", "frontier_cost_usd": 99.0}))
    db.execute("DELETE FROM workflows WHERE id=?", (wf_probe,))

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
