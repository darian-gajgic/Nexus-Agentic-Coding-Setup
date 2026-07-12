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


# ─────────────────── Item 15 — description-informed model routing ───────────────────
# Deterministic (NO LLM at task-create time — house doctrine): a base tier from
# the same keyword heuristics the wizard's guidance describes, then an override
# when a registry model's operator-maintained description ("Best for: …")
# clearly matches the task text. Explainable: the reason is stored on the task.

# Keep in sync with server._DEV_SPECIALISTS — dev pipeline stages have a fixed
# model floor (glm-5.2 via _repair_workflow) that routing must never touch.
_DEV_SPECIALISTS = {"tech-lead-orchestrator", "code-implementer", "code-reviewer",
                    "debugger", "acceptance-verifier"}
_MECHANICAL_RE = None  # compiled lazily


def _significant_tokens(s: str) -> set:
    import re as _re
    stop = {"the", "and", "for", "with", "from", "that", "this", "into", "your",
            "our", "their", "task", "create", "make", "write", "please"}
    return {w for w in _re.findall(r"[a-z0-9]{3,}", (s or "").lower()) if w not in stop}


def _parse_capability_lines(description: str) -> tuple[list[str], list[str]]:
    """(best_for phrases, avoid_for phrases) from the structured description
    shape ('Best for: a; b; c'). Freeform prose yields nothing → no override."""
    best, avoid = [], []
    for line in (description or "").splitlines():
        low = line.strip().lower()
        if low.startswith("best for:"):
            best = [p.strip() for p in line.split(":", 1)[1].split(";") if p.strip()]
        elif low.startswith("avoid for:"):
            avoid = [p.strip() for p in line.split(":", 1)[1].split(";") if p.strip()]
    return best, avoid


def _phrase_matches(phrase: str, task_toks: set) -> bool:
    ptoks = _significant_tokens(phrase)
    if not ptoks:
        return False
    hit = len([t for t in ptoks if t in task_toks])
    return hit / len(ptoks) >= 0.6


def select_model_for_task(task: dict, uid: str | None) -> tuple[str | None, str | None]:
    """(model_id, plain-language reason) or (None, None) = leave NULL (the
    dispatch default). Explicit human/wizard model choices always win upstream;
    dev-pipeline specialists are skipped (their floor is authoritative);
    high-stakes tasks are never routed below the 'complicated' default."""
    import re as _re
    global _MECHANICAL_RE
    if db.get_setting("models.auto_route", "1") != "1":
        return None, None
    if task.get("model"):
        return None, None
    if (task.get("specialist") or "") in _DEV_SPECIALISTS:
        return None, None
    title = str(task.get("title") or "")
    desc = str(task.get("description") or "")
    text = f"{title} {desc}"
    allowed = set(db.task_models_for(uid))
    default_hard = db.default_task_model(uid)

    if _MECHANICAL_RE is None:
        _MECHANICAL_RE = _re.compile(
            r"\b(format|convert|extract|rename|transcrib\w*|csv|cleanup|dedup\w*|"
            r"reformat|normali[sz]e)\b", _re.I)
    base_purpose = "complicated"
    if not task.get("high_stakes"):
        if _MECHANICAL_RE.search(text):
            base_purpose = "mechanical"
        elif len(text.strip()) < 160 and (task.get("domain") or "general") == "general":
            base_purpose = "easy"
    base_row = db.resolve_assignment(uid, base_purpose)
    base_model = (base_row or {}).get("model_id")
    base_reason = None
    if base_purpose == "mechanical" and base_model:
        kw = _MECHANICAL_RE.search(text).group(0)
        base_reason = (f"auto-routed to {base_model}: the task looks mechanical "
                       f"(\"{kw}\") — change the model on the task to override")
    elif base_purpose == "easy" and base_model:
        base_reason = (f"auto-routed to {base_model}: short, simple brief with no "
                       "domain — change the model on the task to override")

    # Description override: score every enabled hermes model's "Best for"
    # phrases against the task text; any "Avoid for" match vetoes the model.
    task_toks = _significant_tokens(text) | _significant_tokens(task.get("domain") or "") \
        | _significant_tokens(task.get("deliverable_type") or "")
    best_model, best_score, best_phrase = None, 0, ""
    for m in db.visible_models(uid, enabled_only=True):
        if m.get("route") != "hermes" or not (m.get("description") or "").strip():
            continue
        if m["model_id"] not in allowed:
            continue
        best_for, avoid_for = _parse_capability_lines(m["description"])
        if any(_phrase_matches(p, task_toks) for p in avoid_for):
            continue
        hits = [p for p in best_for if _phrase_matches(p, task_toks)]
        if len(hits) > best_score:
            best_model, best_score, best_phrase = m["model_id"], len(hits), hits[0]
    if best_model and best_score >= 1:
        # High-stakes work may only route to the default 'complicated' model or
        # a description-matched model that IS that default — never downgraded.
        if task.get("high_stakes") and best_model != default_hard:
            return None, None
        if best_model != (base_model or default_hard):
            return best_model, (f"auto-routed to {best_model}: its description lists "
                                f"\"{best_phrase}\" under Best for, matching this task — "
                                "change the model on the task to override")
    if base_purpose != "complicated" and base_model and base_model in allowed:
        return base_model, base_reason
    return None, None
