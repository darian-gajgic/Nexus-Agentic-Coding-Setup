# IMPLEMENTATION REPORT — Deep Plan mode (Phase 5)

**Date:** 2026-07-10 · **Author:** implementing session (Opus 4.8)
**Contract:** `DEEP-PLAN-MODE-PLAN-2026-07-10.md` (design, locked §3) +
`QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` §5 (binding corrections, overrides on conflict).
**For the independent judge:** everything below is grounded in committed code. Re-run the gates
yourself (§7). Anchors were re-located by symbol name (SR shifted offsets); every file:line the
plan gave was treated as stale and re-found.

Base commit: `23f24d6`. Phase commits (granular, one per step, tree fully committed at each):

| Commit | Step |
|---|---|
| `86d6a42` | 1 — plan_sessions table, spec_model purpose, plan.* settings |
| `1e0661b` | 2 — triage (heuristics + async divergence sampling) |
| `b5ca112` | 4 — planning session backend (templates + endpoints) |
| `354ce00` | 6 — draft the DAG from the SPEC |
| `93c6234` | 7 — structural validators + external premortem critique |
| `b17c54d` | 8 — the SPEC travels downstream |
| `204328b` | 3+5 — recommendation banner + Deep Plan modal (UI) |
| `1ebfdcc` | 9 — JARVIS framing + entry points |
| `81d9175` | 10 — gates + docs |
| `22ef53b` | 10 — Playwright UI gate |

**Commit-order note (not a scope change):** the backend steps 4/6/7/8 were committed before the
UI steps 3/5 so the UI wired against a complete, already-tested backend and no commit left a
dangling reference. All plan steps are implemented; the numeric order is preserved in intent.

**REVISE pass (independent judge, 2026-07-10)** — the judge returned REVISE with two blocking
findings; both re-verified against HEAD (reproduced), fixed, and covered by a new regression check:

| Commit | Judge finding | Fix |
|---|---|---|
| `1e23351` | 1 — JARVIS DEEP PLAN framing omitted `/attach`; voice path stranded the session at `drafted` with its Hermes session never freed (sweep covered `active` only) | Framing now documents the REQUIRED attach call after create; `sweep_stale_plan_sessions()` covers `drafted` too. Regression: verify.sh (`sessions/ID/attach`, `status IN ('active','drafted')`) + a drafted-sweep e2e check (now 21/21) |
| `09bf2a0` | 2 — Step 7's "re-run premortem" button and "flag changed/added/removed cards" were unimplemented and undocumented | **Implemented** (chosen over recording a deviation — both are locked Step 7 requirements): `🔍 Re-run premortem` button + `planEdComputeDiff` flagging ＋added/✎changed/removed cards after revalidate. Regression: verify.sh + a UI button check (now 10/10) |

---

## 1. What each step delivers (grounded, by symbol)

**Step 1 — DB / settings / purpose seed** (`database.py`, `settings_registry.py`, `server.py`, `app.js`)
- `plan_sessions` table (`database.py`, `CREATE TABLE IF NOT EXISTS plan_sessions`): id/user_id/
  goal/family/spec_json/transcript/hermes_session_id/status/triage_json/created_at/updated_at.
  Resumable — no boot-reset (swept by the hygiene sweep instead).
- `spec_model` registry purpose seeded → the frontier judge's model row, in BOTH the empty-table
  seed and a marker-guarded migration for existing installs (`migrated.spec_model`). Verified on a
  scratch DB: `resolve_assignment(None,'spec_model') → claude-opus-4-8`.
- **Premortem-fix (whitelist):** `db.MODEL_PURPOSES` extended to include `spec_model`; `sreg.PURPOSES`
  gains it; new `sreg.CLI_PURPOSES = (frontier_judge, spec_model)`; the assignment API route check
  (`models_assign`) uses `sreg.CLI_PURPOSES` (was frontier_judge-only) so a seeded spec_model row is
  visible AND rotatable; `app.js PURPOSE_ROUTES.spec_model='cli'` so the Settings dropdown renders it.
- Settings section `plan`: deep_enabled/recommend/triage_samples/max_turns/max_questions_per_turn/
  critique_enabled/critique_timeout_s/critique_cmd/stub.

**Step 2 — Triage** (`plan_engine.py`, `server.py`)
- `plan_engine.triage_heuristics` — DETERMINISTIC signals only (length, vague-referent, artifact-
  count, cross-domain, dependency phrases, blast-radius) → complexity 0–10 + reasons. **No LLM
  self-rating** (locked §3.1). `divergence()` computes task-count spread + title-token Jaccard +
  DAG-shape mismatch over cheap draft summaries. `recommend()` soft-gates; spend profile overrides
  `plan.recommend` (eco→never/optimal→auto/smart→always).
- `server._wizard_triage` runs heuristics **synchronously** and attaches `triage` to the questions,
  task and workflow wizard responses. **Premortem-fix (non-blocking):** divergence sampling runs in
  a background `threading.Thread(_triage_sample,…)` on the easy-purpose model, cached per goal-hash;
  it never blocks the questions round — the banner may arrive with phase-2 instead.

**Step 4 — Planning session backend** (`plan_engine.py`, `server.py`, `scheduler.py`)
- `SPEC_TEMPLATES` per family (software/analysis-audit/content/research) with required+optional
  slots; `new_spec/merge_spec/required_filled/empty_required/spec_public/render_spec_md`; scaffolded
  `interview_framing` (≤max_q questions, 3–5 ★ options, READY on required-filled); `parse_turn`;
  `stub_turn` (deterministic slot-filling, mirrors `evals.stub`).
- Endpoints: `POST /api/plan/sessions` (row + dedicated Hermes session + opening turn), `/turn`,
  `PATCH /spec`, `GET` list/one (resume), `DELETE` (abandon). Owner-scoped (`_owned_plan_session`).
- **Session hygiene (premortem-fix; REVISE finding 1):** `sweep_stale_plan_sessions()` abandons
  stale **`active` OR `drafted`** sessions >7d + deletes their Hermes sessions, wired at **startup**
  (`server.py`) AND **hourly on the scheduler** (`scheduler.py`); create→`_plan_start_session`,
  abandon/attach(created)→`delete_session`. `drafted` is covered because only `/attach` reaches
  `created` — a drafted-but-unattached session (the JARVIS voice/API path) would otherwise strand.

**Step 6 — Draft from spec** (`server.py`, `plan_engine.py`)
- `_task_wizard_framing` gains an optional `spec_block`; `POST /…/draft` seeds it with the rendered
  SPEC → `_repair_workflow` → proposal. **Premortem-fix (family map):** `deliverable_type` set from
  `plan_engine.FAMILY_DELIVERABLE_TYPE` (software→`code_change`/analysis-audit→`analysis`/
  content→`content`/research→`research`; verified against `evals.DELIVERABLE_TYPES`) on every task;
  acceptance criteria distributed as `Done when:` lines; status→`drafted`.

**Step 7 — Plan verification** (`server.py`, `evals.py`, `settings_registry.py`)
- `server._validate_plan` — deterministic structural validators: orphan acceptance criterion,
  output-ref-without-dependency (noun-match WARN), near-duplicate titles (≥2-token guard),
  per-task budget sanity. Advisory warnings, never blockers.
- `evals.run_plan_critique` — ONE premortem on the `spec_model` purpose (external verifier, not the
  planner grading itself, satisfying the anti-self-critique evidence). **Routes through the SAME
  `_FRONTIER_GATE` semaphore** as judge/critic (premortem P1); quota-classified; `plan.stub`
  short-circuits; optional `plan.critique_cmd` override. `spec_model_for` mirrors `judge_model_for`.
  `POST /…/critique` runs validators + premortem via `run_in_threadpool`; findings render as ⚠
  annotations on task cards (`planEd.annotations`). Approval is never blocked.
- **Re-run + diff flags (REVISE finding 2):** the premortem auto-runs on first draft AND is
  re-runnable via the `🔍 Re-run premortem` button (`wfRerunCritique` → `deepPlanRunCritique`).
  When the plan checker changes an edited plan, `planEdComputeDiff` (compare by index+title) flags
  ＋added / ✎changed cards and reports the removed count, so the operator never plays
  spot-the-difference. Advisory — approval still never blocked.

**Step 8 — Spec travels downstream** (`server.py`, `evals.py`, `setup/bin/cjudge`)
- `POST /…/attach` writes `SPEC.md` + `spec.json` into the workflow/task `attachments/` (existing
  MUST-READ mechanism), marks the session `created`, deletes the Hermes session. Acceptance criteria
  ride each task description (`Done when:`) and survive `_clamp_wizard_task` (description preserved).
- `evals.build_critic_sandbox` copies the workflow `spec.json` into `_critic_context/` and records
  `ctx["spec"]` — the critic verifies against the ORIGINAL contract.
- `evals.run_judge_cmd` + `cjudge` (both vendored `setup/bin/cjudge` and installed `~/.local/bin/
  cjudge`, byte-identical) gain the optional `JUDGE_SPEC` token; `_judge_thread` resolves the
  workflow's `SPEC.md`.
- `replan_draft` seeds the recovery plan from the original SPEC.

**Steps 3+5 — UI** (`app.js`, `index.html`, `server.py`)
- Step 3: `handleWizardPlan` offers Deep Plan ONCE via `deepPlanRecommendModal` when
  `triage.recommend_deep_plan` (reasons + `✦ Start Deep Plan` / `Quick plan anyway`; deny =
  zero-friction continue). Manual `✦ Deep Plan` button in `describeTaskUI`. Accept/deny →
  `POST /api/plan/telemetry` (router-collapse watch).
- Step 5: `deepPlanModal` — left conversation (option cards + ★, free-text, Send), right live
  editable SPEC pane (per-family slots, required-empty highlighted, filled ✓, family switcher;
  debounced `PATCH /spec`). `deepPlanDraft` → the SAME proposal modal + plan editor; premortem
  findings + structural warnings render as ⚠ annotations (auto-run on first draft when
  `plan.critique_enabled`). On create the SPEC attaches (Step 8). Cache-buster `v85`.

**Step 9 — JARVIS + entry points** (`server.py`)
- The JARVIS system-control framing documents the Deep Plan surface (a `DEEP PLAN:` block +
  triage in the `PLAN WELL` line + PROACTIVE ADVISOR offer) so "plan a project with me" starts a
  session with voice answers as turns (rule 12). **REVISE finding 1:** the block now documents the
  full lifecycle through the REQUIRED `POST /…/attach {kind, new id}` after create — the step that
  writes the SPEC into the project and closes the session — so the voice/API path no longer strands
  the session or drops the SPEC (the UI path already attached; the framing had omitted it). Deck's
  "Hand a task to the fleet" routes through `describeTaskUI` → the banner (honored). Scheduler tasks
  bypass the wizard → skip triage (B4).

**Step 10 — Gates + docs** (`verify.sh` §20, `verify_deep_plan_e2e.py`, `verify_deep_plan_ui.py`, `CLAUDE.md`)

---

## 2. The two binding additions (master plan §5 C-4/C-5) — done

- **C-4 (e2e gate path):** `app/scripts/verify_deep_plan_e2e.py` exists (20 checks) and stubs the
  PLANNING model via the new **`plan.stub`** setting. `plan.stub` short-circuits the Hermes session
  turn with canned slot-filling replies in `plan_engine.stub_turn` (mirrors `evals.stub`); the
  judge/critic command-template stubs do NOT reach session turns (they don't — session turns go
  through `hd.stream_turn`, not the CLI). Gate result: **20/20**.
- **C-5 (B7 no-block-in-async):** every plan-session endpoint that calls a model runs its blocking
  work via `run_in_threadpool` — turn (`_plan_run_turn`), draft (`_plan_draft_raw`), critique
  (`_ev.run_plan_critique`), session start (`_plan_start_session`). `app/scripts/check_async_blocking.py`
  (which audits `server.py`) passes. The premortem stub also honors `plan.stub` so the whole planning
  surface stubs with ONE switch (a superset of C-5's minimum, not a conflict).

## 3. Locked decisions (§3) upheld — no revisiting

1. Triage = heuristics + cheap draft-plan divergence, **never LLM self-rating**. 2. Soft gate
(accept/decline one click; quick path default; `plan.recommend` always/never/auto). 3. Asking gated
+ capped (≤max_q/turn, 3–5 ★ options, READY on required-filled or max_turns). 4. Scaffolded by
per-family spec template. 5. Conversation/drafting on the executor tier (GLM `default_task_model`);
premortem once on `spec_model` via headless claude. 6. Structural validators first, then one
premortem — no LLM self-grading. 7. SPEC on disk that travels (attachment + criteria in tasks +
critic context + judge token + replan seed). 8. Approve-with-edits (existing plan editor); premortem
= annotations. 9. One triage drives both the Deep Plan and Super Result suggestions.

## 4. Deviations & judgment calls (recorded per the headless protocol)

1. **Premortem invocation:** the plan said "runs headless claude on `spec_model` (reuse the
   `run_judge_cmd` invocation pattern)". I reused the *machinery* (frontier gate, quota
   classification, temp files, cwd under knowledge) but invoke `claude -p` directly (default) rather
   than a vendored `cplan` binary — none was specified, and inventing one adds a byte-identical sync
   obligation. An optional `plan.critique_cmd` override is provided for customization/stubbing.
2. **Judge spec token (Step 8, "optional token"):** implemented fully — `JUDGE_SPEC` env in
   `run_judge_cmd` + a read block in BOTH `cjudge` copies (kept byte-identical). Absent when a task
   isn't deep-planned = exactly today's behavior.
3. **`plan.critique_cmd`** added to the registry (not named in the plan) as the premortem's stub/
   override hook, symmetric with `judge.cmd`/`super.critic_cmd`.
4. **Telemetry endpoint** `POST /api/plan/telemetry` added (no `POST /api/activity` existed) to log
   accept/deny for the router-collapse watch.

## 5. Anti-regression evidence (things I verified, refute-by-default)

- The spec_model seed is idempotent + marker-guarded (tested on a scratch copy of nexus.db, live DB
  untouched during that test). Deliberate deletions stay deleted (same contract as existing seeds).
- The near-duplicate-title validator does NOT false-positive on `Spec: X` vs `Implement: X` (single
  shared noun) — guarded to require ≥2 distinctive tokens each side (verified by unit call).
- The triage divergence sampler cannot stall the wizard: heuristics are synchronous; sampling is a
  daemon thread; the wizard response never awaits it (async-blocking gate green).
- The `JUDGE_SPEC` temp file is cleaned in `run_judge_cmd`'s `finally`.
- No stray runtime artifacts: `workspaces/` is gitignored; test plan_sessions rows deleted; the tree
  is fully committed (`git status` clean).

## 6. NOT done — deferred by contract, not omission

- **Step 11 (deep-plan-vs-quick benchmark)** — explicitly deferred to the ONE Phase-8 measurement
  campaign (master plan §3, benchmarks deferred). No measured claims are made here; the win is
  argued from the elicitation literature (§2 of the design), unmeasured — recorded risk, accepted.
- **JARVIS full streaming re-run:** the rule-12 JARVIS framing was updated and the static rule-12
  gates pass (verify.sh: "JARVIS knows Deep Plan", advisor stance, decisions, presets). A full
  `verify_jarvis_v2_backend.py` streaming re-run is GLM-load-dependent; the framing change is
  additive (no text removed), so the existing JARVIS gates remain valid.

## 7. Gate results (re-run these)

From the repo root / `app/`:

- `bash app/scripts/verify.sh` → **409/409 PASS** (Deep Plan = §20, 27 checks — incl. the two
  REVISE regressions: "session hygiene sweep (+drafted)", "JARVIS knows Deep Plan (+attach)", and
  the new "Step7 re-run premortem + diff flags").
- `app/.venv/bin/python app/scripts/verify_deep_plan_e2e.py` → **21/21 PASS** (plan.stub-driven,
  self-cleaning): triage heuristics + recommendation payload + spend override + divergence; session
  CRUD/resume/READY stop rule/spec edit; draft phase-2 + family type + criteria distribution;
  orphan-criterion validator + premortem-stub annotations; SPEC attachment + critic context; stale
  **active AND drafted** sweep (REVISE finding 1).
- `app/.venv/bin/python app/scripts/verify_deep_plan_ui.py` → **10/10 PASS** (Playwright): banner
  accept/deny, two-pane modal + family switcher, a turn, a persisting spec edit, Draft → proposal
  with the Deep Plan banner + a ⚠ premortem annotation + the re-run premortem button (REVISE
  finding 2); zero console errors.
- `app/.venv/bin/python app/scripts/check_async_blocking.py` → PASS (B7).

Working tree: fully committed, clean.
