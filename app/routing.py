"""NEXUS Agent OS — routing telemetry + learned parameters (L1 + L4 + rule 9).

L1: every task logs (routing decision → actual outcome) at its terminal state.
    A deterministic monthly / per-100-tasks stats job (NO LLM) compares triage
    predictions with outcomes and proposes threshold adjustments as a Decisions
    card — continuous router learning between benchmark campaigns, at zero model
    cost. It also runs the rule-9 router-collapse monitor.

L4: tuned thresholds are model-specific — stored WITH the config fingerprint and
    auto-invalidated on tier rotation (revert to heuristic defaults). Distilled
    craft lessons live in ~/knowledge and survive rotations. Two stores.

Autonomy ceiling (binding): collection + analysis + proposal are autonomous;
every WRITE that changes routing behaviour goes through the Decisions approval.
"""
import json
import time
import uuid
import hashlib

import auth
import database as db

STATS_EVERY_TASKS = 100  # or monthly, whichever comes first


# ─────────────────────────── L4 — fingerprint-tagged params ───────────────────────────

def config_fingerprint(user_id: str | None = None) -> str:
    """Short hash of the TIER configuration that tuned thresholds depend on —
    the model ids assigned to the judgment + bulk purposes. Rotating a tier
    changes this, which auto-invalidates every learned threshold (L4)."""
    parts = []
    # C2/L4 (Phase 7): the fingerprint spans EVERY purpose whose model can shape a
    # tuned threshold — including the spec_model + escalation_model judgment tiers
    # added in Appendix C. Rotating any of them invalidates the learned params
    # (e.g. escalation thresholds Phase 8 tunes) back to the heuristic defaults.
    for purpose in ("frontier_judge", "complicated", "easy", "mechanical",
                    "spec_model", "escalation_model"):
        try:
            row = db.resolve_assignment(user_id, purpose)
            parts.append(f"{purpose}={row['model_id'] if row else '-'}")
        except Exception:
            parts.append(f"{purpose}=?")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


def learned_param(key: str, default=None):
    """A tuned threshold ONLY if it was learned under the CURRENT tier config;
    otherwise the heuristic default (L4 invalidation on rotation)."""
    row = db.query_one("SELECT value, fingerprint FROM learned_params WHERE key=?", (key,))
    if not row:
        return default
    if row.get("fingerprint") != config_fingerprint():
        return default  # stale for this tier — fall back to heuristic
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def set_learned_param(key: str, value):
    db.execute(
        "INSERT OR REPLACE INTO learned_params (key, value, fingerprint, updated_at) "
        "VALUES (?,?,?,?)", (key, json.dumps(value), config_fingerprint(), time.time()))


# ─────────────────────────── L1 — outcome capture ───────────────────────────

def _effective_loop_cfg(task: dict) -> dict:
    try:
        if task.get("loop_config"):
            return json.loads(task["loop_config"]) or {}
        if task.get("workflow_id"):
            w = db.query_one("SELECT loop_config FROM workflows WHERE id=?", (task["workflow_id"],))
            if w and w.get("loop_config"):
                return json.loads(w["loop_config"]) or {}
    except Exception:
        pass
    return {}


def _rounds_used(cfg: dict, task_id: str) -> int:
    total = 0
    for t in cfg.get("triggers") or []:
        total += int(t.get("used") or 0)
        total += int((t.get("used_tasks") or {}).get(task_id) or 0)
    return total


def record_outcome(task_id: str):
    """Upsert this task's routing outcome at a terminal state (deterministic, no
    LLM). Idempotent — the row keeps refining as later transitions land."""
    t = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
    if not t:
        return
    cfg = _effective_loop_cfg(t)
    # fan-out: this task's project ran >=2 parallel investigators/drafts
    fanout = 0
    if t.get("workflow_id"):
        sibs = db.query_all("SELECT tags FROM tasks WHERE workflow_id=?", (t["workflow_id"],))
        n = sum(1 for s in sibs if {"fanout", "investigation", "draft"}
                & set(_tags(s.get("tags"))))
        fanout = 1 if n >= 2 else 0
    # escalated / overridden read straight from the approvals ledger
    esc = db.query_one(
        "SELECT 1 FROM approvals WHERE action_type='super_result' AND payload LIKE ? "
        "AND payload LIKE '%\"reason\"%'", (f'%"task_id": "{task_id}"%',))
    ovr = db.query_one(
        "SELECT 1 FROM approvals WHERE status='rejected' AND payload LIKE ?",
        (f'%"task_id": "{task_id}"%',))
    triage = {"domain": t.get("domain"), "high_stakes": bool(t.get("high_stakes")),
              "super_result": bool(t.get("super_result")),
              "deliverable_type": t.get("deliverable_type")}
    verdicts = {"judge": t.get("judge_verdict"), "critic": t.get("critic_verdict")}
    db.execute(
        "INSERT OR REPLACE INTO routing_outcomes (id, task_id, user_id, triage_json, "
        "spend_profile, autopilot, rounds_used, fanout_used, final_verdicts, escalated, "
        "overridden, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"ro-{task_id}", task_id, t.get("user_id"), json.dumps(triage),
         t.get("spend_profile"), t.get("autopilot"), _rounds_used(cfg, task_id), fanout,
         json.dumps(verdicts), 1 if esc else 0, 1 if ovr else 0, time.time()))


def _tags(raw):
    try:
        return json.loads(raw or "[]")
    except Exception:
        return []


# ─────────────────────────── L1 stats job + rule-9 collapse monitor ───────────────────────────

def sweep_stats():
    """Deterministic (NO LLM) routing statistics — runs at most once per
    STATS_EVERY_TASKS new outcomes. Proposes threshold adjustments as an
    admin Decisions card, and runs the router-collapse monitor (rule 9)."""
    total = db.query_one("SELECT COUNT(*) AS n FROM routing_outcomes") or {}
    n = int(total.get("n") or 0)
    last = int(db.get_setting("routing.stats_last_n", "0") or 0)
    if n - last < STATS_EVERY_TASKS:
        return
    db.set_setting("routing.stats_last_n", n)
    proposals, reasons = [], []

    # (a) triage sensitivity: 'simple' (eco/no-SR) goals that still needed >=2
    # rework rounds suggest the triage under-provisions.
    simple = db.query_all(
        "SELECT rounds_used FROM routing_outcomes WHERE (spend_profile='eco' OR spend_profile IS NULL)")
    if simple:
        heavy = sum(1 for r in simple if int(r.get("rounds_used") or 0) >= 2)
        if heavy and heavy / len(simple) >= 0.5:
            proposals.append("raise triage sensitivity (more work routed to Balanced/Smart)")
            reasons.append(f"{heavy} of {len(simple)} low-spend goals needed ≥2 rework rounds")

    # (b) rule 9 — router collapse: Optimal saturating to the max-spend path.
    opt = db.query_all("SELECT fanout_used, rounds_used FROM routing_outcomes WHERE spend_profile='optimal'")
    if opt and len(opt) >= 10:
        maxed = sum(1 for r in opt if int(r.get("fanout_used") or 0) == 1 and int(r.get("rounds_used") or 0) >= 3)
        if maxed / len(opt) >= 0.8:
            db.log_activity("warn", "routing",
                            f"ROUTER COLLAPSE WARNING: {maxed}/{len(opt)} 'Balanced' tasks "
                            "saturated to the max-spend path (fan-out + full rounds). Cost "
                            "dashboards without quality-per-route are misleading — the Phase 8 "
                            "campaign adds the quality side.")
            reasons.append(f"router collapse: {maxed}/{len(opt)} Balanced tasks ran max-spend")
            proposals.append("investigate Balanced routing saturation (rule 9)")

    # (c) escalation frequency signal
    esc = db.query_one("SELECT COUNT(*) AS e FROM routing_outcomes WHERE escalated=1") or {}
    if int(esc.get("e") or 0) and n:
        rate = int(esc["e"]) / n
        if rate >= 0.3:
            reasons.append(f"{int(esc['e'])} of {n} tasks escalated to a human ({rate:.0%})")
            proposals.append("review escalation thresholds — escalation rate is high")

    if not proposals:
        db.log_activity("info", "routing",
                        f"Routing stats over {n} outcomes: no threshold change proposed")
        return
    payload = {
        "headline": f"Routing review over {n} completed tasks — {len(proposals)} suggestion(s).",
        "recommendation": "Review the routing suggestions",
        "reasons": reasons[:3],
        "cost_hint": "these are heuristic proposals — measured tuning happens in the benchmark phase",
        "proposals": proposals, "sample": n,
    }
    db.execute(
        "INSERT INTO approvals (id, agent_id, action_type, description, payload, status, "
        "risk_level, requested_at, user_id, scope) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (f"appr-{uuid.uuid4().hex[:10]}", "routing-stats", "routing_tuning",
         f"Routing review: {len(proposals)} threshold suggestion(s) from {n} tasks",
         json.dumps(payload), "pending", "low", time.time(),
         auth.DEFAULT_USER_ID, "admin"))  # [15]
    db.log_activity("info", "routing",
                    f"Filed a routing-tuning Decisions card ({len(proposals)} proposals)")
