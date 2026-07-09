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

## Part 2 — Autopilot & the Decision Cockpit (Q7)

Goal: the system drives itself; the human sees ONE inbox of decisions, each answerable in seconds; every concept is explained for a non-AI user.

### Q7a — Autopilot presets (one choice instead of six toggles)
- Three named profiles selectable at wizard/project/task level (radio cards, pattern: `loopPrefCardsHTML`):
  - **🚀 Full Auto** — closed loops, SR per triage recommendation, auto-judge, auto-replan-draft (N6), checkpoints ONLY at: plan approval, final deliverable, escalations, and anything irreversible.
  - **🤝 Assisted (default)** — closed fix-rounds, but SR checkpoints in open mode (review auto-comments before re-runs), replan drafts wait for a click.
  - **🎛 Manual** — everything open; the engine only detects and recommends (pre-v3.2 behavior, now a named choice).
- Implementation: a `autopilot` field (task/workflow) that `design_loop` + wizard read to derive the existing flags (`mode`, `auto_judge`, SR open/closed, `plan.recommend` behavior, `replan.auto_draft`) — presets SET the existing knobs, they don't replace them; power users can still override individual toggles afterwards (the loop modal shows "customized" when drifted from the preset).
- **Files:** `database.py` (2 columns), `loop_engine.design_loop`, `server.py` wizard/create paths, `app.js` preset cards.

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

## Part 4 — Gates
- verify.sh: existence checks per lever (exemplars block in build_framing, `## Decisions` harvest, acceptance-hash instruction, `[UNSURE` in cverify, `edit_evidence` table, `/api/decisions`, autopilot columns, presets in wizard).
- New `scripts/verify_autopilot_e2e.py` (~15 checks): exemplar selection SQL (seeded fixtures, min-score/verdict/user guards), decisions harvest from a fixture deliverable, DECISIONS.md injection presence, edit-evidence capture on reject→accept cycle, distillation approval card (stubbed model call), `/api/decisions` aggregation + recommendation fields, preset→flags derivation, auto-approve-ship honored only in Full Auto with hours>0.
- Playwright: Decisions view renders cards + badge; manual view sections; preset cards in wizard.
- `app/CLAUDE.md` + user manual updated (Q7c IS the manual update).
