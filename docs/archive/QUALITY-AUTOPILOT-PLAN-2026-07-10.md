# QUALITY AUTOPILOT — compounding quality levers + full automation & decision cockpit

**Status:** APPROVED DESIGN, NOT IMPLEMENTED. Execute in a dedicated session (or ride items with the N5–N8 batch as noted).
**Date:** 2026-07-10
**Author:** Claude Fable 5 (frontier side).
**Relationship:** third plan in the series — assumes `SUPER-RESULT-PLAN-2026-07-09.md` (implemented; 2 REVISE blockers pending) and `DEEP-PLAN-MODE-PLAN-2026-07-10.md` (planned). Shares the tier principle (judgment tier = Opus 4.8; Fable 5 = reference only, never a component).
**Operator decisions recorded:** (1) all six quality levers approved for spec; (2) maximize automation, and where a human IS needed, present the decision so it takes seconds, explained so a user with NO AI knowledge can operate the system; (3) **benchmarks are deferred** — C4 harness, Step 11, and any measurement-driven tuning run AFTER these implementations land, to save tokens now. Recorded consequence: these features ship unmeasured at first; the final benchmark phase validates them all at once and anything that doesn't pay gets reverted then.
**For the implementing session:** anchors are symbol names (post-SR offsets shifted — re-locate by symbol). Every step leaves `bash app/scripts/verify.sh` green; service restarts only via `systemctl --user restart nexus`; bump `?v=N` for app.js edits.

---

## Part 1 — The six quality levers (Q1–Q6)

### Q1 — Golden-exemplar retrieval (best quality-per-token for business deliverables)
Inject the operator's own best past work as few-shot exemplars.
- **Selection (deterministic SQL, no embeddings in v1):** at dispatch framing time, for judgeable domains with `deliverable_type` in (content, research, analysis): `SELECT` past tasks of the same `domain` (+ same `client` when set) with `judge_verdict='SHIP'` AND `rubric_score >= exemplars.min_score`, same `user_id`, order by `rubric_score DESC, completed_at DESC`, take `exemplars.max`. Union with curated `~/knowledge/domains/<d>/examples/*` (curated wins ties).
- **Injection (token-cheap):** in `build_framing` (hermes_dispatch.py, after the domain PLAYBOOK block): list exemplar deliverable PATHS as MUST-READ — "these are past deliverables rated excellent for this business; read them first; match their quality bar, voice, and depth; do NOT copy content." Paths only — the executor reads via file tools; framing grows by ~5 lines.
- **Guards:** never for `code_change` (repo context suffices); skip when the CURRENT task is a retry round (the feedback matters more than exemplars); exclude the current task's own earlier versions.
- **Settings:** `exemplars.enabled` (1), `exemplars.min_score` (3.5), `exemplars.max` (2).
- **Files:** `hermes_dispatch.py` (`build_framing`), `settings_registry.py`, verify.sh checks.

### Q2 — Operator-edit distillation (every human correction becomes permanent)
Extends the N8 distillation (Appendix A Tier 3 of the SR plan) with the strongest evidence source: what the operator actually changed.
- **Evidence collected per domain** (deterministic sweep, no LLM): (a) rejection feedback texts (`approvals` rejected + `retry_feedback` history), (b) `review_comments` with `source='user'`, (c) **the diff between a human-rejected version and the subsequently accepted one** — both exist on disk (`_history/vN` snapshots / `deliverable.vN.md`): compute a compact unified diff at accept time and store it in a new `edit_evidence` table (`id, task_id, domain, user_id, kind ('feedback'|'comment'|'accept_diff'), content TEXT ≤8000, created_at`).
- **Distillation job (this IS N8, upgraded):** scheduler-run (default weekly, or manual button) per domain with ≥`lessons.min_evidence` new items: ONE judgment-tier call — "here are the operator's corrections and the judges' learning notes for <domain>; propose ≤5 durable deltas to STYLE-VOICE / PLAYBOOK / RUBRIC, each with the evidence lines that justify it; sentinel-fenced JSON" → filed as ONE approval (`action_type='lesson_deltas'`) rendering each delta with before/after. On approve: apply to `~/knowledge` files (git-commit like onboarding apply); on reject with feedback: feedback itself becomes evidence.
- **Settings:** `lessons.auto_distill` (1), `lessons.min_evidence` (5), `lessons.cron` (weekly).
- **Files:** `database.py` (table), `server.py` (accept-diff capture in the approve path + apply endpoint), `scheduler.py` or loop-engine sweep hook, `evals.py`-style runner for the call, UI approval card.

### Q3 — Acceptance-tests-first for coding pipelines (buy the oracle once)
- **Template change** (`_task_wizard_framing`, SOFTWARE pipeline): the spec stage (judgment-tier per Appendix C1a once landed; GLM until then) MUST deliver `acceptance/` — executable acceptance tests + a `RUN.md` (exact commands) — derived from the acceptance criteria (Deep Plan spec when present). The implement stage is told: "the acceptance tests are the contract; make them pass; you may add tests but MUST NOT modify `acceptance/`."
- **Tamper guard (deterministic):** spec stage's `_dispatch.json`/deliverable records SHA-256 of each `acceptance/` file; the acceptance-verifier task description instructs verifying hashes first (files available via predecessor injection), then running `RUN.md` commands via the existing `/api/verify` runner; the SR critic sandbox re-runs them independently (it already copies the workspace).
- **`_repair_workflow`:** when a coding pipeline has a spec stage, append the acceptance-tests requirement to its description deterministically (same pattern as the review-gate insertion); verifier description gains the hash-check + run steps.
- **Settings:** `pipeline.tests_first` (1).
- **Files:** `server.py` (framing + repair), verify.sh; no schema changes.

### Q4 — Project decision log + running brief (coherence for ~zero tokens)
- **Executor contract (prompt-only):** workflow-member framing gains: "end your deliverable with a `## Decisions` section — every choice you made that later stages must respect (naming, structure, stack, tone), one line each with the reason."
- **Deterministic harvest (no LLM):** `_finalize_result` (hermes_dispatch.py) parses the `## Decisions` section and appends `### <task title> (<date>)` + the lines to `workspaces/workflow-<id>/DECISIONS.md`.
- **Injection:** `build_framing` adds DECISIONS.md as MUST-READ for every workflow member (before predecessor deliverables). Optional token saver: `framing.brief_mode` (0 default) — when 1, tasks ≥3 steps downstream get DECISIONS.md + only their DIRECT predecessors' deliverables instead of all of them.
- **Files:** `hermes_dispatch.py` (framing + finalize), `settings_registry.py`.

### Q5 — Uncertainty tagging (prompt-only, focuses the critique budget)
- **Executor framing:** "mark every claim you could not verify against a primary source inline as `[UNSURE: reason]` — unmarked claims are treated as verified assertions."
- **Critic (`cverify` prompt):** "verify `[UNSURE]` claims FIRST; an unmarked claim that proves false is a `critical` finding; a marked one is `medium`." Same line in cjudge + a note in the INVESTIGATION rubric (A1 interacts: marked inference ≠ A1 violation, unmarked is).
- **UI:** highlight `[UNSURE: …]` spans in deliverable previews (regex wrap in the markdown renderer, styled amber).
- **Files:** `hermes_dispatch.py`, `setup/bin/cverify` + `~/.local/bin/cverify`, `setup/bin/cjudge` + live copy, `~/knowledge/rubrics/INVESTIGATION.md`, `app.js` preview renderer.

### Q6 — Prompt lab: GEPA-style optimization of the system's own prompts (RUN LAST — needs eval spend)
- **Scope v1 = knowledge artifacts only** (PLAYBOOK / RUBRIC / STYLE-VOICE / specialist definitions — they're files with an existing eval fingerprint), NOT code-side framing strings.
- **Loop (manual trigger only, given the token-saving decision):** "Optimize <domain>" button → judgment-tier call reads the artifact + recent judge outputs + Q2 evidence → proposes ONE candidate edit → eval runner executes the domain's corpus subset under the candidate (the runner + fingerprinting already exist) → score delta shown → operator approves (git-commit) or discards. No autonomous loop in v1 — each iteration is operator-triggered because each costs a full eval run (~8 gen+judge calls).
- **Files:** `evals.py` (candidate-run mode: temporary knowledge overlay dir via `onboarding.root`-style override), `server.py` endpoint, Specialists→Evals tab button.
- **Sequencing note:** this is the ONE lever that consumes meaningful tokens per use — schedule it with the deferred benchmark phase.

### Learning-loop completeness (audit 2026-07-10 — binding additions)
The levers above must form a CLOSED learning system. Four additions:
- **L1 — Outcome-driven routing tuning (new, fold into Q7/C5; the biggest gap).** Every task logs `(triage signals, profile, rounds used, fan-out fired?, verdicts, escalated?, operator override?)` — a deterministic statistics job (NO LLM calls; scheduler-run monthly or per 100 tasks) compares triage predictions with actual outcomes and proposes threshold adjustments as a Decisions-inbox card (e.g. "34 of 41 'simple' goals needed ≥2 SR rounds — raise triage sensitivity?"). Continuous router learning between benchmark campaigns, at zero model cost.
- **L2 — Per-user vs shared lesson targeting (extend Q2).** Distilled deltas are classified: user-specific taste → that user's knowledge OVERLAY (onboarding already has owner-canonical vs member-overlay); universal craft lessons → canonical, admin-approved. Cross-user sharing = an admin Decisions card ("apply this lesson for all users?") — implements the operator's standing wish to review and share lessons between users.
- **L3 — Exemplar lifecycle (extend Q1).** Keep top-K per domain (K=`exemplars.max`×3 pool); re-score candidates when the domain RUBRIC changes (fingerprint delta); age out exemplars older than N months unless re-confirmed. Prevents stale "excellence" from anchoring new work.
- **L4 — Fingerprint-tag learned parameters (extend C2/C4).** Tuned thresholds (triage, escalation, profile boundaries) are MODEL-SPECIFIC → stored with the config fingerprint and auto-invalidated on tier rotation (revert to heuristic defaults until re-tuned). Distilled lessons/playbook deltas are CRAFT knowledge → survive rotations. Two stores, never mixed.
- **Autonomy ceiling (binding):** collection, analysis, and proposal are fully autonomous; every WRITE that changes system behavior (knowledge files, thresholds, routing) requires the one-click Decisions-inbox approval. No unsupervised self-modification — the self-critique evidence applies to a system editing its own prompts too.

## Part 2 — Autopilot & the Decision Cockpit (Q7)

Goal: the system drives itself; the human sees ONE inbox of decisions, each answerable in seconds; every concept is explained for a non-AI user.

### Q7a — Autopilot presets: TWO orthogonal axes (operator decision 2026-07-10: "Two axes")
The wizard/project/task UI presents **two rows of three plain-language radio cards** (pattern: `loopPrefCardsHTML`), defaults preselected so a beginner can ignore both; an "Advanced" expander below exposes every raw knob for professionals. Presets SET the existing knobs, they never replace them — any manual knob change flips the display to "customized (based on <preset>)".

**Axis 1 — Involvement ("How much should I ask you?"):**
- **🚀 Full Auto** — closed loops, auto-judge, auto-replan-draft (N6), checkpoints ONLY at: plan approval, final deliverable, escalations, anything irreversible.
- **🤝 Assisted (default)** — closed fix-rounds, but SR checkpoints in open mode (review auto-comments before re-runs), replan drafts wait for a click.
- **🎛 Manual** — everything open; the engine only detects and recommends.

**Axis 2 — Spending profile ("How much should this cost?"):**
| Knob | 🌱 Eco | ⚖ Optimal (default) | 🧠 Smart |
|---|---|---|---|
| Model routing | cheapest capable (executor-light where triage allows) | standard purposes | standard, escalation eager |
| Deep Plan recommendation | never | triage-routed | offered on everything non-trivial |
| Super Result | off unless user forces | triage-routed | on |
| Fan-out width | 0 | triage-routed 0–`super.fanout_n` | max |
| Loop round caps | 1 | 2–3 by stakes | max |
| Escalation (C1c, once landed) | off | REWRITE only | REWRITE or round-cap |
| Auto-judge scope | high-stakes only | quality-mode work | everything |
| Est. $/medium task (API-equiv) | ~$0.30–1.50 | ~$1–10 | ~$5–25 |

- **Honesty rule baked into the code comments + manual:** "Optimal = best result per $" is HEURISTIC (triage-routed per C5) until the deferred Phase 8 benchmark measures marginal quality per dollar; the C4 data then tunes Optimal's thresholds. Label it "balanced" in beginner-facing copy until measured.
- Implementation: `autopilot` + `spend_profile` fields (task/workflow, user-level default in settings `autopilot.default_involvement` / `autopilot.default_spend`); `design_loop`, the wizard, and the triage read BOTH to derive the existing flags (`mode`, `auto_judge`, SR on/off/open/closed, fan-out width, round caps, `plan.recommend`, `replan.auto_draft`, escalation setting, model-purpose floor). Cascade to member tasks mirrors `high_stakes`; per-item override allowed.
- **Files:** `database.py` (columns + settings seeds), `loop_engine.design_loop`, `server.py` wizard/create/triage paths, `app.js` (two card rows + Advanced expander).

**Coherence & guardrail rules (audit + SOTA research pass, 2026-07-10 — binding):**
1. **The spend profile ABSORBS `loop_config.preference` (quality|speed).** Three overlapping dials would defeat the beginner goal. `design_loop` derives preference from the profile (Eco→speed, Optimal/Smart→quality); the quality/speed radio cards in task-create/wizard/loop-modal are REPLACED by the profile cards (the derived value shows read-only under Advanced). Keep the `preference` field populated for backward compatibility — derived, never independently editable.
2. **Risk is an independent HARD FLOOR the profiles cannot bypass** (convergent industry standard: risk tiers gate on reversibility/blast-radius, enforced at the workflow layer regardless of what any preset says — MindStudio 4-tier, CSA autonomy levels). Concretely: `high_stakes` forces judge + final approval even under Eco; `autopilot.auto_approve_ship_hours` NEVER applies to high-stakes tasks or `super_result`/escalation approvals even in Full Auto; irreversible-action approvals (deploy/send/purchase) are untouched by both axes.
3. **Eco ships STAGED.** Its model-tier routing ("cheapest capable") depends on C2 registry-only roles, which lands in Phase 7 — Q7a v1 implements Eco via rounds/SR/fan-out/judge knobs only; the model-floor override completes in Phase 7 (note it in the Eco card's Advanced view until then).
4. **Profiles scale token budgets:** per-task default budget × 0.5 (Eco) / 1 (Optimal) / 2 (Smart) — budgets are the hard cost backstop and must move with the profile.
5. **Profiles shape pipeline DEPTH in the wizard**, not just loop knobs: Eco collapses the coding template to implement→verify (review gate re-inserted only when high_stakes — rule 2 wins); Optimal keeps the standard templates; Smart = full pipeline + fan-out. New framing param alongside the Step-7 fan-out block.
6. **Smart's round cap = 3 in v1** (matches the loop-modal UI clamp; the adaptive-compute literature shows steeply diminishing returns past ~3 verified rounds). Revisit only with Phase 8 data.
7. **Passthrough:** scheduler job templates (B4) and JARVIS-created tasks carry/respect both profile fields; Decisions-inbox cost hints become profile-aware ("another round ≈ $0.40 — within Optimal").
8. **Adaptive early-exit inside Optimal** (measured 50–70% savings at near-equal quality in the literature — Snell, Adaptive-Consistency): when fan-out investigators/drafts strongly agree (low divergence, the triage's own signal), the reconciler skips the extra adversarial round; when the SR critic's confidence is high and findings are empty, skip the residual polish round.
9. **Instrument against router collapse and silent quality regression** ("When Routing Collapses" 2602.03478; industry eval-gate practice): log per-profile spend distribution + route choices to the activity/observability feed; WARN when Optimal's routing saturates to the max-spend path; the manual states that cost dashboards without quality-per-route are misleading — the C4 campaign adds the quality side.
10. **Eco is validated BEHAVIORALLY in Phase 8**, not assumed: low-effort modes are documented (FutureSearch, Mar 2026) to reduce tool-call thoroughness and instruction-following, not just token count — "same answer, cheaper" must be proven per task family, or Eco's floor gets raised.
11. **Specialist sweep (executor-side teaching).** The 18 Hermes specialist definitions were written before the new executor contracts (`## Decisions` section, `[UNSURE]` tagging, "Done when" criteria, acceptance-tests-first, exemplar reading). Audit all 18 for conflicting output-format instructions and align them — a specialist prompt that fights the framing makes contract compliance model-mood-dependent. One task inside Phase 3; keep the guardian/vendored copies in sync per the ship-flow.
12. **JARVIS stays current — standing rule.** (a) JARVIS's chat framing becomes a proactive advisor: deliverable-shaped complex requests get a plain-language recommendation to route to the fleet with Deep Plan and a suggested spend profile, using the Q7c house metaphors (inspector/foreman) in speech. (b) EVERY implementation phase ends by updating the JARVIS system-control framing with the new endpoints/fields and re-running the JARVIS gates — the assistant that fronts the system must never be a phase behind it.

### Q7b — Decision Inbox (the single human surface)
- **New nav view "Decisions"** aggregating EVERY pending human action: approvals of all `action_type`s (deliverable, super_result, lesson_deltas, replan, escalations), each as a **decision card** with a fixed anatomy:
  1. **Headline** (1 sentence, plain language): "The audit report for X is ready — the independent inspector found 0 remaining problems after 2 fix rounds."
  2. **Recommendation** (★): the system's suggested action, stated as a button label — "★ Approve & ship".
  3. **Why (≤3 bullets, evidence-linked):** "verdict SHIP (confidence 0.9)" / "all 6 acceptance criteria verified" / "2 earlier findings fixed — view diff".
  4. **Options as buttons** with consequences: `★ Approve` / `Request changes (opens comment box, pre-filled with open findings)` / `Open details` (full review modal / plan editor — the existing deep surfaces).
  5. **Cost line** where relevant: "another fix round ≈ ~N tokens (~$x)".
- **Backend:** `GET /api/decisions` aggregates approvals + replan-needed + escalations, sorted blocking-first then age. **Every producer attaches `recommendation` + `reasons[]` + `cost_hint` into the approval payload at insert time** (loop engine escalations, SR checkpoints, replan detection, Q2 deltas, finalize) — a small addition at each of the ~6 insert sites; the card falls back gracefully when absent (legacy rows).
- One badge (replaces/absorbs the approvals badge), deck section reuses the cards, JARVIS briefing reads the blocking count + headlines (framing already documents approvals — extend to `/api/decisions`).
- **Auto-timeout is OFF by default** and only exists as `autopilot.auto_approve_ship_hours` (0=never): in Full Auto, a SHIP-verdict final approval may auto-approve after N hours — never for rejections, escalations, or anything irreversible.
- **Files:** `server.py` (endpoint + payload additions), `loop_engine.py` (payload additions), `app.js` (view + cards + badge), `index.html` (nav), JARVIS framing.

### Q7c — Plain-language layer (operate it without AI knowledge)
- **House metaphor, used EVERYWHERE consistently:** worker (executor) / **inspector** (critic — "independently re-checks the work against the real files") / **foreman** (loop engine — "sends work back until it passes") / **planner** (wizard/Deep Plan) / **you = the client** (decisions inbox). Every chip, modal, and card uses these words first, technical terms in parentheses.
- **"?" explainers:** every feature chip (SR round chip, judge/critic verdict, loop badge, autopilot preset, decision card) gets a hover/click explainer (pattern exists: `LOOP_INTRO_SHORT`, loop-modal flow diagrams) — 2–3 sentences, no jargon, always ending with "what should I do?" guidance.
- **Manual view rewrite** (`data-view="manual"` exists): a task-oriented guide — "Give the system work", "Read your Decisions inbox", "What the inspector does", "When to use Deep Plan / Super Result / Full Auto", "What things cost" — each section: one diagram (reuse the loop-modal flowBox pattern), one worked example, one FAQ. Written for a smart person who has never used an AI tool: no "LLM", "token" explained once ("tokens ≈ the system's fuel; more rounds = more fuel"), every button screenshot-referenced.
- **Wizard microcopy:** preset cards and the SR/Deep-Plan recommendation banners state cost and benefit in plain terms ("uses roughly 5–10× more fuel; worth it for work you'd pay a specialist to double-check").
- **Files:** `app.js` (manual view content, explainers), no backend.

## Part 3 — Sequencing (benchmarks deferred by operator decision)

1. **SR REVISE fixes** (2 blockers from the grounded review) — nothing else lands first.
2. **Free-tier levers, one batch:** Q4 + Q5 + Q3 (prompt/template/deterministic-harvest work, ~zero runtime tokens) alongside the open N5–N7 items.
3. **Q1 exemplars** (small, immediate business value).
4. **Q2 edit-distillation** (includes N8 — table + sweep + job + approval card).
5. **Q7 autopilot + decision inbox + plain-language layer** (pure product work, zero model tokens; biggest time-saver for the operator).
6. **Deep Plan mode** (`DEEP-PLAN-MODE-PLAN-2026-07-10.md`).
7. **Appendix C:** C3 cost ledger → C1 escalation ladder → C2 registry-only roles.
8. **DEFERRED MEASUREMENT PHASE (operator decision — run once, at the end):** C4 benchmark harness + Step 11 + Q6 prompt lab. Everything above gets validated in one paid campaign; anything that doesn't show a delta gets reverted or disabled then.

## Part 4 — Premortem resolution (2026-07-10, BINDING; overrides earlier text where in conflict)

An independent adversarial premortem reviewed all three plan docs against the post-SR codebase. Verdict: READY-WITH-FIXES. The fixes:

- **P1 (CRITICAL — frontier backpressure; code change, added to the SR fix batch — runbook Phase 1 finding 3).** All judgment-tier calls (critic/judge/spec/escalation/premortem/distillation) spawn unbounded threads against ONE Claude CLI subscription with hard 5-hour/weekly ceilings. Fix: a global frontier-call semaphore gating every headless-claude spawn (setting `frontier.max_concurrent`, default 2 — mirror the GLM slot gate), and classify CLI rate-limit/quota errors DISTINCTLY from content errors (stderr/exit patterns): quota → backoff + requeue (mirror `dispatch.quota_backoff` pattern), NEVER an `error` verdict and NEVER escalate-to-human on quota. Without this, "maximize automation" trips the subscription cap and mass-escalates every in-flight task.
- **P2 (Q7a forward dependencies staged).** The profile→knob derivations for `plan.recommend` (needs Deep Plan, Phase 5), the escalation knob (needs C1c, Phase 7), and the model floor (needs C2, Phase 7) are ALL gated behind feature-present checks — at Phase 3 they derive nothing and log "staged". Extends guardrail rules 2/3.
- **P3 (benchmark ordering reconciled).** SR Appendix C's original "C3 → C4 first" build order and its "post-Step-11" label are SUPERSEDED by this doc's Part 3 (operator decision: one deferred measurement campaign at the end). Recorded risk, stated plainly: C1/C5/profile thresholds ship HEURISTIC and unmeasured until Phase 8 — the final campaign validates or reverts them. (SR §10 carries a pointer note.)
- **P4 (L1 telemetry schema + missing gates).** L1 requires a schema that Q7a never defined — new table `routing_outcomes(id, task_id, user_id, triage_json, spend_profile, autopilot, rounds_used, fanout_used, final_verdicts, escalated INTEGER, overridden INTEGER, created_at)`, written at terminal task states by `_finalize_result`/the sweep. Part 4 gains gates for: routing_outcomes row on completion (L1), overlay-vs-canonical lesson targeting (L2), exemplar age-out (L3), fingerprint invalidation of tuned thresholds (L4), staged-Eco guards (rule 3), scheduler/JARVIS profile passthrough (rule 7), early-exit as respecified in P6 (rule 8).
- **P5 (purpose whitelist).** `db.MODEL_PURPOSES` is a hard whitelist enforced by the assignment API and UI — seeding `spec_model`/`escalation_model` rows without extending it means the operator can never point or rotate them. Extend `MODEL_PURPOSES` + the assignment UI in the same step that seeds the purposes (Deep Plan Step 1 / Appendix C1a — noted in both docs).
- **P6 (rule 8 respecified — was unimplementable).** Fan-out is planning-time; the reconciler cannot be skipped at runtime. Early-exit inside Optimal now means: (a) SR critic returns empty findings + high confidence → skip the residual round (existing loop knob); (b) the RECONCILER'S OWN FRAMING instructs: "first compute agreement across the investigator reports; adversarially re-verify only the DISAGREEMENTS; strongly-agreed claims get spot-check verification only." Prompt-level, no DAG surgery.
- **P7 (multi-user approval scoping).** `lesson_deltas` and L2 "share with all users?" cards have no task_id and don't fit the per-user fail-closed approval filter. Fix: approvals gain a `scope` ('user' default | 'admin'); distillation/share cards insert scope='admin'; `GET /api/decisions` returns the user's rows plus (for admins) admin-scoped rows; the user_id backfill must never claim task-less approvals for the owner.
- **P8 (SR review findings — canonical repo record; fixes ride the Phase 1 batch):** blockers: (1) `build_critic_sandbox` (app/evals.py) — fresh `clone --local` has the task branch only as `origin/nexus/<slug>`; the guard misses it and `remote remove origin` then discards the refs → critic reviews the BASE branch on repo tasks; checkout from origin BEFORE removing the remote. (2) `_critic_thread` (app/server.py) — catches only ValueError; post-parse exceptions strand `critic_verdict='running'`; persist verdict early + catch-all → 'error'. Follow-ups: reconciler dropped by `tasks[:7]` truncation; later-added workflow tasks inherit no SR flag; empty-findings REVISE retries instead of escalating; no WS broadcast on SHIP/escalation; critic 409 TOCTOU→CAS; false "Speed mode" reasoning line.
- **P9 (ops hardening, schedule alongside the build):** GLM slots — two concurrent fan-out workflows exceed the 8-slot pool; tasks WAIT by design (document it; auto-reducing fan-out under load is post-C4). Sandbox/session hygiene — sweep `workspaces/_critic` age-outs at startup + on the scheduler (not only lazily on next build); `delete_session` when a plan session reaches `created`/`abandoned`. SQLite — set `PRAGMA busy_timeout` explicitly; keep the new periodic jobs' writes short and batched.
- **P10 (precedence rules an implementer would otherwise guess):** (a) framing section order, later-wins on conflict: task brief → spec → DECISIONS.md → exemplars → predecessor deliverables → attachments → **retry feedback last (final word)**. (b) Legacy rows: NULL `spend_profile`/`autopilot` = legacy behavior — no derivation, existing explicit `preference` honored as-is; a pre-Autopilot item never silently flips on loop regeneration until the operator sets a profile. (c) Deep Plan triage runs heuristics synchronously; divergence sampling is async/cached and never blocks the questions round.

## Part 5 — Gates
- verify.sh: existence checks per lever (exemplars block in build_framing, `## Decisions` harvest, acceptance-hash instruction, `[UNSURE` in cverify, `edit_evidence` table, `/api/decisions`, autopilot columns, presets in wizard).
- New `app/scripts/verify_autopilot_e2e.py` (~15 checks): exemplar selection SQL (seeded fixtures, min-score/verdict/user guards), decisions harvest from a fixture deliverable, DECISIONS.md injection presence, edit-evidence capture on reject→accept cycle, distillation approval card (stubbed model call), `/api/decisions` aggregation + recommendation fields, preset→flags derivation for BOTH axes (Eco forces SR off + rounds 1; Smart forces SR on + max width; Optimal defers to triage; involvement axis flips open/closed + checkpoint behavior), workflow cascade of both fields, auto-approve-ship honored only in Full Auto with hours>0 AND never on high-stakes/super_result approvals (guardrail rule 2), `preference` derived-not-editable (rule 1), Eco+high_stakes still judges and gates (rule 2), budget multiplier applied (rule 4), Eco pipeline collapse + high-stakes re-insertion (rules 2+5), Smart rounds ≤3 (rule 6), collapse-monitor activity line fires when routing saturates (rule 9).
- Playwright: Decisions view renders cards + badge; manual view sections; preset cards in wizard.
- `app/CLAUDE.md` + user manual updated (Q7c IS the manual update).
