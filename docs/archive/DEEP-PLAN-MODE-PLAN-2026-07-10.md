# DEEP PLAN MODE — conversational planning phase: implementation guide

**Status:** APPROVED DESIGN, NOT IMPLEMENTED. Execute in a dedicated session.
**Date:** 2026-07-10
**Author:** Claude Fable 5 (frontier side), from a SOTA research pass + the existing wizard/plan-editor code map.
**Relationship:** builds on the implemented Super Result feature (`SUPER-RESULT-PLAN-2026-07-09.md`, report `IMPLEMENTATION-REPORT-SUPER-RESULT.md`). Shares the tier principle from its Appendix C: judgment-tier model (today Opus 4.8) for critique, executor tier (GLM-5.2) for bulk; the top model (Fable 5) stays a test reference only.
**For the implementing session:** read this fully; decisions in §3 are locked. Line anchors were valid pre-Super-Result — **re-locate by symbol name**, the SR implementation shifted server.py/app.js offsets. Each step must leave `bash app/scripts/verify.sh` green; restart only via `systemctl --user restart nexus`; bump `?v=N` in index.html for app.js changes.

---

## 1. What this is and why

Today the wizard is one-shot: goal in → ONE round of ≤6 questions → plan proposal → editable DAG → create. That's good for simple goals and demonstrably too thin for complex ones: elicitation research shows LLM interviewers surface less than half of implicit requirements in a single round, and the best questions only emerge in later turns. Every serious product converged on the same upgrade: **read-only research → iterative conversation → editable plan artifact → explicit approval** (Claude Code plan mode, Cursor plan mode, GitHub Spec Kit, Gemini Deep Research's editable plan preview, Devin's planning checkpoint).

**Deep Plan mode** adds that conversational phase to Nexus for ALL deliverable types: the system detects complex/ambiguous goals from the first prompt, *recommends* deep planning (user accepts or denies — soft gate), runs a short scaffolded interview that builds a persistent **SPEC artifact**, drafts the DAG from the spec, verifies the plan structurally plus with an external-model premortem, and injects the spec into every downstream task, the judge, and the Super Result critic. Planning tokens are tiny next to execution tokens — this is the highest quality-per-token lever in the system.

## 2. Research grounding (what the evidence actually says)

| Finding | Consequence here |
|---|---|
| Clarification improves outcomes when **gated on detected ambiguity**: ClarifyGPT (FSE'24) +10pts Pass@1 via consistency-check-triggered questions; "Ask or Assume?" nearly closes the underspecification gap on SWE-bench-style tasks with calibrated asking | Ask only when sampled drafts diverge; never a fixed questionnaire |
| Most tasks need **0–3 questions** (Ask-before-Plan, EMNLP'24); over-asking adds friction without quality; **3–5 answer options** beat 2 | ≤3 questions per turn, ≤3 turns before offering to draft; 3–5 recommended options each |
| Interview-style elicitation preferred over forms, but free-form LLM interviews miss >half of implicit requirements — **scaffold the questions** | Structured spec template drives the interview; conversation fills slots, not vibes |
| **LLM self-critique of plans DEGRADES them** (Valmeekam & Kambhampati: false-positive approvals of broken plans); external/structural verifiers work (LLM-Modulo, VerifyLLM) | Plan verification = deterministic DAG checks + a premortem by a DIFFERENT model (judgment tier). Never the planner grading itself |
| Complexity triage: **sample-disagreement** is the reliable signal (AutoMix/BEST-Route); LLM "rate this 1–10" self-assessment is unreliable; RouteLLM shows routing pays (~2× cost cut at 95% quality) | Triage = heuristics + divergence across N cheap draft plans; one sampling pass yields ambiguity AND complexity |
| Plan-first beats ReAct only on dependency-heavy tasks | Keep the quick path as default; deep plan is recommended, not forced |
| Cross-product convergence: **plan/spec as a persistent editable artifact** injected downstream (Spec Kit: specify→plan→tasks; Claude Code/Cursor: plan file); **approve-with-edits**, diff-style revisions | SPEC.md on disk, attached to the workflow, criteria per task node; extend the existing plan editor, don't replace it |

## 3. Locked decisions (do NOT revisit)

1. **Triage never uses LLM self-rating.** Signals = deterministic heuristics + divergence across N=2–3 cheap sampled draft plans (executor-light model). Output: `complexity`, `ambiguity`, `recommend_deep_plan`, `reasons[]`.
2. **Soft gate.** Deep Plan is recommended with reasons; the user accepts or declines in one click; quick path stays default. Settings can force always/never/auto.
3. **Asking is gated and capped.** ≤3 targeted questions per turn, 3–5 recommended options each (defaults marked ★), stop asking when the spec's required slots are filled or divergence clears; after ~3 turns always offer "Draft plan now". User can draft at ANY time.
4. **The interview is scaffolded by a per-family spec template** (software / analysis-audit / content / research — same families as `deliverable_type`). The conversation fills template slots; free-form chat is allowed but the planner always maps answers back into the spec.
5. **Model split per the tier principle:** the CONVERSATION + drafting run on the executor tier (GLM — latency + cost, elicitation isn't the hard part). The PREMORTEM CRITIQUE runs once on the judgment tier via headless claude (new registry purpose `spec_model`, default = the frontier_judge assignment) — external verifier, satisfies the anti-self-critique evidence and Appendix C1a's "frontier does design review" principle.
6. **Plan verification is structural first:** deterministic validators (extend `_repair_workflow`) for missing prerequisites, orphan acceptance criteria, redundant/duplicate nodes, budget sanity — then the one premortem call. No LLM self-grading pass.
7. **The spec is an on-disk artifact that travels:** `SPEC.md` (+ `spec.json`) written into the workflow workspace on creation, attached as a workflow attachment (existing MUST-READ framing), acceptance criteria distributed into task descriptions, spec path added to the Super Result critic's `_critic_context/context.json` and available to the judge. Replan drafting (R2) seeds from it.
8. **Approve-with-edits stays the approval model** (existing plan editor); premortem findings render as annotations on task cards, re-plans highlight what changed.
9. **One triage, two recommendations:** the same triage output also drives the "recommend Super Result for this goal" suggestion (Appendix C5 synergy) — complexity/blast-radius above threshold → suggest both, independently accept/deny.

## 4. Architecture

```
 goal typed (wizard / JARVIS deck)
        │
        ▼
 TRIAGE (Step 2) — heuristics + N cheap draft plans → divergence
        │
        ├─ simple → existing quick wizard (unchanged, still may ask its one round)
        │
        └─ complex → banner: "This looks complex because <reasons>.
                     ✦ Deep Plan?  [Start Deep Plan] [Quick plan anyway]"
                            │ accept
                            ▼
 DEEP PLAN SESSION (Steps 3-5) — plan_sessions row + Hermes session
   chat pane (≤3 Qs/turn, 3-5 ★options) ⇄ live SPEC pane (editable slots,
   per-family template; user may edit slots directly or type freely)
   "Draft plan" button always available
                            ▼
 DRAFT (Step 6) — spec.json seeds the existing phase-2 wizard framing →
   _repair_workflow → DAG; acceptance criteria attached per task node
                            ▼
 VERIFY PLAN (Step 7) — deterministic structural validators
   + ONE premortem call on spec_model (external model):
   "what fails, what's missing, which criteria are untestable"
   → annotations in the plan editor; user edits; revalidate; approve
                            ▼
 CREATE — SPEC.md → workflow workspace + attachment; criteria in tasks;
   spec path → SR critic context + judge; replan seeds from spec
```

Everything downstream (dispatch, loop engine, Super Result, approvals) is untouched — Deep Plan only upgrades what enters the pipeline.

## 5. Implementation steps

### Step 0 — Preconditions
Super Result implemented and its judge pass done. Re-locate all anchors by symbol (post-SR offsets differ). New registry purpose `spec_model` will be seeded (Step 1) — coordinate with Appendix C1a if that landed first (same purpose, seed once).

### Step 1 — DB, settings, purpose seed (`app/database.py`, `app/settings_registry.py`)
- New table `plan_sessions`: `id TEXT PK, user_id TEXT, goal TEXT, family TEXT, spec_json TEXT, transcript TEXT, hermes_session_id TEXT, status TEXT ('active'|'drafted'|'created'|'abandoned'), triage_json TEXT, created_at REAL, updated_at REAL`. Boot-reset: none needed (sessions are resumable; sweep `abandoned` >7 days).
- Seed `model_assignments` purpose `spec_model` → default to the frontier_judge row (global scope), same seeding pattern as existing purposes (`database.py` model-registry block). **Premortem fix (2026-07-10): also extend `db.MODEL_PURPOSES` and the assignment API/UI whitelist — a seeded row without the whitelist entry is invisible and unrotatable.** Premortem calls route through the frontier backpressure semaphore (QUALITY-AUTOPILOT Part 4 P1).
- Settings section `plan`: `plan.deep_enabled` (1), `plan.recommend` (`auto|always|never`, default auto), `plan.triage_samples` (2, min 0=heuristics-only, max 3), `plan.max_turns` (3), `plan.max_questions_per_turn` (3), `plan.critique_enabled` (1), `plan.critique_timeout_s` (600). **Coherence note (2026-07-10):** once the Quality Autopilot spend profiles land, `plan.recommend` is DERIVED from the item's spend profile (Eco→never, Optimal→auto, Smart→always) and the raw setting becomes the fallback for items without a profile.

### Step 2 — Triage (`app/server.py`, extend the wizard phase-1 path)
In `task_wizard` phase 1 (symbol: `task_wizard`, pre-SR ~`:4520`):
- **Heuristics (free):** goal length + vague-referent markers ("it", "the system", unnamed targets), artifact-count nouns (report+site+campaign…), cross-domain keyword hits (≥2 domains), dependency phrases ("then", "based on", "after"), blast-radius terms (deploy, prod, send, purchase, migrate). Each contributes to `complexity_score` 0–10 with the trigger recorded in `reasons[]`.
- **Divergence sampling (cheap):** when heuristics land in the uncertain middle band (3–7) and `plan.triage_samples > 0`, run N draft-plan generations on the `easy`-purpose model (existing wizard framing, temperature via separate sessions), then compute divergence deterministically: task-count spread, Jaccard distance of normalized task-title token sets, DAG-shape mismatch. High divergence ⇒ ambiguous+complex (ClarifyGPT signal). Reuse one of the drafts for the quick path so the tokens aren't wasted. **Premortem fix (2026-07-10): heuristics run SYNCHRONOUSLY; divergence sampling must never block the wizard's questions round — run it async (or piggyback on the phase-2 call) and cache per goal-hash; on the questions path the recommendation banner may arrive with the phase-2 response instead of phase-1.**
- Response gains `triage: {complexity, ambiguity, recommend_deep_plan, recommend_super_result, reasons[]}`. Quick path is unchanged otherwise. Monitor the accept/deny split via activity log (router-collapse warning from the literature).

### Step 3 — Recommendation UI (`app/static/app.js`)
In the wizard modal flow (`describeTaskUI` / `handleWizardPlan`, pre-SR ~`:8367/:8415`): when `recommend_deep_plan`, render a banner above the proposal/questions: reasons in plain language + `[✦ Start Deep Plan]` `[Quick plan anyway]`. Deny → existing flow continues with zero friction. `plan.recommend=always` shows it for every goal; `never` hides it; a "✦ Deep Plan" button in the modal header lets the user start it manually regardless. Log accept/deny to activity.

### Step 4 — Planning session backend (`app/server.py` + new `app/plan_engine.py`)
- `plan_engine.py`: spec templates per family — required + optional slots:
  - **software:** goal, users, stack/platform, constraints, acceptance_criteria[] (testable), out_of_scope, risks, data/integrations
  - **analysis-audit:** scope (subsystems enumerated), questions_to_answer[], evidence_standard (A-gates ref), deliverable format, out_of_scope
  - **content:** audience, channel/format, core_message, voice (STYLE-VOICE ref), success_metric, length, mandatories/taboos
  - **research:** research_questions[], source_standard, depth/breadth, output format, decision_it_informs
  Family selection = triage guess from the goal, user-switchable.
- Endpoints: `POST /api/plan/sessions` (start: creates row + a dedicated Hermes planning session with a scaffolded system framing: "fill this template by interviewing; ≤{max_q} questions/turn, each with 3–5 options and a ★ recommended default; ask ONLY for empty/ambiguous required slots; when required slots are filled say READY"), `POST /api/plan/sessions/{id}/turn` (user message → model reply parsed into: questions[] with options, slot updates, spec_json merge; store transcript), `PATCH /api/plan/sessions/{id}/spec` (direct slot edits from the UI), `POST /api/plan/sessions/{id}/draft` (→ Step 6), `GET /api/plan/sessions(/{id})` (resume support — a session survives browser restarts). Owner-scoped, same auth pattern as wizard.
- Stop rule: after `plan.max_turns` turns OR all required slots filled, the reply must lead with "ready to draft" instead of more questions.
- **Session hygiene (premortem fix):** call `hermes_dispatch.delete_session` when a plan session reaches `created` or `abandoned`; sweep stale `active` sessions >7 days at startup AND on the scheduler, not only lazily.

### Step 5 — Deep Plan UI (`app/static/app.js`)
New modal (pattern: existing wizard modal + JARVIS chat mechanics): left = conversation (questions render like `wizardQuestionsModal` option cards with ★ defaults; free-text always allowed), right = **live spec pane** — the template slots as editable fields, filled ones ✓, required-empty highlighted; direct edits PATCH the session. Header: family switcher, `[Draft plan →]` (always enabled), abandon. On draft → the existing proposal modal/plan editor renders the result (Step 6) with the premortem annotations (Step 7). Keep `uiLocked()` discipline; no blind re-renders during ticks.

### Step 6 — Draft from spec (`app/server.py`)
`.../draft`: seed the existing phase-2 wizard call with the spec — `_task_wizard_framing` (symbol; pre-SR ~`:4104`) gains an optional SPEC block ("this plan MUST satisfy every acceptance criterion; distribute each criterion onto exactly one task as 'Done when: …'; respect out_of_scope"), then the normal `_repair_workflow` path. Set `deliverable_type` from family on every task — **explicit map (premortem fix; the enum in `evals.py DELIVERABLE_TYPES` is the truth): software→`code_change`, analysis-audit→`analysis`, content→`content`, research→`research`; spec-template labels stay friendly but the stored family key IS the enum value**; carry `recommend_super_result` → preset the ✨ toggle in the proposal. Store `plan_sessions.status='drafted'`.

### Step 7 — Plan verification (`app/server.py` + plan editor)
- **Structural validators** (deterministic, inside `_repair_workflow` or a sibling `_validate_plan` called by revalidate): every acceptance criterion owned by ≥1 task ("orphan criterion"); no task references another task's output without a dependency edge (title/description noun-match heuristic — WARN not error); duplicate/near-duplicate task titles; per-task budget sanity vs `dispatch.default_task_budget`; verifier/reconciler sink present per family rules (already enforced). Emit as `repairs`/`warnings` — the existing proposal modal already renders repair notes.
- **Premortem critique (one call, external model):** `POST /api/plan/sessions/{id}/critique` runs headless claude on `spec_model` (reuse the `run_judge_cmd` invocation pattern from `evals.py` — cwd=knowledge, spec+plan as temp files): "Premortem: assume this plan FAILED. List the most likely causes; missing tasks/dependencies; criteria that are not testable as written; risks with no owner. ≤8 findings, each: {task_idx|spec_slot, problem, concrete_fix}. Sentinel-fenced JSON." Findings render as ⚠ annotations on the matching plan-editor task cards (extend `planEd*` card rendering) and spec slots. Auto-run on first draft when `plan.critique_enabled`; button to re-run after edits. Findings are advisory — approve is never blocked.
- Re-plan diffing: when revalidate/critique changes the plan, flag changed/added/removed task cards (compare by index+title) — "don't make the user play spot-the-difference."

### Step 8 — Spec travels downstream (`app/server.py`, `app/evals.py`, `app/hermes_dispatch.py`)
On create: write `SPEC.md` (rendered) + `spec.json` into `workspaces/workflow-<id>/attachments/` via the existing attachment mechanism (framing already marks attachments MUST-READ); embed each task's criteria as "Done when: …" lines in its description (already done at draft time — verify they survive `_clamp_wizard_task`); add `spec` path into the SR critic's `_critic_context/context.json` (evals.build_critic_sandbox — copy spec.json in) so the critic verifies against the ORIGINAL contract, not just the task brief; expose spec path to the judge via the N1 type-rubric mechanism's context (optional token). `replan_draft` framing gains the spec as input. `plan_sessions.status='created'`.

### Step 9 — JARVIS + entry points
JARVIS system-control framing (B2 pattern from the SR plan): document `POST /api/plan/sessions` + the triage fields so "JARVIS, plan a project with me" starts a Deep Plan session (voice answers = turns). Deck's "✨ Hand a task to the fleet" honors the recommendation banner. Scheduler-created tasks skip triage (B4 unchanged).

### Step 10 — Gates + docs
verify.sh section (symbols: plan_sessions, /api/plan/sessions, _validate_plan, spec_model, plan.deep_enabled, plan_engine.py exists). New `app/scripts/verify_deep_plan_e2e.py` (~15 checks; stub the PLANNING model via a new `plan.stub` setting that short-circuits the Hermes session turn with canned slot-filling replies — mirror `evals.stub` in evals.py; the judge/critic command-template stubs do NOT apply to session turns — critic check F9): triage heuristics (crafted simple vs complex goals), recommendation payload, session CRUD + resume, slot fill → READY stop rule, draft seeds phase-2 + criteria distribution, orphan-criterion validator fires, premortem stub → annotations payload, spec lands as attachment + in critic context, abandon sweep. Playwright: banner accept/deny, spec pane edit, draft → proposal with annotations. Update `app/CLAUDE.md`.

### Step 11 — Measure (C4 harness arm)
Add a "deep-plan vs quick-plan" comparison to the Appendix C4 benchmark: the complex-task suite rows run both paths (same execution settings), blind-judged by the reference model; also track planning-phase token cost and user-turn count. Expected from the literature: biggest deltas on dependency-heavy, multi-artifact goals; ~zero delta on simple goals (which is why the soft gate defaults to quick).

## 6. Cost & expectations (honest)
Triage: ~5–15k executor tokens (only in the uncertain band). Deep Plan session: 3–6 turns × a few k. Premortem: one judgment-tier call (~5–15k). Total ≈ **$0.10–0.50 per deep-planned goal** — noise next to a 5–10× SR execution, with the entire downstream run steered by a better contract. What this does NOT do: fix mid-execution drift (that's the loop engine's job), or help goals the user themselves can't specify — the interview surfaces requirements, it doesn't invent intent. And per the evidence, expect the quick path to remain correct for the majority of everyday goals; the win is concentrated in exactly the complex tasks where today's single question round under-elicits.

## 7. Primary sources
ClarifyGPT (arxiv 2310.10996, FSE'24) · Ask or Assume? (2603.26233) · Ask-before-Plan (2406.12639, EMNLP'24) · clarification options study (2402.01934) · LLM interviewer limits (2507.02564, 2602.18306) · self-critique degrades plans — Valmeekam & Kambhampati (2310.08118) · LLM-Modulo (ICML'24, 2402.01817) · VerifyLLM (2507.05118) · RouteLLM (2406.18665) · BEST-Route (microsoft/best-route-llm) · router collapse (2602.03478) · plan-and-execute vs ReAct (LangChain planning-agents) · GitHub Spec Kit (github/spec-kit) · Cursor plan mode (cursor.com/blog/plan-mode) · Devin interactive planning (docs.devin.ai) · Claude Code plan mode · HITL approve-with-edits syntheses (StackAI, buildmvpfast).
