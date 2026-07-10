"""NEXUS Agent OS — Quality Autopilot presets (Q7a, two orthogonal axes).

Presets SET the existing knobs; they never replace them. Two axes:

  Involvement ("How much should I ask you?"): full_auto | assisted | manual
  Spend       ("How much should this cost?"): eco | optimal | smart

derive() maps the two axes to the concrete flags the rest of the system already
understands (loop preference/mode, auto-judge scope, Super Result on/off/open/
closed, fan-out width, round caps, budget multiplier, pipeline depth), honouring
the binding guardrail rules (QUALITY-AUTOPILOT-PLAN Part 2 §Q7a):

  rule 1  spend ABSORBS loop_config.preference (eco→speed, else quality)
  rule 2  risk is an INDEPENDENT HARD FLOOR the presets cannot bypass
  rule 3  eco ships STAGED — the model-tier floor lands with C2 (Phase 7)
  rule 4  budget × 0.5 / 1 / 2
  rule 5  spend shapes pipeline DEPTH (eco collapse / optimal std / smart full)
  rule 6  smart round cap = 3
  rule 8  adaptive early-exit inside optimal (P6: prompt-level, not DAG surgery) —
          realized by the SHIP quiet-stop + the reconciler framing, NOT a derived
          flag; derive() emits no early-exit field (see the rule-8 note below)
  P2      plan.recommend / escalation / model-floor are forward-deps → 'staged'
"""
INVOLVEMENTS = ("full_auto", "assisted", "manual")
SPEND_PROFILES = ("eco", "optimal", "smart")

INVOLVEMENT_DEFAULT = "assisted"
SPEND_DEFAULT = "optimal"

# Plain-language house labels (Q7c metaphors travel with the presets).
INVOLVEMENT_LABELS = {
    "full_auto": "🚀 Full Auto",
    "assisted": "🤝 Assisted",
    "manual": "🎛 Manual",
}
SPEND_LABELS = {"eco": "🌱 Eco", "optimal": "⚖ Balanced", "smart": "🧠 Smart"}


def norm_involvement(v) -> str:
    v = (v or "").strip()
    return v if v in INVOLVEMENTS else INVOLVEMENT_DEFAULT


def norm_spend(v) -> str:
    v = (v or "").strip()
    return v if v in SPEND_PROFILES else SPEND_DEFAULT


def _feature_present(name: str) -> bool:
    """P2: the profile→knob derivations for forward features are gated behind a
    feature-present check — at Phase 3 they derive nothing and report 'staged'."""
    try:
        import database as db
        if name == "deep_plan":
            return db.get_setting("deep_plan.enabled", "") == "1"
        if name == "escalation":
            return db.get_setting("super.escalation", "") == "1"
        if name == "model_floor":
            # C2 (registry-only roles / executor_light) — not seeded until Phase 7
            return "executor_light" in (db.MODEL_PURPOSES or ())
    except Exception:
        return False
    return False


def derive(involvement, spend, *, high_stakes: bool = False,
           base_budget: int | None = None) -> dict:
    """The single source of truth mapping (involvement, spend) → knobs. Pure and
    deterministic; consumers pick the fields they need. Risk (high_stakes) is an
    independent hard floor applied here so no preset can silently skip it."""
    inv = norm_involvement(involvement)
    sp = norm_spend(spend)

    # rule 1 — preference is derived from spend, never independently editable.
    preference = "speed" if sp == "eco" else "quality"

    # involvement → loop mode + Super Result rework mode.
    if inv == "manual":
        mode, sr_mode = "open", "open"
    elif inv == "assisted":
        mode, sr_mode = "closed", "open"      # closed fix-rounds, SR checkpoints wait
    else:  # full_auto
        mode, sr_mode = "closed", "closed"

    # spend → Super Result. None = triage-routed (caller keeps the explicit choice).
    super_result = {"eco": False, "optimal": None, "smart": True}[sp]

    # spend → fan-out width. None = triage-routed 0..super.fanout_n; "max" = full.
    fanout = {"eco": 0, "optimal": None, "smart": "max"}[sp]

    # spend → round cap. rule 6: smart = 3; optimal 2–3 by stakes; eco 1.
    if sp == "eco":
        round_cap = 1
    elif sp == "smart":
        round_cap = 3
    else:
        round_cap = 3 if high_stakes else 2

    # spend → auto-judge scope (feeds judge.auto_scope semantics).
    judge_scope = {"eco": "high_stakes", "optimal": "all_quality", "smart": "all_quality"}[sp]

    # rule 4 — budget multiplier is the hard cost backstop; move it with the profile.
    budget_mult = {"eco": 0.5, "optimal": 1.0, "smart": 2.0}[sp]
    budget = int(base_budget * budget_mult) if base_budget else None

    # rule 5 — spend shapes pipeline DEPTH (consumed by the wizard).
    pipeline_depth = {"eco": "collapsed", "optimal": "standard", "smart": "full"}[sp]

    # rule 8 / P6 — adaptive early-exit is NOT a derived preset flag. A boolean
    # consumed nowhere would be theatre; instead early-exit is realized
    # UNCONDITIONALLY (for Optimal/Smart fan-out + SR alike) by two mechanisms
    # that live where the work actually runs:
    #   P6(a) SHIP quiet-stop — loop_engine._sweep_super_result ends the SR loop
    #         on a SHIP verdict, skipping the residual polish round;
    #   P6(b) reconciler framing — server._reconciler_gate_task instructs the
    #         reconciler to compute agreement FIRST and adversarially re-verify
    #         only the DISAGREEMENTS ("rule 8 early-exit").
    # So derive() emits no early-exit field (the old boolean was removed after the
    # 2nd judge pass — it was dead). design_loop surfaces P6(a) as "Stops on SHIP".

    out = {
        "involvement": inv,
        "spend_profile": sp,
        "preference": preference,          # rule 1
        "mode": mode,
        "sr_mode": sr_mode,
        "super_result": super_result,      # True/False/None(triage)
        "fanout": fanout,                  # 0/"max"/None(triage)
        "round_cap": round_cap,            # rule 6
        "judge_scope": judge_scope,
        "budget": budget,                  # rule 4
        "budget_mult": budget_mult,
        "pipeline_depth": pipeline_depth,  # rule 5
        # rule 8/P6 early-exit is realized elsewhere (see the note above) — no field
        "checkpoints_only_at": (
            ["plan approval", "final deliverable", "escalations", "irreversible actions"]
            if inv == "full_auto" else None),
        # rule 2 — risk hard floor (informational; enforced at the loop/finalize
        # layer regardless of the preset): high-stakes always judges + gates.
        "risk_floor": {"forces_judge": bool(high_stakes), "forces_final_approval": bool(high_stakes)},
        # P2 — forward-dependency derivations, gated behind feature-present.
        "staged": {},
    }

    # P2 staged: plan recommendation (Deep Plan, Phase 5).
    if _feature_present("deep_plan"):
        out["plan_recommend"] = {"eco": "never", "optimal": "triage", "smart": "always"}[sp]
    else:
        out["staged"]["plan_recommend"] = "Deep Plan (Phase 5) not present — not derived"

    # P2 staged: escalation ladder (C1c, Phase 7).
    if _feature_present("escalation"):
        out["escalation"] = {"eco": "off", "optimal": "rewrite", "smart": "rewrite_or_cap"}[sp]
    else:
        out["staged"]["escalation"] = "Escalation ladder (Phase 7) not present — not derived"

    # rule 3 / P2 staged: eco's cheapest-capable model floor (C2, Phase 7).
    if _feature_present("model_floor"):
        out["model_floor"] = {"eco": "executor_light", "optimal": None, "smart": None}[sp]
    else:
        out["staged"]["model_floor"] = ("Eco model-tier floor (C2, Phase 7) not present — "
                                        "Eco runs via rounds/SR/fan-out/judge knobs only")
    return out


def plain_summary(involvement, spend) -> str:
    """One-line plain-language description for cards / JARVIS speech (Q7c)."""
    inv = norm_involvement(involvement)
    sp = norm_spend(spend)
    inv_txt = {
        "full_auto": "I run the loops and only ask you at the big moments",
        "assisted": "I close the fix-rounds but pause for your eyes on the inspector",
        "manual": "I only flag and recommend — you drive every step",
    }[inv]
    sp_txt = {
        "eco": "cheapest that still works",
        "optimal": "balanced — best result per fuel",
        "smart": "spare no fuel — maximum checking",
    }[sp]
    return f"{INVOLVEMENT_LABELS[inv]}: {inv_txt}. {SPEND_LABELS[sp]}: {sp_txt}."
