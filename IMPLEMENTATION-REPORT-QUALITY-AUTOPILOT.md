# IMPLEMENTATION REPORT — Quality Autopilot (Phase 3)

**Date:** 2026-07-10 · **Branch:** main · **Base:** `3a51247` (Phase-1 fixes committed)
**Contract:** `QUALITY-AUTOPILOT-PLAN-2026-07-10.md` (Part 4 binding) + `QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` §5 (overrides on conflict).
**Scope delivered:** Part 1 Q1–Q5 (Q6 skipped, deferred), Learning-loop L1–L4, Part 2 Q7a/b/c + guardrail rules 1–12, still-open N5/N6/N7 and B4. NOT implemented (separate sessions by contract): Deep Plan, Appendix C, Phase-8 benchmarks, Q6 prompt lab.

Protocol followed: `bash app/scripts/verify.sh` green after every step; one commit per lever (pre-commit hook re-runs verify.sh); full gate suite at the end. **Nothing below is claimed unverified** — each item lists what was built and the gate that proves it. An independent judge should re-run the gates personally.

---

## Sequencing (Part 3 order, as executed)

| # | Commit | Lever |
|---|--------|-------|
| 1 | `feat(quality): Q4` | Q4 project decision log |
| 2 | `feat(quality): Q5` | Q5 uncertainty tagging |
| 3 | `feat(quality): Q3` | Q3 acceptance-tests-first |
| 4 | `feat(quality): N5/N6/N7` | Tier-2 setting-gated automations |
| 5 | `feat(quality): Q1` | Q1 golden exemplars (+ L3) |
| 6 | `feat(quality): Q2` | Q2 edit distillation / N8 (+ L2, P7) |
| 7 | `feat(quality): Q7a` | Autopilot presets, two axes (rules 1–10, P2) |
| 8 | `feat(quality): Q7b` | Decision Inbox |
| 9 | `feat(quality): L1/L4` | Routing telemetry + fingerprint params (+ rule 9) |
| 10 | `feat(quality): B4` | Scheduler template passthrough (+ rule 7) |
| 11 | `feat(quality): Q7c` | Plain-language layer |
| 12 | `chore(quality): rule 11` | Specialist sweep (18 defs) |
| 13 | `feat(quality): rule 12` | JARVIS advisor + surface |
| 14 | `test(quality): verify_autopilot_e2e` | Gate + this report |
| 15 | `fix(quality): rule 5 Eco collapse…` | Judge finding 1 — gate-stage exclusion |
| 16 | `fix(quality): Q1 reserves a slot…` | Judge finding 2 — own-work reservation + honest labels |
| 17 | `test(quality): Part 5 Playwright gate…` | Judge finding 3 — `verify_autopilot_ui.py` |

---

## Part 1 — the levers

### Q4 — Project decision log + running brief — **BUILT**
- Executor contract: workflow members are told to end with a `## Decisions` section and to READ the project `DECISIONS.md` first (P10a order: after the domain block, before predecessor deliverables). `hermes_dispatch.build_framing`.
- Deterministic harvest (no LLM): `harvest_decisions()` parses `## Decisions` and appends `### <title> (<date>)` to `workspaces/workflow-<id>/DECISIONS.md` at `_finalize_result` completion.
- `framing.brief_mode` setting wired (only direct predecessors are ever injected, so brief mode leans on the log for deeper context — noted honestly).
- **Gate:** verify.sh §19 Q4 (5 checks); `verify_autopilot_e2e.py` Q4 group (harvest writes the file, injection appears in a member's framing, `## Decisions` contract present).

### Q5 — Uncertainty tagging — **BUILT**
- Executor framing tells the worker to mark unverifiable claims `[UNSURE: reason]`; unmarked claims are held to a verified-assertion standard.
- `cverify` (critic): verify UNSURE first; unmarked-false = critical, marked-false = at most medium. `cjudge`: same stance. INVESTIGATION rubric A1: an `[UNSURE]` tag counts as an explicit inference label. Live `~/.local/bin` copies synced byte-identical; vendored `setup/` copies committed.
- UI: `highlightUnsure()` wraps `[UNSURE: …]` in amber in deliverable previews (post-escape, injection-safe).
- **Gate:** verify.sh §19 Q5 (5 checks); e2e Q5 group.

### Q3 — Acceptance-tests-first (coding) — **BUILT**
- Spec stage owns an executable `acceptance/` suite + `RUN.md` and records SHA-256s; implementer must pass them without editing `acceptance/`; verifier re-checks the hashes before running.
- Deterministic binding in `_repair_workflow` via `_apply_tests_first()` (setting `pipeline.tests_first`, sentinel-guarded against the revalidate round-trip) so it holds even when the planner omits it.
- **Gate:** verify.sh §19 Q3 (4 checks).

### Q1 — Golden-exemplar retrieval (+ L3) — **BUILT** (judge finding 2 fixed 2026-07-10)
- `golden_exemplars()`: deterministic SQL — SHIP'd, self-score ≥ `exemplars.min_score`, same owner/domain (+client when set), freshest first, unioned with curated `~/knowledge/domains/<d>/examples`. Returns `[{"path","own"}]` and **RESERVES one slot for the operator's own past work** when both kinds exist (curated lead for reading priority but cannot fill every slot — see the judge-review section). `build_framing` labels the two kinds honestly (own vs curated reference). Injected as MUST-READ paths (P10a: after DECISIONS, before predecessors).
- Guards verified: never `code_change`, never a retry round, never the task's own versions. L3 lifecycle: candidate pool capped at `exemplars.max×3`, age-out past `exemplars.max_age_months`.
- **Gate:** verify.sh §19 Q1/L3 (4 checks); e2e Q1 group — now at the DEFAULT `exemplars.max=2` against a 2-curated-file scratch root: selects the high-score SHIP'd exemplar, own work survives the reservation, curated is labeled `own=False`, framing splits the labels; excludes below-min/aged-out/code_change; skips retry.

### Q2 — Operator-edit distillation / N8 upgraded (+ L2, P7) — **BUILT**
- `edit_evidence` table + capture: rejection feedback and the rejected→accepted diff (`_capture_accept_diff`) at approve/reject time; user review comments + judge/critic learning notes folded in at distillation time (B6).
- `lessons.py`: `run_distillation()` gathers evidence, runs ONE judgment-tier call (`lessons.cmd` → vendored `cdistill`, frontier-gated + quota-classified, stubbable), files ONE **admin-scoped** `lesson_deltas` approval; `apply_deltas()` writes to `~/knowledge` and git-commits (autonomy ceiling: the write waits for the one-click approve).
- L2: each delta classified canonical vs user_overlay; `_delta_path()` routes canonical → shared domain file, user_overlay STYLE-VOICE → the member's overlay (flipping the target in the card IS the "share with all users?" decision). P7: `approvals.scope` column; admin rows visible to all admins.
- Cron sweep (`lessons.cron`, `lessons.auto_distill`, `lessons.min_evidence`) + manual `POST /api/lessons/distill`.
- **Gate:** verify.sh §19 Q2/P7/L2 (10 checks); e2e Q2 group (stubbed distill → admin card → apply → canonical + overlay routing → evidence marked distilled).

### Q6 — **SKIPPED** (deferred by contract to the Phase-8 measurement campaign).

### Learning loop L1–L4
- **L1 — BUILT.** `routing_outcomes` (P4 schema) written at terminal task states (`_finalize_result`, `decide_approval`); deterministic no-LLM `sweep_stats()` (per 100 outcomes) proposes threshold tweaks as an admin `routing_tuning` Decisions card.
- **L2 — BUILT** (see Q2).
- **L3 — BUILT** (see Q1).
- **L4 — BUILT.** `learned_params` store tags tuned thresholds with the tier `config_fingerprint()` and auto-invalidates to heuristic defaults on rotation; distilled lessons live in `~/knowledge` and survive — two stores, never mixed.
- **Autonomy ceiling:** every behaviour-changing write (knowledge files, thresholds) is Decisions-gated.
- **Gate:** verify.sh §19 L1/L4 (5 checks); e2e L1/L4 group (outcome row on completion, fingerprint invalidation, rule-9 collapse line).

## Part 2 — Autopilot & Decision Cockpit

### Q7a — Two-axis presets — **BUILT**
- `autopilot.py::derive()` is the single source of truth mapping (involvement, spend) → knobs, honouring the binding rules (see the rules table below). Columns `autopilot`/`spend_profile` on tasks + workflows (NULL = legacy, P10b); settings `autopilot.default_involvement`/`default_spend`. `design_loop`, the wizard, and create/patch derive from the axes; cascade to members mirrors `high_stakes`; UI adds two card rows + an Advanced expander (raw knobs, derived preference read-only).
- **Gate:** verify.sh §19 Q7a + rule1..6/P2 (13 checks); e2e Q7a group (derivation for all three profiles, design_loop derivation, rule-2 floor).

### Q7b — Decision Inbox — **BUILT**
- `GET /api/decisions` aggregates approvals (all kinds) + replan checkpoints, blocking-first then oldest, as cards (headline / ★recommendation / reasons / options / cost). Producers attach `recommendation`+`reasons[]`+`cost_hint` at insert (`_finalize_result`, `_escalate_super`, lesson/routing cards); legacy rows fall back. Unified `decBadge`. New Decisions nav view + card UI. P7: admins see admin-scoped cards.
- `autopilot.auto_approve_ship_hours` — auto-approves ONLY Full-Auto SHIP-verdict deliverables, NEVER high-stakes / SR / escalations (rule 2).
- **Gate:** verify.sh §19 Q7b (6 checks); e2e Q7b group (auto-approve guard both ways, endpoint shape + card fields).

### Q7c — Plain-language layer — **BUILT**
- House metaphor (worker / inspector / foreman / planner / you=client) used across the Decisions view, autopilot cards, and manual. `?` explainer chips (`EXPLAINERS` map + delegated click handler) end with "what should I do?". Manual gains sections for the house roles, the two dials (tokens ≈ fuel), the Decisions inbox, and a when-to-use-what guide. Preset microcopy states cost + benefit plainly.
- **Gate:** verify.sh §19 Q7c (3 checks).

## Still-open items folded in

- **N5 — BUILT.** `judge.auto_scope=all_quality` widens auto-judge from high-stakes-only to every quality-mode rubric deliverable (design_loop + runtime sweep gate + per-profile scope).
- **N6 — BUILT.** `replan.auto_draft` fires `replan/draft` from the detection sweep; APPLY stays operator-approved (the engine still never applies — verify.sh gate updated to forbid only `replan/apply`).
- **N7 — BUILT.** `judge.on_blind_reject` gate-runs the judge synchronously before a no-feedback retry so it carries findings.
- **B4 — BUILT.** `scheduled_jobs.task_template` carries SR / deliverable_type / autopilot preset / high-stakes / domain (rule 7); `scheduler._trigger` applies it and syncs the SR loop; job-create UI gains the controls.
- **Gate:** verify.sh §19 N5/N6/N7 + B4 (7 checks); e2e rule-7 group.

## Guardrail rules 1–12 (binding)

| Rule | Status | Where |
|---|---|---|
| 1 spend absorbs preference | BUILT (loop UI made read-only — 2nd judge pass) | `autopilot.derive` + `design_loop` (eco→speed else quality; the server re-derives on every regenerate regardless of any control). UI now shows quality/speed **derived read-only**: one reactive chip in the Autopilot Advanced expander (follows the spend dial live) and, in the loop-detail modal, a read-only chip whenever a spend profile governs (legacy no-profile items keep the editable select). The duplicate `*-loop-pref` radio group was removed entirely — no editable loop-pref builder remains |
| 2 risk is an independent hard floor | BUILT | high_stakes forces auto-judge even under Eco (`design_loop`); auto-approve never touches high-stakes/SR/escalations (`_sweep_auto_approve_ship`) |
| 3 Eco ships STAGED | BUILT | model-floor derivation gated behind `_feature_present("model_floor")` → "staged" until Phase 7 |
| 4 profiles scale budgets | BUILT | `_autopilot_fields` × 0.5/1/2 on the default budget |
| 5 profiles shape pipeline depth | BUILT (judge finding 1 fixed 2026-07-10) | wizard `pipeline_depth` note + `_repair_workflow` Eco collapse. Risk-floor scan now EXCLUDES quality-gate stages (`_GATE_SPECIALISTS`) so the always-high-stakes verifier doesn't defeat the collapse on real plans; review still re-inserted when a genuine WORK stage is high-stakes — rule 2 wins |
| 6 Smart round cap = 3 | BUILT | `derive` round_cap; `design_loop` clamps every trigger |
| 7 scheduler/JARVIS passthrough | BUILT | B4 template + JARVIS framing carry both axes |
| 8 adaptive early-exit (P6) | BUILT (dead flag removed — 2nd judge pass) | NO derived preset flag (the old `early_exit` boolean was consumed nowhere → removed). Realized unconditionally by **P6(a)** the SHIP quiet-stop (`loop_engine._sweep_super_result` ends the SR loop on SHIP, skipping the residual round — surfaced to the operator as "Stops on SHIP" in `design_loop`) + **P6(b)** the reconciler's own agreement-first framing (`_reconciler_gate_task`: compute agreement first, re-verify only DISAGREEMENTS) |
| 9 router-collapse instrumentation | BUILT | `routing.sweep_stats` WARNs when Balanced saturates to the max-spend path |
| 10 Eco validated behaviourally | DEFERRED (Phase 8) | documented in the Eco card copy + this report |
| 11 specialist sweep | BUILT | all 18 defs + frontier-method skill aligned to `[UNSURE]`, live↔vendored synced |
| 12 JARVIS stays current | BUILT | advisor stance + `/api/decisions` + preset fields in the framing; boots clean (live smoke) |

## Premortem P1–P10 (binding)

- **P1** frontier backpressure — pre-existing from Phase 1; every new frontier call (`lessons.run_distillation`) goes through `evals._FRONTIER_GATE` + quota classification. **P2** forward-deps staged behind `_feature_present`. **P4** L1 `routing_outcomes` schema + the new gates. **P7** `approvals.scope` + admin-visible decisions, task-less rows never claimed for the owner. **P10a** framing order honoured (DECISIONS → exemplars → predecessors → retry-last). **P10b** NULL profile = legacy, no silent flip until the operator sets a profile.
- **P5** (purpose whitelist) is a Deep-Plan / Appendix-C concern (spec_model/escalation_model) — out of Phase-3 scope; noted for Phase 7.
- **P9** (ops hardening; the two in-Phase-3 items are BUILT — added in the 2nd judge pass): SQLite now sets `PRAGMA busy_timeout=10000` explicitly in `database.get_conn` (a writer waits out a concurrent lock instead of erroring), and the disposable critic-sandbox age-out is a shared `evals.sweep_critic_sandboxes()` run at **server startup** + **hourly on the scheduler** (not lazy-only on the next critic build). The other P9 items are out of Phase-3 scope by contract: the GLM-slot WAIT-under-load is documented existing behavior (auto-reducing fan-out is post-C4), and plan-session `delete_session` hygiene belongs to Deep Plan (Phase 5, no plan sessions exist yet).

## Deviations & honest notes

- **Q4 `framing.brief_mode`:** `task_dependencies` already resolves only DIRECT predecessors, so brief mode does not further trim the reading list — it makes deep members lean on the DECISION LOG. Setting wired + documented; behaviour is correct, the token saving is the log substituting for reading history.
- **L2 for PLAYBOOK/RUBRIC:** the read-path overlay (`_knowledge_paths`) covers BUSINESS-CONTEXT + STYLE-VOICE only, so a user_overlay classification meaningfully routes STYLE-VOICE to the member overlay; PLAYBOOK/RUBRIC user_overlay deltas fall back to canonical (there is no executor read-path for a per-user PLAYBOOK). Recorded, not hidden.
- **Rule 10 / Phase-8 measurement:** Eco's "same answer, cheaper" and Optimal's thresholds ship HEURISTIC and unmeasured, per the operator's deferral — the Eco card copy says so and the final campaign validates or raises the floor.
- **Q7a plan-time derivation in the wizard entry flow:** the profile fully governs at CREATE time (loop knobs, budget, cascade, judge scope, round caps) and at revalidate (Eco collapse); a fresh wizard *plan* is produced before the proposal-modal profile pick, so plan-time SR/fan-out/depth from the profile apply on the direct create + revalidate paths, not the very first wizard draft. Noted.

## Judge review — REVISE → all three blockers addressed (2026-07-10)

The independent judge returned **REVISE** with three blocking findings. Each was re-verified
against HEAD first (live-reproduced), fixed, and given a regression check. Commits are granular
(one per finding); the tree is fully committed.

1. **Eco pipeline collapse (rule 5) never fired on real wizard plans.** `_repair_workflow`
   (`app/server.py`) computed `eco_collapse = spend_profile=="eco" and not any(high_stakes)` over
   the RAW plan. Real coding plans always carry the acceptance-verifier with `high_stakes=True`
   (wizard template "high_stakes TRUE always"), so `any(high_stakes)` was always True → the
   review/fix gates were never collapsed under Eco. **Live-reproduced** via `/api/tasks/wizard/revalidate`
   with a realistic-shape plan (verifier present) — the reviewer + fix stages were inserted; the
   thin fixture (no verifier) that the old test used had masked it.
   **Fix:** exclude quality-gate stages (`_GATE_SPECIALISTS = {code-reviewer, acceptance-verifier}`)
   from the risk-floor scan; only a genuine spec/impl stage being high-stakes re-inserts the gates.
   **Re-verified:** realistic Eco plan now collapses (no reviewer); an Eco plan with a high-stakes
   IMPL still re-inserts the reviewer (rule 2 beats rule 5). **Regression:** `verify_autopilot_e2e.py`
   rule-5 group now includes a realistic-shape fixture (verifier in the input) + the high-stakes-work case.

2. **Q1 own-work exemplars never selected under live defaults; framing mislabeled curated files.**
   `golden_exemplars` did `curated + paths` capped at `exemplars.max` (default 2); with the
   live-default 2–3 curated files per domain, the operator's OWN SHIP'd work was always crowded
   out. `build_framing` then labeled the whole list "the operator's OWN past deliverables", so
   stock curated files were presented as the operator's own excellence. **Live-reproduced** with a
   3.9/4 SHIP'd fixture at `exemplars.max=2`: own work absent, framing block falsely OWN-labeling curated.
   **Fix:** `golden_exemplars` returns `[{"path","own"}]` and reserves one own-work slot when both
   kinds exist; `build_framing` splits the block into an OWN header and a "Curated reference
   exemplars … (not the operator's own)" header. **Regression:** `verify_autopilot_e2e.py` Q1 group
   runs at the DEFAULT max=2 against a 2-curated-file scratch root and asserts own-work survival +
   `own=False` labels + honest framing split (the old `max=5` room-making workaround removed).

3. **Part 5 Playwright gate not delivered / not recorded.** The plan's Part 5 lists a Playwright
   row ("Decisions view renders cards + badge; manual view sections; preset cards in wizard").
   **Delivered:** new `app/scripts/verify_autopilot_ui.py` (14 checks, no LLM) driving all three
   surfaces in a real headless browser — a seeded pending high-risk approval renders as a Decisions
   card + lights the `#decBadge`; the User Manual renders its plain-language sections (autopilot
   dials + Decisions inbox + chapter TOC); and the Q7a two-axis preset cards mount in BOTH the
   project proposal wizard and the task-create wizard. Registered in `verify.sh` ("autopilot UI
   gate exists") and `app/CLAUDE.md`.

## Gate outputs (real)

All run on 2026-07-10 against the live service (restarted via `systemctl --user restart nexus`
first — it booted clean, ran every new migration, and answered `/api/decisions`,
`/api/loop/design` (Smart→quality/closed/cap3) and `/api/lessons/evidence` with 200).

```
$ bash app/scripts/verify.sh                              → ALL CHECKS PASSED: 373/373   (+ autopilot UI gate)
$ app/.venv/bin/python scripts/verify_autopilot_e2e.py    → 40 passed, 0 failed   (36 + 4 judge-finding regression checks)
$ app/.venv/bin/python scripts/verify_autopilot_ui.py     → 14 passed, 0 failed   (NEW Part-5 Playwright gate; judge finding 3)
$ app/.venv/bin/python scripts/verify_super_result_e2e.py → 46 passed, 0 failed   (regression: loop_engine/decide_approval/repair)
$ app/.venv/bin/python scripts/verify_block3_e2e.py       → 33 passed, 0 failed   (regression: _repair_workflow/replan/wizard)
$ app/.venv/bin/python scripts/verify_settings_e2e.py     → 62 passed, 0 failed   (regression: settings registry + judge plumbing)
$ app/.venv/bin/python scripts/verify_jarvis_e2e.py       → ALL CHECKS PASS       (rule 12b: JARVIS boots + streams + no page errors with the new advisor framing)
```

The independent judge should re-run all of the above personally; `verify_jarvis_v2_backend.py`
(heavy SDXL/vision, GPU-contended) was not run in this headless pass — the framing change was
verified via clean boot + the lighter Playwright JARVIS gate instead (recorded honestly).

## Post-verification fix (Block 2 regression caught by the full gate sweep)

The program runner's end-of-phase sweep ran the fuller gate suite (which the recorded run above
did not include) and `verify_block2_e2e.py` came back **47 passed, 1 failed** on the check
*"owner list: own + shared visible, foreign invisible."* Root cause was a **pre-existing latent
bug, not a Quality Autopilot regression**: `GET /api/memory` scrolled qdrant with a single fixed
`limit=500` page and never followed `next_page_offset`, so once the live `mem0` collection grew
past 500 points (now 760) any memory whose id landed in the untouched tail silently vanished from
the list. The gate's freshly-seeded probe points (random UUIDs) fell into that tail ~a third of
the time, and needing *both* the owned and the shared probe visible made the failure land reliably.

**Fix** (`server.py::get_memory`, commit `77b8fe5`): paginate the scroll — follow
`next_page_offset` to the end, hard-stopped at 200 pages (100k points) against a runaway cursor.
Strictly additive to the response (returns all memories instead of the first page); the per-user
tag filter is unchanged. Verified:

```
$ app/.venv/bin/python scripts/verify_block2_e2e.py      → 48 passed, 0 failed   (stable across repeated runs)
$ bash app/scripts/verify.sh                             → ALL CHECKS PASSED: 373/373   (pre-commit hook)
```

## Second judge review — REVISE #2 → all four blockers addressed (2026-07-10)

A second independent judge pass on Phase 3 returned **REVISE** with four blocking findings.
Each was re-verified against HEAD (re-located by symbol), fixed (or recorded already-ok with
evidence), given a regression check, and committed granularly. The tree is fully committed.

1. **`autopilot.py` rule-8 `early_exit` was a dead flag; the P4 early-exit gate was missing.**
   Confirmed at HEAD: `derive()` emitted `early_exit = sp in ("optimal","smart")` (autopilot.py)
   but a repo-wide grep found NO consumer — the flag was theatre, and the report's rule-8 row
   over-claimed it. The two real P6 mechanisms both exist and run **unconditionally** (not gated
   by any preset flag): P6(a) the SHIP quiet-stop in `loop_engine._sweep_super_result` (SHIP →
   done, residual round skipped) and P6(b) the reconciler's agreement-first framing in
   `server._reconciler_gate_task` ("compute AGREEMENT … re-verify only the DISAGREEMENTS … rule 8
   early-exit"). **Fix:** removed the dead flag from `derive()` and documented the honest reality
   in the module docstring + inline (P6(a) = SHIP quiet-stop, P6(b) = reconciler framing); no
   `early_exit` field is emitted. **Regression:** `verify_autopilot_e2e.py` gains a "rule 8 / P6"
   group — (i) `derive()` emits no `early_exit` field for any profile, (ii) the Optimal SR loop
   surfaces the SHIP quiet-stop as its stop condition via `design_loop` ("Stops on SHIP"), and
   (iii) a 2-lens fan-out driven through `/api/tasks/wizard/revalidate` produces a reconciler
   whose framing is agreement-first / re-verify-only-DISAGREEMENTS. `verify.sh` adds a rule-8
   static check (no `early_exit` in autopilot.py; "rule 8 early-exit" in server.py; "Stops on
   SHIP" in loop_engine.py). Rule-8 row above corrected.

2. **`app/static/app.js` loop quality/speed was a first-class editable control (rule-1 violation) +
   a double-rendered `m-task-loop-pref` radio group.** Confirmed at HEAD: the loop-detail modal
   (`renderLoopModal`) had a top-level editable `<select id="lp-pref">`, and `autopilotCardsHTML`'s
   Advanced expander plus the task-create/project Looping sections BOTH rendered `loopPrefCardsHTML`
   with the same `${prefix}-loop-pref` radio name — so in the task-create modal two radio groups
   shared `name="m-task-loop-pref"` (a real DOM collision), while the "read-only" note was false.
   The server already re-derives `preference` from the spend profile on every `design_loop` call, so
   the editable value was silently overridden — cosmetically misleading and contrary to binding rule 1
   ("preference derived-not-editable"). **Fix:** one source of truth (`derivedPref`/`derivedPrefLabel`)
   drives a **read-only** derived chip: the Autopilot Advanced expander shows a reactive `#${prefix}-pref-derived`
   chip wired to the spend dial (`updateDerivedPref` on the spend axis' `onchange`); the loop-detail
   modal shows a read-only chip whenever the item carries a `spend_profile` (captured in `loopViewerModal`)
   and keeps the editable select only for legacy no-profile items; the separate Looping sections drop the
   duplicate radios for a "set by the Autopilot spend dial above" note; and `loopPrefCardsHTML`/`selectedLoopPref`
   were removed entirely (no editable loop-pref builder can be reintroduced). Submit paths now source the
   preference from `derivedPref(spend_profile)`. `app.js?v=81`. **Regression:** `verify_autopilot_ui.py`
   asserts zero `m-task-loop-pref` radios, a present `#m-task-pref-derived` chip, and that the chip
   reacts to the Eco spend selection (Eco → Speed). Rule-1 row above corrected.

3. **`verify_autopilot_e2e.py` missing two Part-5-enumerated behavioral checks.** Part 5 lists a
   "workflow cascade of both fields" and "edit-evidence capture on reject→accept cycle"; the gate had
   neither — the Q7a group never PATCHed a workflow, and the Q2 group seeded `edit_evidence` directly
   via `record_evidence`, so `server._capture_accept_diff` (the strongest correction signal) was never
   exercised. **Fix — two new behavioral groups (deterministic, no LLM):** (a) *workflow cascade* —
   `POST /api/workflows`, seed 2 members, `PATCH` both preset axes, assert every member inherits BOTH
   `autopilot` and `spend_profile` (and the workflow row too); (b) *real reject→accept cycle* — seed a
   review-stage task with a live workspace and a **dangling dependency** (so `deps_satisfied`, which is
   fail-closed, parks it and no worker ever claims/dispatches it — deterministic), then `PATCH` its
   deliverable approval **rejected** (asserting the deliverable is versioned to `deliverable.v1.md` and
   the feedback is captured as evidence), stage the reworked deliverable, and `PATCH` a fresh approval
   **approved** — asserting `_capture_accept_diff` fired and wrote an `accept_diff` evidence row carrying
   the actual added→removed text. Self-cleaning (verified: no leftover tasks/approvals/evidence/workspaces).

4. **P9 (ops hardening) neither implemented nor recorded as deferred.** Confirmed at HEAD: no
   `PRAGMA busy_timeout` anywhere in `database.py`, and the critic-sandbox age-out lived inline in
   `evals.build_critic_sandbox` (~lines 480–486) — lazy-only, so a machine that stopped running critics
   leaked stale sandboxes forever; nothing swept at startup or on a scheduler. **Fix (the two in-scope
   items):** (a) `database.get_conn` now sets `PRAGMA busy_timeout=10000` explicitly; (b) the age-out is
   extracted to `evals.sweep_critic_sandboxes(max_age_h=24)` and invoked from three places — lazily before
   each build (as before), once at **server startup**, and **hourly on the scheduler thread** (throttled).
   The remaining P9 items are recorded as deferred with rationale (GLM-slot WAIT is documented existing
   behavior; plan-session `delete_session` is a Phase-5 Deep-Plan concern — see the P9 note above).
   **Regression:** `verify_autopilot_e2e.py` P9 group asserts the connection's `busy_timeout` is 10000 and
   that the sweep reclaims a stale (>24h) sandbox while keeping a fresh one; `verify.sh` adds three P9
   static checks (busy_timeout PRAGMA; the sweep helper; the sweep wired into both server.py + scheduler.py).

**Gates re-run after the four fixes** (real, against the live service after `systemctl --user restart nexus`
— it booted clean, swept sandboxes at boot, and answered the APIs):

```
$ bash app/scripts/verify.sh                              → ALL CHECKS PASSED: 377/377   (+ rule-8, +3 P9 checks)
$ app/.venv/bin/python scripts/verify_autopilot_e2e.py    → 50 passed, 0 failed   (40 base + 10 across the four fixes)
$ app/.venv/bin/python scripts/verify_autopilot_ui.py     → 17 passed, 0 failed   (14 + 3 finding-2 checks)
```
