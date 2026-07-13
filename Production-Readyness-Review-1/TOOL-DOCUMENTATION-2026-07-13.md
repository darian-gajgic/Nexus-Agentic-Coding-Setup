# NEXUS AGENT OS — TOOL DOCUMENTATION (2026-07-13)

**Purpose.** This document exists so that any future session fixing or improving this tool understands the
PURPOSE of every part before touching it: what each functionality is for, the value it adds today, how it is
currently implemented, how the same capability is built properly per web-researched state-of-the-art and best
practices (mid-2026, cited), and an honest verdict — is it done properly, and if not, what has to change.
Fixes and rebuilds must target the **intended goal**, never merely preserve the current code (owner directive:
treat the codebase as junior-authored; nothing is assumed correct, including its design).

**How to read.**
- Every entry has four fixed fields: *Intended goal & added value* → *Current implementation* → *The proper
  way (web-researched)* → *Verdict* (`PROPER / PARTIAL / NOT-PROPER` + required changes).
- Verdicts are **design-level hypotheses from code reading + research** — the readiness campaign
  (`PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md`) confirms or refutes them at runtime. A PARTIAL verdict's
  change list is a candidate FIX/REBUILD batch, not yet a confirmed one.
- Written at HEAD `2b7200a`, while the **Frontier Judge + Task Management Efficiency Overhaul** was landing
  (commits `571d59b`, `2b7200a`; only e2e-gate edits still uncommitted at writing time). Judge/review entries
  describe the post-overhaul contract and flag old-design remnants explicitly.
  **UPDATE: the overhaul is fully LANDED + pushed** (`f999047` gates/A-B-runbook/report, `5a005de` docs;
  service restarted; all gates green — see the "LANDED addendum" at the top of Cluster D3). Its mechanism
  source of truth is `app/docs/SPEC-JUDGE-LOOP.md` (read alongside this file's D3 verdicts).
- Method: 8 parallel research agents, one per cluster; every entry backed by repo code reading plus ≥2 web
  lookups; citations inline as [title — URL (accessed 2026-07-13)]. Security topics are deliberately absent
  (separate security-sweep campaign owns them).

**The product's 10 goals** (every entry maps to these):
G1 organized UI/overview + productivity workflows · G2 fully automated parameter setting (a non-IT user names
a task and gets max performance — never stuck, no token waste) · G3 full manual control, full visibility,
teach/correct so mistakes don't repeat · G4 learns/memorizes/recaps its own work, asks when unsure, adapts to
the user · G5 frontier techniques that fix LLM weaknesses (max quality per $) · G6 self-adjusting economics
(Eco/Balanced/Smart + Super Result), each mode beating normal model use · G7 broad task-type coverage with
per-type best-practice workflows · G8 productivity tools (code review, PDF, image, transcription, notes)
properly implemented and automatically used · G9 integrated JARVIS voice assistant · G10 multi-user company
deployment with shared learning + a modern, impressive GUI.

## Verdict summary (30 functionalities)

| # | Functionality | Cluster | Verdict |
|---|---|---|---|
| 1 | Task lifecycle & dispatch engine | D1 | PARTIAL |
| 2 | Workflows/DAGs + house coding pipeline + replanning | D1 | PARTIAL |
| 3 | Task wizard + automated parameter derivation | D2 | PARTIAL |
| 4 | Deep Plan mode | D2 | PARTIAL |
| 5 | Scheduler | D2 | PARTIAL |
| 6 | Frontier judge loop (post-overhaul) | D3 | PARTIAL |
| 7 | Grounded critic + Super Result + escalation | D3 | PARTIAL |
| 8 | Economic modes + cost governance & visibility | D3 | PARTIAL |
| 9 | Semantic/agent memory (mem0 + qdrant + scopes) | D4 | PARTIAL |
| 10 | Wins/Lessons feedback ledger + framing injection | D4 | PARTIAL |
| 11 | Lesson distillation + golden exemplars | D4 | PARTIAL |
| 12 | Self-recap & uncertainty | D4 | PARTIAL |
| 13 | JARVIS voice assistant pipeline | D5 | PARTIAL |
| 14 | Hologram avatar + visemes | D5 | PARTIAL |
| 15 | Vision (analysis + generation) | D5 | PARTIAL |
| 16 | Dictation (system-wide voice typing) | D5 | **PROPER** |
| 17 | Meetings intelligence | D5 | PARTIAL |
| 18 | Code review v2 (in-app diff review) | D6 | PARTIAL |
| 19 | Git integration: worktrees, artifacts, PR, per-user GitHub | D6 | PARTIAL |
| 20 | App preview (▶ Test app / Test project) | D6 | PARTIAL |
| 21 | Document & artifact generation (PDF/docx/pptx/xlsx) | D6 | PARTIAL |
| 22 | Multi-user accounts & per-user environments | D7 | PARTIAL |
| 23 | Onboarding (business-brain wizard) | D7 | PARTIAL |
| 24 | Settings v2 + credentials + model registry | D7 | PARTIAL |
| 25 | Notes + Known Issues + User Manual + guided tour | D7 | PARTIAL |
| 26 | Observability & usage | D7 | PARTIAL |
| 27 | Hermes integration seam | D8 | PARTIAL |
| 28 | Frontend architecture | D8 | PARTIAL |
| 29 | Data layer | D8 | PARTIAL |
| 30 | Service topology & ops | D8 | PARTIAL |

**Distribution: 1 PROPER · 29 PARTIAL · 0 NOT-PROPER.** Read that as: no subsystem needs a from-scratch
rewrite of its core idea — the architecture skeleton repeatedly matches researched best practice — but almost
every subsystem is missing the layer that would make it trustworthy and complete. The detailed change lists
live in each entry's Verdict.

## Cross-cutting themes (what the 30 entries agree on)

1. **Sound skeleton, missing verification layer.** The core designs — CAS-claimed worker queue, worktree
   isolation, evaluator-optimizer judge cascade, per-user config layering, VRAM orchestration with killable
   workers — independently match best practice. What's absent nearly everywhere is the layer that PROVES
   behavior: no judge-vs-operator calibration metric, learning loops have writers and readers but no
   *verifier* (nothing measures whether an injected lesson changed behavior), no output validation on
   generated documents, TCP-not-HTTP readiness probes, and the A/B value evidence (added-value benchmark)
   still unrun. The tool enforces quality and cost policy it cannot yet prove is calibrated.
2. **Missing invariants, compensated by sweeps.** `dispatch_state` has no single transition authority — ~6
   modules write states via free-form UPDATEs, and the five recovery mechanisms (reconciler, stranded-claims,
   zombie detector, boot reconcile, runaway ceiling) are incident-driven compensation. Same pattern:
   stub/test-hook settings (`judge.cmd`, `super.critic_cmd`, `plan.stub`, …) still lack the env-gate +
   boot-clear hardening that only `dispatch.stub_stream` received after the third leak incident;
   `remove_worktree()` has zero call sites (worktrees accumulate forever in client repos).
3. **Reproducibility rot between the live machine and the repo.** `app/requirements.txt` omits the entire
   document/render stack the dispatch framing promises (reportlab, pypdf, python-docx, openpyxl, python-pptx,
   pillow, markdown, pygments) — a fresh install from the repo's own runbook breaks every binary-deliverable
   task; `setup/hermes/mem0.json` still ships `max_tokens: 2000`, re-introducing the fixed dropped-writes bug
   on any fresh install; the Usage tab prices GLM spend from a hardcoded table that contradicts the frontier
   ledger's `cost.model_prices` by up to ~9×.
4. **One-generation-stale local-model tier (voice/vision).** The orchestration (gpu_lock, eviction, idle
   unload) is best-practice; the models aren't: energy-floor VAD where Silero is standard, batch
   faster-whisper large-v3 where Parakeet-TDT-v3 is faster AND more accurate for English, Piper where
   Kokoro-82M is the bar — and `kokoro-onnx` runs on onnxruntime without torch, likely voiding the documented
   py3.11-worker blocker — SigLIP v1 with SigLIP 2 drop-in available, SDXL-Turbo two generations behind
   FLUX.1-schnell on 12 GB.
5. **The economics rest on unmeasured heuristics.** Model routing is unvalidated lexical keyword matching
   (English keywords — a German-market user's briefs risk silent mis-routing), "Balanced/Eco best value"
   labels are self-declared heuristics pending the unrun benchmark, and the two price tables disagree. The
   G6 promise ("each mode beats normal model use") is currently unprovable from inside the product.
6. **Where full rebuilds are NOT needed:** nothing earned NOT-PROPER. The change lists concentrate on
   (a) centralizing invariants (state transitions, stub hygiene, worktree lifecycle), (b) adding
   measurement/validation layers, (c) closing reproducibility gaps, (d) refreshing the local-model tier, and
   (e) finishing follow-through on otherwise-SOTA designs (finding-resolution loop, converter tier for
   documents, HTTP readiness, package-manager detection).

---
## Cluster D1 — Task Execution Core

### Task lifecycle & dispatch engine
**Intended goal & added value** — Turns a kanban card into a real, unattended LLM work session and
guarantees it finishes, blocks visibly, or stays recoverable — never silently lost. Serves G2 (a named
task runs to completion with budgets/quota/self-heal, no babysitting), G5+G6 (resume-not-restart harvest
never re-pays for finished work; per-task/daily budgets, quota backoff, per-model concurrency slots),
G3 (stop/retry/bulk ops, live preview, activity feed), G1 (board + dispatch states visible), G10
(user-scoped tasks). It is the load-bearing layer every other feature (loops, judge, SR, workflows) drives.

**Current implementation** — Kanban `tasks.status`: backlog→todo→in_progress→review→done (+`archived`);
the column is `review`, not `in_review` (app/database.py:71; app/hermes_dispatch.py:1560). Orthogonal
`tasks.dispatch_state` (database.py:241): none→queued→dispatching→streaming→finalizing→
completed|failed|blocked_budget|blocked_quota|cancelled (active set at app/server.py:4258). Dispatch is
queue-only: `POST /api/tasks/{id}/dispatch` (server.py:4261) 409s on an active dispatch, claims via the
single CAS `db.claim_task_cas` (database.py:1122 — one `UPDATE … WHERE status IN ('backlog','todo')`),
then `start_dispatch` (hermes_dispatch.py:2123) only marks 'queued'; the per-agent `app/worker.py` lane is
the sole executor. `_find_work` (worker.py:81) prioritizes: interrupted dispatch (heartbeat stale >90s →
resume) → queued → cleared blocks → dep- and slot-gated auto-claim. `run_task_dispatch`
(hermes_dispatch.py:1802): cancel check → orphan ladder (`orphan_run_state`:1638 finished→`_try_harvest`
free recovery / active→wait / dead→continue-turn / gone→fresh) → `check_budgets`:478 → one Hermes session
per task → `build_framing` as ephemeral system_message → `stream_turn`:208 with wall-clock cap (14400s) +
stall guard (900s silence); a cut turn is NON-terminal (:2046 — detach/wait/harvest; runaway ceiling 2× cap,
worker.py:169). `_finalize_result`:1490 books tokens, writes deliverable.md, files high-stakes approvals.
Stop (`_request_stop` server.py:4317) sets `cancel_requested` first, then immediate park or the executor's
~30s cancel poll → `_finalize_cancel`:1447; retry (`_retry_task` server.py:6179) versions deliverables,
drains [F#] comments, grants bounded budget slices (0.5× original, 2× ceiling → decision card), escalates
light-tier→strong on judge REVISE. Self-heal: watchdog.py 10s sweep — dead/stuck restart with PID-recycle
check (:71), circuit breaker (20→retire), boot grace, stranded-claim release (1h), the reconciler
(hermes_dispatch.py:363, 600s stale → re-queue, session kept if the orphan run is live/harvestable), and a
log-only zombie-dispatch detector (watchdog.py:227). SQLite runs WAL + busy_timeout=10000 (database.py:19-25).

**The proper way (web-researched)** — A DB-backed queue should claim atomically in a single UPDATE, lease
work via a visibility timeout, and guard completion with a per-delivery counter so a timed-out worker A
cannot finalize a job re-delivered to worker B; crashed workers' jobs auto-return to the queue [Building a
Durable Message Queue on SQLite for AI Agent Orchestration —
https://dev.to/minnzen/building-a-durable-message-queue-on-sqlite-for-ai-agent-orchestration-335m (accessed
2026-07-13)]. WAL + busy_timeout is the accepted SQLite posture; single-machine SQLite queues are legitimate
at this throughput [A SQLite Background Job System — https://jasongorman.uk/writing/sqlite-background-job-system/
(accessed 2026-07-13)]. Durable-execution practice: long activities heartbeat against ONE
`heartbeat_timeout` so the server retries on another worker within one window, carrying heartbeat details so
the retry RESUMES rather than restarts [Activity Execution — Temporal docs —
https://docs.temporal.io/activity-execution (accessed 2026-07-13)]; at-least-once delivery is the default,
so every side effect needs idempotency (keys, check-before-act) [What is idempotency? — Temporal —
https://temporal.io/blog/idempotency-and-durable-execution (accessed 2026-07-13)]; and state machines whose
transitions are hand-written across many components with no single authority are the canonical failure mode
durable-execution engines exist to replace [Temporal: Beyond State Machines —
https://temporal.io/blog/temporal-replaces-state-machines-for-distributed-applications (accessed 2026-07-13)].
The harvest idea (recover an orphaned finished run instead of re-running) matches the heartbeat-details
resume pattern and is genuinely strong practice for long LLM sessions.

**Verdict: PARTIAL** — the claim/lease/harvest core independently reinvents the researched pattern well
(CAS claim, WAL, heartbeats, resume-not-restart), but state transitions have no single authority and
recovery is five accreted incident-patches instead of one lease invariant.
- Centralize `dispatch_state` transitions behind one guarded writer with a legal-transition CAS
  (`UPDATE … WHERE dispatch_state IN (<legal prev>)`): today `_set_task(**fields)` (hermes_dispatch.py:1352)
  plus raw UPDATEs in worker.py:174, watchdog, the reconciler and server routes each write any state from
  any prior state — the scattered-state-machine anti-pattern [Temporal beyond-state-machines], and the root
  reason the compensating-sweep fleet exists.
- Validate `TaskUpdate.status` (server.py:420 — a free, unchecked string) against the enum and refuse (or
  route to /stop) status changes while `dispatch_state` is active: the "'backlog' task stuck at 'streaming'"
  class the reconciler exists to mop up (hermes_dispatch.py:352 comment) is caused by this open PATCH door.
- Collapse the four recovery thresholds (worker resume 90s, reconciler 600s, zombie detector 600s log-only,
  stranded claims 3600s) into ONE lease deadline on the dispatch row with ONE enforcing reaper — the single
  visibility-timeout model [dev.to SQLite queue; Temporal activity heartbeat]; the log-only zombie detector
  (watchdog.py:227) is an admission that detection and enforcement live in different places today.
- Add a per-delivery fencing token to the finalize tail (the `received`-counter guard from [dev.to SQLite
  queue]): a superseded executor reviving after the reconciler re-queued its task can still run
  `_finalize_result` — token booking and the completed-flip are not conditioned on owning the newest
  dispatch row, and at-least-once semantics make this double-finalize reachable [Temporal idempotency].

### Workflows/DAGs + house coding pipeline + replanning
**Intended goal & added value** — Multi-stage projects as dependency-wired task DAGs so a plain-language
goal becomes a best-practice pipeline automatically: coding goals get the enforced house pipeline
(spec&plan → implement+tests → review → fix → acceptance verification); content/research get their own
shapes. Serves G7 (per-type workflows), G5 (review/verify gates + fan-out fix LLM weaknesses), G2
(deterministic repair yields a runnable DAG even from bad model wiring), G3+G4 (operator-gated replanning,
plan editor, cross-stage DECISIONS.md memory), G1 (Projects rollups + workflow ledger/review/preview).

**Current implementation** — `workflows` table + `tasks.workflow_id` + `tasks.depends_on` (JSON id list in
a TEXT column, database.py:257-258). Gating: `deps_satisfied` (hermes_dispatch.py:551) requires every dep
`status=='done'`, FAIL-CLOSED on dangling ids; enforced at worker claim (worker.py:101,135) and manual
dispatch (409 naming the blockers, server.py:4302); task delete scrubs `depends_on` via `LIKE '%id%'`
(server.py:939). Input passing: `build_framing` (hermes_dispatch.py:1163-1181) injects direct predecessors'
`deliverable.md` paths (capped 8) as MUST-READ INPUT plus the flock-guarded per-project `DECISIONS.md`
(`harvest_decisions`:1266). `_repair_workflow` (server.py:7310) enforces the house pipeline and never
trusts model wiring: earlier-index invariant (acyclic by construction), stringified-index coercion (:7344),
restores the implement→spec edge (:7418 — a live 2026-07-11 incident), inserts missing review/fix gates,
re-appends the acceptance-verifier as unique high-stakes sink (:7480-7496), enforces the fan-out reconciler
(:7500), chains orphans, sequential-chain fallback on any exception (:7533), Eco collapse with a
high-stakes risk floor (:7373); repairs are surfaced to the operator. Cycle guard on PATCH deps
(`_deps_would_cycle`, server.py:881); `GET /api/workflows/{id}` orders topologically and surfaces cycles
last instead of hiding them (:9020-9034). Replanning is three deliberate gates: (1)
`loop_engine._sweep_replan_detection` (loop_engine.py:1160, 20s sweep) flags `replan='needed'` ONLY on
terminal `dispatch_state='failed'` or final-verifier FAIL with no fix round left, re-arming per new failed
task (optional auto-draft `replan.auto_draft`); (2) `POST /replan/draft` (server.py:9316) drafts in a
background session over `_replan_context` (DAG state + failure evidence + original SPEC) then
`_repair_workflow`; (3) `POST /replan/apply` (server.py:9336) 409s while any stage executes, creates
recovery tasks first with rollback on failure, only then archives the superseded remainder, roots inherit
every DONE task as input deps, loop rounds reset under `_CFG_LOCK`. Workflow-level routes: ledger
(server.py:4204), aggregated review (:10634), project preview (`/api/workflows/{id}/app*`, :4700-4755),
attachments, cascade delete with a live-dispatch 409 (:9154).

**The proper way (web-researched)** — Anthropic's canonical guidance builds exactly this shape: "prompt
chaining" with programmatic gates between steps, "orchestrator-workers" for dynamic decomposition,
"evaluator-optimizer" loops as review stages, agents that "pause for human feedback at checkpoints or when
encountering blockers", and ground truth from the environment at each step [Building Effective Agents —
Anthropic — https://www.anthropic.com/research/building-effective-agents (accessed 2026-07-13)].
Plan-and-execute practice separates planner/executor and adds an explicit replanner that runs AFTER EACH
step ("respond or generate a follow-up plan"), not only on hard failure; the LLMCompiler variant represents
the plan as a DAG whose task-fetching unit schedules a task the moment its dependencies are satisfied and
passes predecessor OUTPUTS as typed variables (`${1}`-style substitution) rather than prose pointers
[Plan-and-Execute Agents — LangChain blog — https://www.langchain.com/blog/planning-agents (accessed
2026-07-13)]. Current orchestration research criticizes end-only evaluation ("evaluates results only after
the entire graph completes with no mid-execution adaptation") and pushes mid-execution gating/adaptation of
running plans [KAIJU: An Executive Kernel for Intent-Gated Execution of LLM Agents —
https://arxiv.org/html/2604.02375 (accessed 2026-07-13)]. Deterministic server-side validation of a
model-proposed plan — enforcement separated from generation — is aligned with all three sources.

**Verdict: PARTIAL** — pipeline enforcement and human-gated replanning genuinely match the researched
patterns (gates, checkpoints, deterministic non-trust of model wiring), but the DAG is claim-time-only:
nothing re-evaluates dependents or the plan once stages start moving.
- Add downstream invalidation when a `done` predecessor is reworked: `_retry_task` (server.py:6179) flips
  only the task itself to todo — dependents that already claimed/finished keep building on the superseded
  deliverable because `deps_satisfied` (hermes_dispatch.py:551) is checked only at claim time; dataflow DAG
  practice re-schedules consumers of changed inputs [LangChain planning-agents]. Minimum: park unclaimed
  dependents + open a replan checkpoint listing affected done dependents.
- Trigger plan reassessment on milestone success, not only terminal failure: `_sweep_replan_detection`
  (loop_engine.py:1181-1198) fires solely on `dispatch_state='failed'` or verifier FAIL — a stage that
  "succeeded" in the wrong direction never re-opens the plan; plan-and-execute replans after each step
  [LangChain planning-agents], and end-only evaluation is the named weakness [KAIJU]. A deterministic
  per-completion check (stage output vs SPEC criteria echo) would fit the existing no-LLM detection budget.
- Replace prose-path handoff with a structured output contract: predecessors are injected as "read these
  deliverable.md paths" (hermes_dispatch.py:1171) with no machine-readable outputs manifest, so a stage
  cannot cheaply verify it consumed the right artifacts — approximate LLMCompiler/ReWOO variable passing
  with an `outputs.json` per stage referenced by the framing [LangChain planning-agents].
- Promote `depends_on` from JSON TEXT + `LIKE '%id%'` scrubs (server.py:939; approval expiry likewise
  string-matches serialized JSON, server.py:9410) to a real edge table (or JSON1-indexed queries): the graph
  is re-parsed per candidate per 2s worker tick and every graph mutation depends on string matching against
  a serialization format — fragile and unindexable [dev.to SQLite queue: queue/graph state belongs in
  first-class relational columns].
## Cluster D2 — Automation Brain (Wizard, Routing, Deep Plan, Scheduler)

### Task wizard + automated parameter derivation
**Intended goal & added value** — The core G2 mechanism: a non-IT user types one plain-language goal and
gets back a fully parameterized task or dependency-wired project — specialist, model, budget, stakes,
quality gates, pipeline shape all derived. Serves G2 (max performance from one prompt), G6 (Eco/Balanced/
Smart axes set every knob), G5 (cheap-first routing + judge-triggered escalation cascade), G3 (plan editor
override + 🧭 routing-reason visibility), G7 (per-goal-family pipeline templates). Value today: "build X"
becomes the house 5-stage coding pipeline with locked review/verify gates instead of a bare one-liner.

**Current implementation** — `POST /api/tasks/wizard` (`app/server.py:task_wizard`, ~7694): two-phase —
phase 1 may return ONE round of ≤6 clarifying questions (options with pros/cons, exactly one ★ recommended,
skippable default); phase 2 folds answers into the goal and forces a plan (one silent retry on malformed
JSON, then 502). The goal is fenced as data (`<<<GOAL`) after a live incident where the wizard executed the
work. `_task_wizard_framing` (~6907) embeds per-family templates (5-stage coding, research→create, SR
fan-out shapes); `_repair_workflow` (~7310) deterministically distrusts model wiring: earlier-index
invariant (acyclic by construction), mandatory review/fix/verifier gates appended, verifier normalized to
unique sink, orphan chaining, sequential-chain fallback. `_clamp_wizard_task` whitelists specialists/models,
enforces the dev-stage floor and Eco light-tier floor. `autopilot.derive` (`app/autopilot.py`) is the pure
single source mapping involvement×spend → preference/mode/SR/fan-out/round caps/judge scope/budget ×0.5-2/
pipeline depth, with per-type budget baselines (`hermes_dispatch.type_setting`) and `_feature_present`-staged
derivations. `routing.select_model_for_task` (`app/routing.py:271`) is deliberately deterministic (no LLM at
create time): mechanical regex → mechanical tier, <160-char general-domain → easy tier, "Best for"/"Avoid
for" description phrases at ≥0.6 token overlap (avoid = veto), high-stakes/`smart` never below the strong
default; reason persisted to `tasks.model_reason` (🧭), applied at the single create choke point
(`server.py:714`). L1 telemetry (`routing.record_outcome` + `sweep_stats`) proposes threshold changes as
approval cards; `learned_params` fingerprint-invalidated on tier rotation. `plan_engine.recommend_spend`
preselects the spend card; `hermes_dispatch.session_effort_for_task` (:732) bridges per-task reasoning
effort. Manual override: `planEd*` editor (`app/static/app.js` ~10637, gates locked) → `/wizard/revalidate`.

**The proper way (web-researched)** — Mid-2026 SOTA model routing is *learned*, not lexical: RouteLLM-class
routers trained on preference data reach ~85% cost reduction at ~95% of GPT-4 quality, and MixLLM/FrugalGPT
cascades escalate cheap-first on confidence signals [LLM Model Routing: Cheapest Capable Model Per Query —
https://leanlm.ai/blog/llm-model-routing (accessed 2026-07-13)]. The 2026 survey taxonomizes routers by when
the decision is made (pre-inference vs cascade), what feeds it (query features, past performance) and how
(rules → classifiers → RL), with keyword rules the weakest tier [Dynamic Model Routing and Cascading for
Efficient LLM Inference: A Survey — https://arxiv.org/html/2603.04445v2 (accessed 2026-07-13)]. Production
guidance: measure router accuracy on YOUR traffic; ship per-tier quality/escalation observability, not just
cost dashboards [LLM Model Routing in 2026: Cost-Quality Optimization — https://www.digitalapplied.com/blog/
llm-model-routing-2026-cost-quality-optimization-engineering-guide (accessed 2026-07-13)]. For one-prompt
auto-configuration UX, Manus-class lessons: keep derivation deterministic, context scoped, with explicit
loop guards/caps — unbounded auto-config is where agents loop and burn tokens [Context Engineering for AI
Agents: Lessons from Building Manus — https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-
Building-Manus (accessed 2026-07-13)]; [Debugging AI Autonomy: What I Learned From a Failing Manus Agent
Loop — https://medium.com/@connect.hashblock/debugging-ai-autonomy-what-i-learned-from-a-failing-manus-
agent-loop-408e8c0a5e5a (accessed 2026-07-13)]. Anthropic's canonical advice — predefined workflows when
task structure is known, strict data models on model I/O — matches the deterministic repair layer here
[Building Effective AI Agents — https://www.anthropic.com/research/building-effective-agents (2026-07-13)].

**Verdict: PARTIAL** — derivation/repair/override architecture is genuinely best-practice-shaped
(deterministic scaffolding, explainable routing, FrugalGPT-style cascade), but the router core is
unvalidated keyword matching and the JSON contract is enforced by string search.
- Replace/augment the lexical router: `routing._phrase_matches` (0.6 token overlap on operator prose) and
  the `len(text)<160 → easy` heuristic have zero measured accuracy — `sweep_stats`'s own warning admits
  "cost dashboards without quality-per-route are misleading." Run the deferred Phase-8 benchmark, add
  per-route quality telemetry, or move to an embedding/classifier router (survey + 2026 guide above).
- Fix the language gap: `MECHANICAL_RE` knows German verbs but `_significant_tokens` "Best for" matching is
  English-token-based — a German brief (supported input per `_task_wizard_framing`) can never
  description-match a model. Normalize/translate or use embedding similarity.
- Enforce the plan schema: `task_wizard._call` parses via `find("{")/rfind("}")` + one silent retry then
  502 — use schema-constrained output or a validating repair parser (Anthropic strict-data-models guidance).
- Kill the hand-mirrored constant: `routing.py:233` admits `app.js` duplicates `DEV_SPECIALISTS` ("keep
  them in sync") — serve the set from the API; it was already "one edit away from silently disagreeing."
- Divergence sampling is async-cached (`_wizard_triage` spawns a thread), so the FIRST wizard call usually
  renders triage without it — surface "still sampling" or await it in phase 2; ClarifyGPT-style signals
  only help if present at decision time.

### Deep Plan mode
**Intended goal & added value** — The plan-then-execute layer for complex/ambiguous goals: instead of
one-shot planning, the system interviews the operator, fills a structured SPEC, drafts the DAG from it,
premortems the draft with an external model, and ships the SPEC downstream to executors/critic/judge.
Serves G5 (planning + premortem fix one-shot LLM planning weakness), G4 (asks when unsure — gated, capped
interview), G2 (an ambiguous goal becomes a conversation, not a guess), G3 (live editable spec pane +
manual revise rounds), G7 (four per-family spec templates).

**Current implementation** — `app/plan_engine.py` is the deterministic core: `triage_heuristics`
(length/vague-referent/artifact-count/cross-domain/dependency/blast-radius signals), `divergence` (Jaccard
disagreement across N cheap sampled draft plans — LLM self-rating explicitly locked out, §3.1), `recommend`
soft gate (plan.recommend, spend override). `/api/plan/sessions` CRUD (`app/server.py` ~8121-8236): start
creates a row + dedicated Hermes session and runs the opening turn; `interview_framing` scaffolds per-family
`SPEC_TEMPLATES` (required slots gate READY, ≤max questions/turn with 3-5 ★ options, tools-off block, turn
cap); `parse_turn` defensively extracts the JSON reply; `PATCH /spec` = direct slot edits; stale sessions
swept hourly (7d). `/draft` (`plan_session_draft` ~8512) seeds the phase-2 wizard framing with the SPEC
contract, runs the SAME `_repair_workflow`, stamps `FAMILY_DELIVERABLE_TYPE`, then `_distribute_criteria`
guarantees every acceptance criterion lands verbatim on the best-matching task; `_validate_plan` (~8274)
emits advisory warnings (fuzzy `_criterion_covered` ≥60% token match, output-ref-without-dep, near-dup
titles, budget sanity). `/critique` = ONE external premortem on the `spec_model` purpose; `/revise` folds
findings back (`_plan_revise_raw` → same deterministic pipeline; `_preserve_task_fields` keeps operator
knobs; ≤3 operator questions → `notes` slot; one auto round via plan.auto_revise). SPEC.md + spec.json land
in attachments and reach the critic sandbox, judge (`JUDGE_SPEC`) and replan drafts; `repo_path` →
`_plan_repo_block` grounds interview + draft + revise in the real repo. Verified holes:
`_CRITERIA_SLOT["content"] = None` (content plans carry NO criteria list → `_distribute_criteria` and the
orphan-criterion check no-op for that family), and single-task drafts skip critique/revise entirely.

**The proper way (web-researched)** — This is the spec-driven-development pattern that dominated 2025-26
agent tooling: GitHub Spec Kit's Specify→Plan→Tasks→Implement flow treats the spec as the primary artifact
traveling with the work, with reported ~3-10× first-pass success on non-trivial tasks [Spec-driven
development with AI: Get started with a new open source toolkit — https://github.blog/ai-and-ml/
generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/ (accessed
2026-07-13)]; [GitHub Spec Kit — https://github.github.com/spec-kit/ (accessed 2026-07-13)]. AWS Kiro gates
all code behind Requirements→Design→Tasks and uses EARS notation to make every requirement testable;
Fowler's comparison of Kiro/spec-kit/Tessl stresses the spec as a reviewable, versioned artifact rather
than a one-shot prompt [Understanding Spec-Driven-Development: Kiro, spec-kit, and Tessl —
https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html (accessed 2026-07-13)]. The interview +
divergence design is validated research: ClarifyGPT detects ambiguity via consistency checks across sampled
solutions, then asks targeted clarifying questions — lifting GPT-4 Pass@1 from ~71% to ~81% [ClarifyGPT:
Empowering LLM-based Code Generation with Intention Clarification — https://arxiv.org/abs/2310.10996
(accessed 2026-07-13)]. Anthropic's guidance backs the shape: explicit checkpoints, human gates on plans,
strict I/O contracts [Building Effective AI Agents — https://www.anthropic.com/research/
building-effective-agents (accessed 2026-07-13)].

**Verdict: PARTIAL** — the multi-task flow is authentically SOTA-shaped (triage → gated interview → spec →
draft → external premortem → revise → spec-travels matches Spec Kit/Kiro/ClarifyGPT point for point), but
coverage holes exclude exactly the users/goals G2 and G7 promise.
- Give the content family a criteria backbone: `plan_engine._CRITERIA_SLOT` maps content→None, so the
  coverage guarantee and orphan-criterion validator silently no-op for the family non-technical users touch
  most — SDD practice (Spec Kit/Kiro EARS) makes a testable "definition of done" list the backbone of EVERY
  spec; add a required list slot and wire it into `criteria_slot`.
- Run verification on single-task drafts: the `/draft` `type:"task"` path gets no `_validate_plan`
  annotations, no `/critique`, no `/revise` (self-documented limitation) — a high-stakes single task gets
  zero plan-level premortem; at minimum run the validators + one critique pass on the brief.
- Constrain the interview contract: `parse_turn` brace-searches unconstrained JSON; a malformed turn
  silently drops `spec_updates` (progress loss, no operator signal) — schema-enforce the output per
  Anthropic's strict-data-models guidance, or surface "this turn could not be parsed."
- Version the SPEC: revise rounds overwrite `spec_json` in place; Spec Kit/Kiro treat the spec as a
  versioned reviewable artifact — persist per-round snapshots so the operator can diff what a revise
  changed (`planEdComputeDiff` exists for tasks; the spec has no equivalent).

### Scheduler
**Intended goal & added value** — Recurring automation: cron-style jobs that mint real tasks on the board
so periodic work (reports, checks, content) runs through the exact same claim/dispatch/quality machinery as
manual tasks. Serves G8 (productivity automation), G2/G6 (the B4 `task_template` passes SR/type/autopilot/
spend presets so recurring high-value jobs get the quality+budget machinery automatically), G1 (CRUD UI in
the Agentic view). Value today: a creation-validated cron reliably produces properly-parameterized tasks —
before the `_trigger` fix, firing only wrote a cosmetic log line while `run_count` grew.

**Current implementation** — `app/scheduler.py`: hand-rolled 5-field cron parser (`*`, `*/N`, values, comma
lists, ranges `a-b[/N]`, dow 7→Sunday) raising `ValueError` at parse time so unmatchable jobs are rejected
at creation (`scheduler_create`, `app/server.py:4091` → 400); `next_run` scans minute-by-minute up to 366
days on NAIVE LOCAL time (`dt.datetime.fromtimestamp`, no tz handling); `scheduler_loop` daemon thread
ticks every 15s and fires enabled jobs with `next_run <= now` — after downtime each job therefore
catch-up-fires exactly once (implicit, undocumented policy). `_trigger` (:100) creates a REAL `todo` task
via raw INSERT owned by `auth.DEFAULT_USER_ID`, normalizing template axes + rule-4 budget through the SAME
`autopilot.preset_fields` as the API path (the D5 fix — scheduled Smart/Eco jobs used to get unscaled
budgets), syncing the SR loop via `server._sync_super_result_loop`, updating
`last_run/next_run/run_count/last_status`. API: GET/POST/PATCH/DELETE `/api/scheduler`
(server.py:4084-4157), all admin-only (`scheduled_jobs` is a global table); PATCH supports ONLY `enabled`.
The loop thread moonlights as the app's maintenance runner (hourly critic-sandbox sweep, plan-session
sweep, agent-memory consolidation — the last detached to a spawned thread after it blocked cron firing for
minutes, comment at scheduler.py:196-199). Verified gaps: no overlap/instance guard (an every-minute job
keeps minting tasks regardless of prior ones still open); `_trigger`'s raw INSERT bypasses
`routing.select_model_for_task` (no `model`/`model_reason` columns), unlike `POST /api/tasks`.

**The proper way (web-researched)** — Standard guidance is to not hand-roll in-app scheduling: mature
libraries (APScheduler, croniter) provide tested parsing, timezone-aware triggers, and — critically —
explicit `misfire_grace_time` (missed-run policy), `coalesce` (collapse a missed-run backlog into one), and
`max_instances` (prevent overlapping executions) [Job Scheduling in Python with APScheduler —
https://betterstack.com/community/guides/scaling-python/apscheduler-scheduled-tasks/ (accessed 2026-07-13)];
[User guide — APScheduler 3.x documentation — https://apscheduler.readthedocs.io/en/3.x/userguide.html
(accessed 2026-07-13)]. Scheduling on naive local time is a known DST trap — jobs double-fire or never fire
across transitions; the fix is UTC or tz-aware computation, and even mature libraries have documented DST
edge cases, making hand-rolled naive-local strictly worse [DST transitions cause APScheduler to incorrectly
calculate next trigger times — https://github.com/agronholm/apscheduler/issues/529 (accessed 2026-07-13)];
[How Debian Cron Handles DST Transitions — https://blog.healthchecks.io/2021/10/how-debian-cron-handles-
dst-transitions/ (accessed 2026-07-13)]. Product-grade agent schedulers shipped in 2026 set the UX bar:
per-user scheduled tasks with in-place editing, run history, isolated sessions, and hard caps against
runaway load (ChatGPT scheduled tasks cap at 15/user; Claude Code scheduled tasks/routines are per-user and
permission-controlled) [Run prompts on a schedule — Claude Code Docs — https://code.claude.com/docs/en/
scheduled-tasks (accessed 2026-07-13)]; [ChatGPT Gets Scheduled Tasks — https://enterprisedna.co/resources/
news/openai-chatgpt-scheduled-tasks-autonomous-business-automation-2026/ (accessed 2026-07-13)].

**Verdict: PARTIAL** — minting real tasks through the normal flow with creation-time cron validation and
preset parity is the right core, but it lacks several behaviors every standard scheduler ships.
- Adopt croniter (or APScheduler triggers) with tz-aware UTC computation — `next_run`'s naive-local minute
  scan double-fires/skips at DST transitions and burns up to ~527k iterations for rare expressions
  (croniter/APScheduler DST evidence above).
- Add overlap/pileup control: nothing stops a `*/1` job from minting unbounded tasks while earlier ones sit
  unclaimed — a leaked every-minute job flooded the board with ~2.9k tasks on 2026-07-10 (recorded incident,
  project memory `e2e-scheduler-job-leak`); implement skip-if-previous-open or a per-job open-task cap
  (APScheduler `max_instances`/`coalesce`; ChatGPT's 15-task cap is the product analogue).
- Make the misfire policy explicit and configurable (catch-up once vs skip-to-next) instead of the silent
  `next_run <= now` catch-up fire after downtime (`misfire_grace_time` concept).
- Extend PATCH beyond `enabled` (`scheduler_update`, server.py:4137): editing name/cron/action/template
  requires delete+recreate today, losing `run_count`/history — 2026 agent schedulers edit in place.
- Route `_trigger` through the same create choke point as `POST /api/tasks` so scheduled tasks get
  `select_model_for_task` + `model_reason` (G2/G6 economics currently skip recurring work), and add
  per-user jobs (global admin-only today — G10 gap; Claude/ChatGPT schedulers are per-user).
- Split the maintenance sweeps out of the trigger thread into their own timer — the agent-memory sweep
  already delayed cron firing once (comment in `scheduler_loop`); a scheduler tick should only schedule.
## Cluster D3 — Quality Stack & Economics

All paths relative to /home/sinep/Nexus-Agentic-Coding-Setup. The judge/economics overhaul ("Frontier Judge + Task Management Efficiency Overhaul", ~/.claude/plans/check-if-the-functionallity-rippling-stallman.md) is **landing 2026-07-13**: mechanics committed in 571d59b (judge-loop) + 2b7200a (mode-ladder); its gates (`app/scripts/verify_judge_loop_e2e.py` new, `verify_mode_coherence_e2e.py` +93 lines) are still uncommitted in the tree. Entries below document the post-overhaul target design and flag pre-overhaul remnants where visible.

> **LANDED addendum (2026-07-13, post-writing — supersedes the "landing/uncommitted" stamps in this cluster):**
> the overhaul is fully committed + pushed (`571d59b` mechanics → `2b7200a` mode-ladder/review-UX →
> `f999047` gates + A/B runbook + report → `5a005de` docs) and the service was restarted on it (~03:12).
> All gates green at HEAD: verify.sh **482**, `verify_judge_loop_e2e.py` **41/41** (new),
> mode-coherence **47/47**, autopilot **72/72**, Super Result **90/90**, block2 **48/48 + 21/21**.
> **Canonical mechanism reference for reviewers: `app/docs/SPEC-JUDGE-LOOP.md`** — full cascade, state
> inventory, settings table (§10), the §11 INVARIANTS list (changes must not break these), verification map
> (§12), and §13 recorded deviations/backlog. Why-evidence: repo `IMPLEMENTATION-REPORT-JUDGE-LOOP-2026-07-13.md`.
> A/B replay protocol: `benchmarks/judge-loop-ab/RUNBOOK.md` — **not yet run** (paid, operator-gated).
> Two findings below are now RECORDED deviations rather than silent drift (SPEC §13): the dropped pre-gate
> self-score check (deliberate — false-positive pre-gate retries cost a GLM round) and `judge.auto_scope`
> keeping default `high_stakes` (profiles govern; the global key only affects profile-less/legacy tasks —
> its registry help now documents all three values incl. `sinks`). The remaining D3 improvement asks
> (judge-vs-operator calibration metric, screen self-preference, global frontier daily ceiling, real
> input/output GLM split, critic execution invariant) are OPEN and unchanged — this campaign confirms or
> refutes them at runtime.

### Frontier judge loop (post-overhaul)

**Intended goal & added value** — A stronger frontier model (Opus via `cjudge`) grades every quality deliverable produced by the cheap GLM executor and drives automatic rework — the core G5 move (second-model verification fixes the weak model's blind spots) and the engine of G2 (auto-judge → auto-retry without a human) with G3 manual override (judge button) and G6 mode-scoped cost. Value is real but was catastrophically mispriced pre-overhaul: live-DB evidence in the plan shows the judge ate **$22.00 of $28.68 total frontier spend (77%), 0% round-1 SHIP, judge input growing 470k→689k→849k tokens/round**. The overhaul re-targets it as a calibrated, bounded, three-tier verification cascade.

**Current implementation** — (all overhaul pieces landing 2026-07-13)
- Contract: `setup/bin/cjudge` (byte-synced to ~/.local/bin) — recalibrated stance (line 74: refute-by-default scoped to factual claims, taste = notes, explicit "do not manufacture findings" anti-bias line, [UNSURE] tags checked first), gate table `PASS/FAIL/N-A/UNVERIFIABLE-HERE` (:78), blockers-only verdict rule (:82 — SHIP with open medium/low notes; REVISE needs ≥1 blocker), numbered `[F1]..[Fn]` revision_brief (:88).
- Bundle: `evals.run_judge_cmd` (evals.py:457) exports `JUDGE_TASK` (stage contract — later stages' criteria out of scope), `JUDGE_SPEC` (omitted on delta rounds, :528), `JUDGE_ARTIFACTS` (`_copy_judge_artifacts` :413, 1MB/file 40MB total, delta-round mtime filter :442); runs under `_FRONTIER_GATE` (evals.py:141, `frontier.max_concurrent`=2), 900s timeout, claude-JSON envelope unwrapped + $ booked (`record_frontier_spend` :199).
- Pre-gate: `evals.judge_pregate` (:697) — free filesystem checks (deliverable exists / ≥`judge.pregate_min_chars` / ≥2 headings / no TBD in opener / repo diff non-empty) run by the sweep before any loop judge POST (loop_engine.py:735-755); failure retries for free and consumes a round.
- Tiering: `loop_engine._judge_tier` (:484) — high_stakes/smart → frontier; eco → none; optimal → frontier for sinks (`_is_sink` :465) + **GLM screen** for interior members (`judge.screen=interior`). Screen = `server._screen_thread` (:5108): one Hermes turn on the owner's default model, same sentinel contract, notes-only REVISE coerced to SHIP (:5189), booked `kind='judge_screen'`, `judge_tier='screen'` — never SHIP-authorizes: excluded from golden-exemplar selection (hermes_dispatch.py:938-944) and from auto-approve (loop_engine.py:1256-1259).
- Rework loop: sweep `_sweep_task_loops` (:659) REVISE branch (:771-806) → `_retry_task` drains open comments as `[F1..Fn]` (server.py:6217-6237); **delta re-judge round ≥2**: `_build_judge_prior` (server.py:4929) = prior blockers + unified diff → `JUDGE_PRIOR`, criteria frozen (cjudge DELTA block :67-69), round memory `workspace/_judge/round-N.json` + `tasks.judge_round/judge_keys` (database.py:282-287).
- Bounds & closure: hard cap `judge.max_runs=4` (sweep :705-711, endpoint 409 server.py:5273); convergence `keys⊆prev` (`_judge_keys_converged` :548); at-cap/converged/error/cost-cap → `_close_judge_loop` (:603) files ONE `deliverable` decision card (screened interior members close silently, `card=False`); operator reject resets the family (`reopen_judge_loop` :591). Robustness: `_judge_thread` catch-all (server.py:4902-4926) + runtime stale-'running' reaper `_sweep_stale_frontier` (loop_engine.py:1283-1309, 2h → 'interrupted', re-judgeable, runs even in drain posture).

**The proper way (web-researched)** —
- Mid-2026 LLM-as-judge practice: explicit criterion-separated rubrics, the lowest-precision verdict scale that suffices, structural bias controls, and **calibration against human labels** (Cohen's-kappa-style agreement tracking) as an ongoing production discipline [LLM-as-Judge Best Practices in 2026: Calibration, Bias, and Cost — https://futureagi.com/blog/llm-as-judge-best-practices-2026 (accessed 2026-07-13)]. The recalibrated stance/verdict rule implements the verdict-tier + "a prompted reviewer always finds gaps" bias advice verbatim.
- Deterministic layers first: rule-based checks catch 30-60% of failures before a judge fires; order guards cheap-to-expensive [Deterministic LLM Evaluation Metrics (2026): The Eval Floor — https://futureagi.com/blog/deterministic-llm-evaluation-metrics-2026/ (accessed 2026-07-13)]. The pre-gate → GLM screen → frontier judge chain is exactly this cascade.
- Refinement evidence: gains concentrate in rounds 1-2 and near-plateau by round 3 [Self-Refine: Iterative Refinement with Self-Feedback — https://selfrefine.info/ (accessed 2026-07-13); Iterative Self-Refinement — https://www.emergentmind.com/topics/iterative-self-refinement (accessed 2026-07-13)] — `judge.max_runs=4` + convergence guard + human closure at plateau match the doctrine; delta re-judge with frozen criteria matches "freeze criteria round 1 + delta re-review".
- Family bias: never use the same model family as generator and judge [LLM-Judge Bias Mitigation (2026) — https://futureagi.com/blog/evaluating-llm-judge-bias-mitigation-2026/ (accessed 2026-07-13)]. Opus-judges-GLM is correctly cross-family; but the GLM screen judges GLM output — same family, in fact the very model that produced the work (server.py:5157).
- Net: the overhaul adopts the researched fixes faithfully (SHIP-with-notes, fix-lists, delta rounds, bounded loops, cascade tiers); the one SOTA element with no implementation is measured calibration — verdicts are never scored against the operator's actual accept/reject decisions.

**Verdict: PARTIAL** — loop mechanics reach researched SOTA on paper; the calibration layer and one bias hole don't.
- Wire a judge-agreement metric: join operator closure-card/reject decisions against `tasks.judge_verdict`/`judge_tier` inside `routing.sweep_stats` (routing.py:158 already sweeps outcomes and now records `judge_runs` :126-138) — overhaul risk #1 ("real blockers downgraded to notes") is currently watched informally, against explicit 2026 calibrate-vs-human guidance (futureagi, above).
- Break screen self-preference: `_screen_thread` uses `db.default_task_model(owner)` — the exact model whose output it grades (server.py:5157). Route the screen to a different GLM tier (e.g. the 'easy' purpose or a pinned alternate), or at minimum log screen-SHIP→later-frontier-verdict pairs to measure false-accept rate.
- Pre-gate drift vs plan §1.3: the "rubric self-score line present" check was dropped from `evals.judge_pregate` (:697-746 has no such check) — add it (one regex) or record the deviation; it is the only pre-gate check that ties the deliverable to the rubric contract.

### Grounded critic + Super Result + escalation

**Intended goal & added value** — Super Result is the paid top tier of G5/G6: instead of a text-only judge refuting what it cannot see, a **grounded critic** (frontier model with full tool access) re-verifies the deliverable inside a disposable sandbox — re-reading sources, re-running quoted commands — so verification is grounded in execution, not prose. The escalation ladder then puts the frontier model in the *write* path exactly once when cheap rework fails, and the premortem catches plan defects before any execution spend. Serves G2 (closed auto-rework), G3 (open checkpoints, line-anchored findings the operator can edit), G4 (learning_note per critique). Pre-overhaul reality check: the critic ran **once ever ($3.23)**, escalation once — the machinery existed but the open-mode checkpoint-every-round default made it unused; the overhaul arms and closes it.

**Current implementation** —
- Sandbox: `evals.build_critic_sandbox` (evals.py:843) — workspace copytree (evidence incl. `_history/`, `deliverable.v*`, attachments), repo tasks `git clone --local` + task-branch materialization from `refs/remotes/origin/<branch>` before `remote remove origin` (:879-901 — without it the critic silently reviews the BASE branch), `_critic_context/` (domain+type rubrics, BUSINESS-CONTEXT, Deep-Plan `spec.json`, sibling deliverables, open comments) + `context.json` manifest.
- Critic run: `run_critic_cmd` (:994) — `cverify {file} {domain} {sandbox}` (settings `super.critic_cmd`, gate-stubbable) with full tool access, cwd=sandbox, secrets-scrubbed env, `super.timeout_s`=1500, under `_FRONTIER_GATE`; sentinel JSON → `parse_critic_json` (:1307) → line-anchored `review_comments` (`_insert_critic_comments` server.py:5318, ±2 anchor validation, workspace + repo-worktree roots :5332-5337 landing 2026-07-13).
- Loop: `_sweep_super_result` (loop_engine.py:964) — critic on every fresh version; SHIP quiet-stop (:1027); closed-mode auto-retry with the revision brief; convergence `keys⊆prev`; **empty-findings REVISE = contradiction → human checkpoint** (:1050); round caps (`super.max_rounds`=3, profile round_cap); per-task frontier cost cap checkpoint (:1011, landing 2026-07-13); `critic_verdict='error'` → checkpoint. Assisted involvement now runs SR **closed** (autopilot.py:117-127, landing — open-every-round is why SR ran once ever).
- Escalation (C1c/C5, **armed** landing 2026-07-13: `super.escalation` default '1'): `_try_escalate_super` (loop_engine.py:863) — profile threshold via `autopilot.derive`.`escalation` {eco:off, optimal:rewrite, smart:rewrite_or_cap} (:205), bounded `super.escalation_max=1`, frontier-cost-cap check (:890), quota tri-state ('wait' parks it); `POST /api/tasks/{id}/escalate` (server.py:5688) CAS-guards 'escalating'; `run_escalation_cmd` (evals.py:1128) runs `cexec` — the frontier model rewrites `deliverable.md` in the REAL workspace from a self-contained dossier (`build_escalation_dossier` :1043: brief + verified findings + contradictions + open comments + clipped siblings), timeout 2100s.
- Premortem: `evals.run_plan_critique` (:1179) — an EXTERNAL `spec_model` (never the planner grading itself) assumes the plan failed, ≤8 sentinel-fenced findings, same frontier gate; findings render as advisory ⚠ annotations in the plan editor with an auto/manual revise loop.

**The proper way (web-researched)** —
- Anthropic's evaluator-optimizer guidance: use the pattern only "when we have clear evaluation criteria, and when iterative refinement provides measurable value", and add complexity "only when it demonstrably improves outcomes" [Building Effective AI Agents — Anthropic — https://www.anthropic.com/engineering/building-effective-agents (accessed 2026-07-13)]. SR is opt-in/triage-routed with a SHIP quiet-stop — compliant in shape; the "measurable value" half remains the unrun Phase-8 claim.
- Execution-grounded verification is the 2026 bar for code: AgentForge makes sandboxed execution a first-class invariant ("no repair action without execution-based confirmation") and beats single-agent baselines by 26-28 points on SWE-Bench Lite [AgentForge: Execution-Grounded Multi-Agent LLM Framework — https://arxiv.org/abs/2604.13120 (accessed 2026-07-13)].
- Execution-FREE critics only *predict* executability/build status (~91.5%/82.1%) [LLM Critics for Execution-Free Evaluation of Code Changes — https://arxiv.org/pdf/2501.16655 (accessed 2026-07-13)] — real execution beats prediction; the cverify sandbox (full tools, disposable clone, re-run commands) is squarely in the SOTA class and ahead of most production quality loops.
- Bounded refinement (cap 3 + convergence + escalate-at-plateau) matches the Self-Refine plateau evidence [Iterative Self-Refinement — https://www.emergentmind.com/topics/iterative-self-refinement (accessed 2026-07-13)]; single bounded escalation to a stronger writer matches cascade doctrine.
- What SOTA has that this doesn't: a mandatory-execution *invariant* — here the critic's grounding is discretionary (the prompt invites re-running commands; nothing requires the acceptance suite to pass), and the acceptance-runner pre-gate is explicitly deferred (overhaul plan §7).

**Verdict: PARTIAL** — sandbox-grounded critique + bounded armed escalation is SOTA-shaped and rare in production; the execution invariant and value measurement are missing.
- For `deliverable_type='code_change'`, make the critic contract REQUIRE executing the workflow's Q3 `acceptance/` suite inside the sandbox and reporting exit codes as findings (`build_critic_sandbox` already copies the workspace + repo; `context.json` can carry the suite path) — per the AgentForge invariant and the 82%-prediction-vs-execution gap cited above; build the deferred `judge.pregate_tests` runner so deterministic test failures never reach a $ critic.
- Instrument critic-finding precision (findings confirmed by the next round/operator ÷ total) into `routing_outcomes` — the C-7 anchoring risk ("a dossier carrying a wrong finding can anchor the rework below a clean direct pass", evals.py:1039-1041) is acknowledged in a comment but unmeasured.
- Add a screen-tier critic mirroring `judge.screen`: one observed critic pass cost $3.23 — above the whole Balanced per-task frontier cap ($3.00), so on Balanced a single frontier critique can exhaust the family's budget before any escalation; a GLM cverify pass on non-HS SR tasks preserves the grounding at ~$0 (same cascade logic the judge tier already applies).

### Economic modes + cost governance & visibility

**Intended goal & added value** — G6 head-on: two plain-language axes — involvement (full_auto/assisted/manual) × spend (eco/optimal='Balanced'/smart) plus the Super-Result flag — deterministically set every quality/cost knob, with the standing claim that each mode beats "using the models the normal way". Cost governance makes spend *bounded* (budgets, ceilings, caps) and *attributable* (per-task/kind/model ledgers), and G3/G1 visibility puts the true cost where decisions happen (task drawer, board chip, Usage tab). Pre-overhaul: budgets silently extended 5M→16.96M on one task, frontier $ had zero UI call sites, and NULL-model tasks priced 99% of GLM spend at $0.

**Current implementation** —
- Mode matrix: `autopilot.derive` (autopilot.py:105) is the single source — preference (rule 1), mode/sr_mode (assisted SR open→**closed**, :117-127, landing 2026-07-13), super_result/fanout/round_cap (:130-141, smart=3), judge_scope `{eco: high_stakes, optimal: sinks, smart: all_quality}` (:152, landing — the estimator-tier inversion fix), budget_mult 0.5/1/2 on the per-TYPE baseline (`preset_fields` :49), pipeline_depth (rule 5), escalation threshold (:205), eco model_floor (:215). Tier cascade `dispatch.escalate_on_revise=1`: a judge-REVISEd light-tier attempt retries on the 'complicated' tier (server.py:6337-6360; never high-stakes/dev).
- Budget honesty (landing 2026-07-13): `tasks.budget_original` pinned at first retry (server.py:6282-6287); retry slice = `dispatch.retry_slice_frac`(0.5)×original; hard ceiling = `dispatch.rework_ceiling_mult`(2.0)×original; at the ceiling ONE `action_type='budget'` decision card (:6306-6330 — approve = one more slice, reject = accept as-is). Frontier caps: `frontier.task_cost_cap_usd`=3.0 × profile mult (→ $1.50/$3/$6) enforced at all four frontier doors (loop_engine.py:512-524 helper; auto-judge :725, REVISE branch :783, escalation :890, SR critic :1011); `frontier.max_concurrent`=2 semaphore.
- Ledger: `database.record_frontier_run` (:952) → `frontier_ledger` rows (kinds judge/judge_screen/critic/escalation/premortem/judge_eval) + `tasks.frontier_tokens/frontier_cost_usd` accumulators; `task_cost_ledger` (:983) / `workflow_cost_ledger` (:1010) served at `GET /api/tasks/{id}/ledger` (server.py:4193) and `/api/workflows/{id}/ledger` (:4204); `effective_task_model` (:1109) resolves NULL model the same way dispatch does (fixes the $0-pricing bug); `glm_cost_estimate` blended rate (:942, `cost.output_fraction`=0.5); frontier $ comes from the claude-JSON envelope unwrap (`_unwrap_frontier_output` evals.py:152).
- Visibility (landing 2026-07-13): task drawer "💰 True cost ≈ $X = GLM + frontier" (app.js:4190-4202), board `$` chip when `frontier_cost_usd>0` (:1314), Usage tab `quality_loop` split (tools_hub.py:665-689 + panel app.js:6889), `GET /api/quota` (server.py:6486, in-flight per model) and `/api/usage` (:11282). Honest labeling: Balanced card reads "Best value — … (Heuristic — Phase-8 benchmark pending.)" and Eco carries the same caveat (app.js:3958-3959, 3993-3994) — the G6 beat-the-baseline claim is explicitly unproven until the deferred added-value benchmark runs.

**The proper way (web-researched)** —
- Routing/cascade SOTA: RouteLLM's preference-trained routers keep ~95% of GPT-4 quality at up to 85% lower cost (matrix-factorization router needs only 14-26% strong-model calls) [RouteLLM — https://github.com/lm-sys/routellm (accessed 2026-07-13)]; production guidance layers cheap pre-request rules, at-inference cascades, and post-response retry [LLM Routing and Model Cascades — https://tianpan.co/blog/2025-11-03-llm-routing-model-cascades (accessed 2026-07-13)]. Nexus's escalate-on-REVISE + three-tier judge IS a verification cascade (the accuracy-safe kind); its pre-router (`routing.select_model_for_task`) is keyword-heuristic, not learned.
- Cost governance: 2026 FinOps doctrine is that budgets must be *enforced policies*, not dashboards — "observability without enforcement" is the named failure mode (Uber burned its 2026 AI budget by April); guidance: per-task hard caps ≈2× the p95 baseline, soft alerts ~70%, org-level ceilings, session termination at the cap [AI Agent Token Budget Enforcement — https://waxell.ai/blog/ai-agent-token-budget-enforcement (accessed 2026-07-13); Agentic AI Cost Governance — https://www.finout.io/blog/agentic-ai-cost-governance-controlling-spend-before-it-controls-you (accessed 2026-07-13)].
- Nexus enforces per-task token budgets at dispatch entry, per-task frontier $ caps, and a 2×-original rework ceiling with a human card — the ceiling literally matches the 2× heuristic — and its per-task/kind/model attribution matches FinOps showback guidance [AI Cost Observability: Measuring and Justifying Token Spend in 2026 — https://www.vantage.sh/blog/finops-for-ai-token-costs (accessed 2026-07-13)].
- Honest labeling of unproven value claims (the Balanced/Eco "heuristic" caveats) is ahead of typical practice, where mode marketing outruns measurement.
- Gap vs doctrine: every $ cap is per-task; there is no aggregate (daily/weekly) frontier ceiling — `dispatch.daily_cap` bounds GLM tokens only.

**Verdict: PARTIAL** — enforcement + attribution + honesty match 2026 FinOps guidance unusually well; three concrete shortfalls remain.
- Add a global frontier spend ceiling (e.g. `frontier.daily_cost_cap_usd`, checked beside `frontier.quota_backoff_until` in the sweep and in `_FrontierGate`): N tasks/day × $3/task is unbounded fleet-level spend with only concurrency=2 as a brake — exactly the org-ceiling gap the waxell/finout sources call out.
- Replace the blended GLM $ estimate with a real input/output split in the ledger: the screen thread already reads `prompt_tokens`/`completion_tokens` from Hermes usage (server.py:5171-5173) — harvest the same split at `run.completed` for executor runs instead of pricing `tokens_used` at `cost.output_fraction`=0.5 (currently an estimate that the ledger note honestly labels but that skews mode comparisons).
- Graduate `routing.select_model_for_task` from keyword heuristics to the L1 `routing_outcomes` data (RouteLLM-class learned pre-routing) once volume allows; until the A/B replay (success gate ≥40% frontier-$ reduction, non-inferior quality) and Phase-8 benchmark run, the "best value" labels stay heuristic — keep them (they are correctly caveated today) and treat G6's beat-the-baseline requirement as OPEN, not met.
## Cluster D4 — Memory & Learning Loops

### Semantic/agent memory (mem0 + qdrant + agent-memory scopes)
**Intended goal & added value** — Give the fleet a persistent brain (G4): facts auto-extracted from
every chat/task session (semantic, mem0), plus a per-lane track record so an agent "knows what it's
good at" and honors operator-taught rules (G3 teach/correct). Serves G1 (Memory tab overview incl.
3D galaxy), G10 (per-user isolation on a shared fleet), G5 (vector memory + consolidation is
frontier practice). Value today: dispatch briefings carry lane rules + track record; JARVIS/task
sessions recall user-scoped facts without re-telling.
**Current implementation** — Two disjoint planes. (1) Semantic: Hermes `memory.provider:
mem0-client` (`setup/hermes/config.yaml:124`, flush_min_turns 6) → mem0 OSS with ollama llama3.1:8b
extractor + nomic-embed-text (768d) into qdrant collection `mem0` (`setup/hermes/mem0.json`;
collection name hardcoded in `server.py:1699`). `setup/hermes/plugins/mem0-client/__init__.py`
subclasses the provider: writes stamped `metadata.client/user` from the
`~/.hermes/client-scopes.json` bridge (`hermes_dispatch.publish_session_scope`,
hermes_dispatch.py:581), reads post-filtered (`_FilteringBackend._row_ok`) — untagged = shared.
Core-mod `phase1-mem0-scoping.patch` adds per-specialist scoping: private `agent_id` + shared
`team-shared` base, merged on recall, with `_log_lesson_usage` feeding a prune job. (2) Agent lanes:
SQLite `memory` table, 4 scopes (`app/agent_memory.py:5-11`): `stm` in-flight scratchpad written at
dispatch start (hermes_dispatch.py:1945-1957, TTL 48h), `experience` one deterministic line per
finalize (`_write_experience`, :1410), `lts` hourly rolling 120-word summary (`consolidate_agent` —
watermark = max consumed created_at, one cheap-model call, sentinel `nexus:agentmem` user scope so
consolidation extractions never leak cross-user; swept by scheduler.py:198), `longterm`
operator-taught rules via admin-only `POST /api/agents/{id}/memory` (server.py:4007). Loop closes:
`build_framing(agent_id=…)` injects longterm (6×200ch) + lts summary (400ch), capped 800ch
(hermes_dispatch.py:1228-1243). UI: Memory tab subtabs map/semantic/agent/feedback
(app.js:6507-6532), galaxy = server-side PCA of real embeddings (`/api/memory3d`, memory3d.js).
Known past defect: mem0 `max_tokens: 2000` truncated grammar-constrained JSON → dropped writes;
fixed live + golden to 8000.
**The proper way (web-researched)** — 2026 production consensus is a tiered architecture — small
always-in-context core + vector retrieval layer + an EXPLICIT forgetting policy — over the
episodic/semantic/procedural taxonomy [AI Agent Memory Systems: A 2026 Engineering Guide (Letta,
LangMem, Mem0, Zep) — https://jobsbyculture.com/blog/ai-agent-memory-systems-guide-2026 (accessed
2026-07-13)]. Mem0 itself is state of the art for the extract→consolidate→retrieve pipeline (91%
lower p95 latency, >90% token savings vs full-context) [Mem0: Building Production-Ready AI Agents
with Scalable Long-Term Memory — https://arxiv.org/abs/2504.19413 (accessed 2026-07-13)]. Current
research says write-time heuristics alone are insufficient: memory needs admission control,
deletion, and time-aware decay (Weibull/Ebbinghaus-style) or stale facts drift from reality
[Governing Evolving Memory in LLM Agents (SSGM) — https://arxiv.org/abs/2603.11768 (accessed
2026-07-13)]. Critically, consolidating raw logs into ABSTRACT insights beats retaining raw
trajectories — raw task records cause negative transfer on later, harder tasks [When Continual
Learning Moves to Memory: A Study of Experience Reuse in LLM Agents —
https://arxiv.org/html/2604.27003 (accessed 2026-07-13)]. Nexus's experience→lts condensation
("merge, don't append — drop stale facts") independently matches that finding; the scope model maps
cleanly onto episodic (experience) / consolidated-semantic (lts) / procedural (longterm).
**Verdict: PARTIAL** — architecture is genuinely close to 2026 practice (scoped writes, watermarked
consolidation, TTL sweep, readers exist for every scope), but hygiene and lifecycle gaps remain:
- Fix the vendored-template drift: `setup/hermes/mem0.json:12` still has `max_tokens: 2000` while
  `setup/guardian/golden/mem0.json` has 8000, and `setup/install.sh:30` copies the 2000 version to
  `~/.hermes/mem0.json` — a fresh install re-introduces the dropped-writes defect (guardian then
  flags/repairs it, but the source of truth contradicts itself).
- No decay/forgetting on the `mem0` collection itself: rows persist forever unless hand-curated;
  only specialist lessons get the usage-tracked prune path (`_log_lesson_usage` → prune_lessons.py).
  Add time+usage-aware archival for general semantic rows (SSGM/Ebbinghaus pattern) — stale user
  "facts" otherwise anchor future sessions.
- No outcome-aware write gating: mem0's llama3.1:8b extractor decides admission alone. Route
  task-outcome signals (judge verdict, cancellation) into ADD/UPDATE/NOOP decisions, or at least tag
  extraction provenance for later quality triage.
- `lts` consolidation runs on the easy-tier model with no quality check on the produced summary (a
  bad merge silently replaces the lane's whole track record — keep N-1 as rollback, or spot-check
  via the eval harness).

### Wins/Lessons feedback ledger + framing injection
**Intended goal & added value** — The human-feedback loop at the heart of G3/G4: every real-world
result (a win with measured numbers) or flop (a lesson with its correction) is captured once and
then rides into every future task briefing of that domain, so "mistakes never repeat" and what
worked is imitated. G10: per-user ledgers with browse/adopt sharing; G8: the 🐞 modal + AI draft
makes capture cheap enough to actually happen. Value today: 2 wins + 2 lessons per domain are
injected into dispatch and JARVIS framings automatically.
**Current implementation** — `app/feedback_log.py` is the single owner: per-user paths (owner =
canonical `~/knowledge/feedback/` = shared "General" bucket; members overlay at
`users/<uid>/feedback/`, `feedback_path:45-52`), template bootstrap, newest-first atomic insert
under a lock (`insert_entry:100`), tolerant parser with stable sha1 entry keys
(`parse_entries:172`). Capture: `POST /api/tasks/{id}/feedback` (server.py:5944) hard-validates — a
WIN without real numbers 400s (:5959), a LESSON without a named correction 400s (:5974). The AI
draft (`/feedback/draft`, :6029) condenses deliverable + judge/critic evidence but is forbidden to
invent numbers (framing :6009 names metrics-to-check only; belt-and-braces pops any
`numbers/result/metrics` key, :6096). Injection: `dispatch_block(domain, user_id)`
(feedback_log.py:292-334) merges own+adopted ahead of General, takes the newest
`feedback.framing_max_entries` (2) wins + lessons, skips "to be decided" corrections, caps 1200
chars, and is deliberately NOT skipped on retries (hermes_dispatch.py:1117-1122); kill switches
`feedback.framing_enabled` / `feedback.cross_user_visible` (settings_registry.py:387-401). Adopt:
`POST /api/feedback/adopt` (server.py:6137) copies with provenance bullets + Origin-key dedupe
(`adopt_entry:259-272`). Wins can promote the deliverable into `domains/<d>/examples/`
(`promote_deliverable:151`), which golden exemplars read.
**The proper way (web-researched)** — 2026's reference loop (PAHF) is exactly this shape: clarify
before acting, ground actions in retrieved preferences, integrate post-action feedback into memory
when preferences drift [Learning Personalized Agents from Human Feedback —
https://arxiv.org/abs/2602.16173 (accessed 2026-07-13)]. But research is blunt that injection alone
is not learning: memory presence does not automatically improve behavior, and credit assignment
("memory was present" vs "session went well") must be tracked — log which entries were injected and
gate on outcomes [When Continual Learning Moves to Memory — https://arxiv.org/html/2604.27003
(accessed 2026-07-13)]; practitioners recommend recording per-run whether memory was injected and
what the outcome was, and routing evaluation signals back to mark entries reliable/unreliable [What
I Learned Adding Memory to AI Agents —
https://dev.to/ksankar/what-i-learned-adding-memory-to-ai-agents-1eh2 (accessed 2026-07-13)].
Production guidance also wants feedback weighted by reviewer role/risk, expiration rules, and
versioned truth sets so old preferences don't override current policy [How AI-powered agents learn —
https://www.glean.com/perspectives/how-ai-powered-agents-learn-a-beginners-guide (accessed
2026-07-13)].
**Verdict: PARTIAL** — capture quality and the write→read plumbing are strong (hard validation,
honest AI drafts, per-user merge, injection with caps and kill switches — writes demonstrably have
readers), but the loop's back half is open:
- No behavior-change verification (the G4 promise): nothing records WHICH entries rode into a
  dispatch (`_dispatch.json` audit doesn't list them) nor detects that the same failure recurred
  after a lesson existed. Add injected-entry keys to the dispatch audit + a recurrence check
  (judge/critic finding fuzzy-matched against existing lesson headlines) so "mistake repeated
  despite lesson" becomes a visible signal.
- Selection is recency-only: `_merged_entries` takes the newest 2 per domain
  (feedback_log.py:311-318) — an older, still-load-bearing lesson rotates out of framings forever
  once 2 newer entries exist. Rank by relevance to the task brief (even keyword overlap) with
  recency as tiebreak, or raise the cap for lessons specifically.
- Domainless work is outside the loop entirely: `dispatch_block` returns "" for `general`/no domain
  (feedback_log.py:298-300) — dev tasks (the largest class) can never receive lessons; the UI even
  warns "no domain → never injected" (app.js:4465). Route code lessons somewhere that dev framings
  read (e.g. lane `longterm` or a code-domain ledger).
- Entry lines truncate at 240 chars (feedback_log.py:323) — corrections can be cut mid-sentence;
  truncate on word/field boundaries.

### Lesson distillation + golden exemplars
**Intended goal & added value** — Turn raw human corrections into DURABLE knowledge (G3/G4):
operator edits, rejections, and review comments are evidence; a frontier call distills them into
concrete PLAYBOOK/RUBRIC/STYLE-VOICE deltas, gated by one admin approval, then git-committed into
`~/knowledge` — which every future task framing already reads. Golden exemplars close a second loop
(G5): the operator's own judge-SHIPped, high-scoring deliverables become few-shot quality bars for
future work in that domain. Together: the system's standards ratchet upward from real use, not from
prompt tinkering.
**Current implementation** — `app/lessons.py`: `record_evidence:40` files rejection feedback / user
comments / rejected→accepted diffs (`compact_diff:71` — "the strongest signal") into
`edit_evidence`; `gather_evidence_text:96` also folds in review comments + judge/critic learning
notes (free B6 input). `run_distillation:167` runs ONE judgment-tier `cdistill` call (vendored
`setup/bin/cdistill`; token-safe resolver, scrubbed env, `_FRONTIER_GATE`), parses ≤5
sentinel-fenced deltas restricted to the 3 knowledge files (`parse_lesson_deltas:137`), marks
evidence distilled even on zero deltas (:228), and files ONE admin `lesson_deltas` approval (:240) —
the binding autonomy ceiling: proposals are autonomous, writes are human-gated. `apply_deltas:275`
snapshots a dirty tree, replaces `before` when found else APPENDS, routes `user_overlay` STYLE-VOICE
to `users/<uid>/` (L2), git-commits. Cron sweep weekly (`sweep_distillation:327`,
`lessons.auto_distill/cron`). Exemplars: `hermes_dispatch.golden_exemplars:901` — deterministic SQL
over same-domain (+client) tasks with `judge_verdict='SHIP'`, self-score ≥ `exemplars.min_score`,
age-out at `exemplars.max_age_months`, never code_change, never retry rounds (:919), and since
2026-07-13 a `judge_tier` guard so GLM screen verdicts never qualify (:938-944); unioned with
curated `domains/<d>/examples/` files (one slot reserved for own work, :977) and injected as
MUST-READ paths with honest own/curated labels (:1149-1162).
**The proper way (web-researched)** — This is the ACE (Agentic Context Engineering) pattern:
contexts as evolving playbooks that accumulate strategies via generator→reflector→curator roles,
with structured INCREMENTAL, itemized updates — naive approaches fail through brevity bias (dropping
domain insight) and context collapse (iterative rewriting eroding details); ACE gains +10.6% on
agent benchmarks [Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models
— https://arxiv.org/abs/2510.04618 (accessed 2026-07-13); ACE prevents context collapse —
https://venturebeat.com/ai/ace-prevents-context-collapse-with-evolving-playbooks-for-self-improving-ai
(accessed 2026-07-13)]. For exemplars, the survey literature says selection and order critically
influence quality, and similarity-to-the-current-task selection is generally beneficial (diversity
sometimes) [The Prompt Report: A Systematic Survey of Prompt Engineering Techniques —
https://arxiv.org/pdf/2406.06608 (accessed 2026-07-13)]; manual curation doesn't scale —
data-centric filtering should keep only verified-quality examples [Ensuring Reliable Few-Shot Prompt
Selection for LLMs — https://cleanlab.ai/blog/learn/reliable-fewshot-prompts/ (accessed
2026-07-13)]. ACE also stresses adapting from natural execution feedback with verification that the
updated context helps.
**Verdict: PARTIAL** — evidence capture, the human-gated frontier distillation, and exemplar guards
are genuinely well-designed (the diff-as-strongest-signal and autonomy ceiling match research); the
gaps are curation hygiene and loop verification:
- Append-mostly application: when `before` isn't found, `apply_deltas` appends (lessons.py:302-305)
  — playbooks grow monotonically with no dedupe/merge/contradiction pass (ACE's curator role is
  missing). Add a periodic curation step (even deterministic near-dup detection) before the
  knowledge files bloat into noise.
- No post-apply verification: the eval harness already fingerprints config per run (evals.py —
  playbook/rubric hashes) so score deltas CAN map to knowledge changes, but nothing triggers a
  before/after eval when deltas land. Wire `apply_deltas` → schedule an eval run on that domain; a
  lesson that doesn't move scores should be reviewable/revertable.
- Promoted-win mislabeling (known, still in code): `promote_deliverable` copies the operator's OWN
  win into `examples/`, but `golden_exemplars` labels every `examples/` file `own=False` and the
  framing calls them "not the operator's own" (hermes_dispatch.py:961-963, 1159-1160) — the
  provenance header written by `promote_file` (feedback_log.py:160) is never read back. Parse it to
  label promoted wins truthfully.
- Exemplar selection ignores brief similarity — domain+client+freshness only
  (hermes_dispatch.py:941-950); with `exemplars.max=2` a mismatched exemplar anchors structure. Add
  lightweight brief-similarity ranking; also note self-`rubric_score` (the executor's own claim)
  remains a gate input.

### Self-recap & uncertainty
**Intended goal & added value** — G4's "recaps its own work, asks when unsure": a spoken JARVIS
daily briefing + task completion/failure callbacks keep the operator oriented without opening the
board (G1/G9); the project decision log makes multi-stage work self-coherent; the [UNSURE] honesty
contract makes uncertainty explicit and INCENTIVE-ALIGNED (tagging protects the executor's score);
the wizard/Deep-Plan interview asks before assuming when an unknown would change the plan's shape
(G2 automation that stays steerable).
**Current implementation** — Briefing: `GET /api/jarvis/briefing` (server.py:3233-3273) is
DETERMINISTIC text — done/failed tasks in 16h, board counts, and the Decisions surface reusing the
exact `/api/decisions` aggregation (:3251, `_collect_decision_cards`) so spoken numbers always match
the inbox; the UI speaks it once per day (`jvBriefDate`, app.js:8687-8694) and polls
`/api/jarvis/events` (:3276) for spoken completion/failure/super-result callbacks while the tab is
open. Decision log: executors must END deliverables with `## Decisions`; `harvest_decisions`
(hermes_dispatch.py:1266-1309) deterministically appends the section to the project's `DECISIONS.md`
under flock, superseding the same task's block on rework (stale choices from a rejected draft never
anchor later stages); every member reads the log FIRST (:1134-1146). Uncertainty: framing orders
`[UNSURE: reason]` tags on every unverified claim and states the asymmetry (:1062-1068);
high-stakes/judged work additionally must end with a Gate-evidence table where unmet criteria are
listed with [UNSURE] rather than papered over (:1084-1093). The contract is enforced on the read
side: `cverify:54,91` and `cjudge:74` check tagged claims FIRST — marked-false = medium,
UNMARKED-false = critical, and a marked-but-load-bearing-wrong claim still blocks SHIP.
Ask-when-in-doubt: the wizard allows ONE round of ≤6 questions only when an unknown changes plan
shape/scope/quality/cost, each with pros/cons + one recommended default so it's skippable ("PREFERS
more questions over wrong assumptions", server.py:7086-7103, clamp :7261); Deep Plan runs a full
slot-filling interview (`plan_engine.py`, `plan.max_questions_per_turn`).
**The proper way (web-researched)** — Research supports exactly this asymmetric contract: models are
chronically overconfident, and MEDIUM verbalized uncertainty yields higher trust and task
performance than either false certainty or reflexive hedging [Confronting verbalized uncertainty —
https://www.researchgate.net/publication/388821876_Confronting_verbalized_uncertainty_Understanding_how_LLM_'s_verbalized_uncertainty_influences_users_in_AI-assisted_decision-making
(accessed 2026-07-13)]. The known gap is calibration: models verbalize uncertainty yet fail to act
on it, and human-sounding hedges are poorly calibrated — systems should MEASURE the
confidence↔accuracy relationship, not just mandate tags [Anthropomimetic Uncertainty —
https://arxiv.org/html/2507.10587v1 (accessed 2026-07-13)]; over-cueing actively harms (hedging +
extra cues produced the highest overreliance on wrong answers) [More is not better —
https://www.sciencedirect.com/science/article/pii/S2949882126000587 (accessed 2026-07-13)]. On
asking: 2026 consensus is calibrated clarification-seeking — ask when uncertainty is real, refrain
when the instruction already resolves it; a question at the start prevents chains of retries [Ask or
Assume? Uncertainty-Aware Clarification-Seeking in Coding Agents —
https://arxiv.org/html/2603.26233v1 (accessed 2026-07-13)]. Deterministic (non-LLM) recaps avoid
hallucinated status — sound choice.
**Verdict: PARTIAL** — each mechanism is individually well-built and unusually incentive-coherent
(tag-first judging, deterministic recap, skippable questions); what's missing is measurement and
recap depth:
- No calibration loop on [UNSURE]: nothing counts tags per deliverable or the judge-verified
  false-claim rate among tagged vs untagged claims, so over-tagging (the rational response to
  "unmarked-false = critical") is invisible and the contract can degrade into hedging — exactly the
  failure the trust research warns about. Log tag counts + judge outcomes per task (both already in
  the DB/critic JSON) and surface drift.
- The briefing recaps the BOARD, never the LEARNING: lane `lts` summaries, new WINS/LESSONS, applied
  lesson deltas, and eval-score movements never reach `/api/jarvis/briefing` (server.py:3238-3272
  queries tasks/decisions only) — G4's "recaps its own work" is half-served; add a weekly "what the
  system learned" line from data that already exists.
- Spoken completion callbacks are best-effort only while the JARVIS tab is open
  (`/api/jarvis/events` client poll); events while closed are silently unspoken — acceptable, but
  document or backfill on next briefing.
- The `## Decisions` requirement is prompt-enforced with no finalize-time check that the section
  exists (harvest just no-ops, hermes_dispatch.py:1276-1278) — a stage that omits it silently
  degrades project coherence; count omissions per lane so the gap is at least visible.
## Cluster D5 — JARVIS, Voice & Vision

### JARVIS voice assistant pipeline
**Intended goal & added value** — A fully local, zero-API-cost spoken/written operator interface (G9):
the user talks to JARVIS to get information, overviews and task control, and JARVIS can drive the entire
Nexus OS (board, wizard, deep plan, approvals, scheduler) over its internal REST surface (G2/G3). The
Business Brain makes replies domain-aware from ~/knowledge (G4/G5); the daily briefing and command deck
give spoken/at-a-glance operational recaps (G8). Everything speech-related runs on-box, respecting the 12
GB VRAM budget (G6).

**Current implementation** — Chat: `POST /api/jarvis/chat/stream` (server.py:2340) proxies Hermes SSE
with a large per-turn `system_message` built by `_jarvis_framing()` (persona + full API surface + curl
token) plus `jarvis_brain.brain_framing()` (9 keyword-scored domains; business facts + AI-slop kill list
every turn, rubric gates/playbook menu on deliverable-looking turns); one-retry overload fallback
(`_jarvis_overload_signature`), post-turn file-diff SSE event. TTS: `/ws/jarvis/tts` (server.py:3310)
streams raw 22 050 Hz PCM per sentence from Piper (`voice.synthesize_stream`, first chunk ~100-300 ms;
en_US-joe-medium via `voice.tts_voice`; global `_tts_lock` serializes ALL synthesis); `POST
/api/jarvis/tts` is the fallback. STT: `POST /api/jarvis/stt` uploads the whole webm utterance → temp
file → `stt_worker.py` subprocess (faster-whisper large-v3 int8_float16, ~2.9 GB download / ~2.5 GB VRAM
budget `NEEDED_MIB`), JSON-lines pipe with keepalive-based inactivity kill, gpu_lock waits, idle-ollama
eviction (`_ensure_vram`), CUDA→CPU self-heal + 600 s cooldown, idle-kill at `voice.stt_idle_timeout`
(300 s), warm-on-mic-press (`/api/jarvis/stt/warm`). Voice-in: browser MediaRecorder + hand-rolled energy
VAD (`jarvisMicLevelLoop`, app.js:8343 — EMA noise floor, threshold `max(0.028, floor*3)`, hangover 1 150
ms CONV / 2 100 ms manual); CONV barge-in = second echo-cancelled mic monitor, RMS > 0.05 for ~450 ms
cuts TTS (app.js:8394). Sessions: per-user multi-session store in `jarvis_session.json` (atomic replace +
`_JARVIS_SESSION_LOCK`), `/api/jarvis/session*`; deterministic briefing `GET /api/jarvis/briefing`
(server.py:3233, reuses the Decisions aggregation); command deck (`jarvisLoadDeck` in app.js). No wake
word — mic press or CONV mode only. Retired: `/api/jarvis/talk` + `/lipsync` return 410
(server.py:3035-3047); `lipsync.py` is dead code on disk; `tools_hub._tool_wav2lip` (tools_hub.py:146)
still health-checks and lists "Wav2Lip Avatar" as a live tool.

**The proper way (web-researched)** — The 2026 local stack norm is exactly this shape (Whisper-class STT
+ local LLM + Piper/Kokoro TTS), with 0.5-1.1 s stop-talking→first-audio considered good [Local AI Voice
Assistant Stack 2026 —
https://dev.to/kunal_d6a8fea2309e1571ee7/local-ai-voice-assistant-stack-2026-whisper-piper-ollama-wired-together-572l
(accessed 2026-07-13)]; faster-whisper large-v3 int8 (~2.5 GB VRAM, ~12× RT on an RTX 4070) is a
legitimate GPU choice [Whisper.cpp vs faster-whisper 2026 —
https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026 (accessed 2026-07-13)].
For English, however, NVIDIA Parakeet-TDT-0.6B-v3 now beats large-v3 on WER (6.32 % vs 7.44 % Open-ASR)
at ~an order of magnitude higher speed and doesn't hallucinate on silence [Parakeet vs Whisper 2026 —
https://localaimaster.com/blog/parakeet-vs-whisper (accessed 2026-07-13)]. VAD best practice is a neural
model (Silero) emitting per-frame speech probability (threshold ≈0.7, min-duration ≈250 ms) instead of an
energy floor, and barge-in should run neural VAD on echo-cancelled client audio [Voice AI Barge-In and
Turn-Taking: A 2026 Implementation Guide — https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026/
(accessed 2026-07-13)]. TTS: Kokoro-82M is the consensus quality upgrade over Piper ("real person" vs
"audibly synthetic"), Apache-2.0, ~330 MB [Best Local TTS Models 2026 —
https://localaimaster.com/blog/best-local-tts-models (accessed 2026-07-13)]; crucially `kokoro-onnx` runs
on plain onnxruntime with no PyTorch [kokoro-onnx — https://github.com/thewh1teagle/kokoro-onnx (accessed
2026-07-13)], which likely voids the documented "needs python3.11 torch worker" blocker. Skipping the
wake word for push-to-talk is a recognized, simpler and more private trade [Complete Guide to Wake Word
Detection (2026) — https://picovoice.ai/blog/complete-guide-to-wake-word/ (accessed 2026-07-13)];
openWakeWord is the drop-in if hands-free is ever wanted.

**Verdict: PARTIAL** — the VRAM-aware plumbing (killable worker, warm-on-press, eviction, fallbacks,
sentence-streamed WS TTS) is genuinely strong, but three layers sit one generation behind mid-2026
practice:
- Replace the hand-rolled browser energy VAD + RMS barge-in with Silero VAD in-browser (e.g.
  `@ricky0123/vad-web`, ONNX) — both `jarvisMicLevelLoop` and `jarvisBargeMonitorStart`
  (app.js:8343/8394) keep their hangover logic, only the speech decision changes.
- Add a Parakeet-TDT backend option to `stt_worker.py` (sherpa-onnx or NeMo) for English chat/dictation
  turns; keep large-v3 for multilingual. Cuts the 1-3 s post-utterance decode that dominates perceived
  latency (STT is batch — whole-utterance upload in `jarvisHandleRecording`).
- Upgrade TTS to Kokoro-82M via `kokoro-onnx` inside the existing `voice.py` load/idle-drop framework;
  re-test the py3.14 assumption before building the 3.11 subprocess worker.
- Delete the cosmetic dead ends: drop `_tool_wav2lip` from `tools_hub.get_tools()` scanners and remove
  `lipsync.py` (endpoints have been 410 since 2026-07-09).
- G10 note: `voice._tts_lock` is one global queue — concurrent users' speech serializes; move to
  per-connection synthesis or a small worker pool if multi-user voice matters.

### Hologram avatar + visemes
**Intended goal & added value** — A living, GPU-cheap embodiment of JARVIS (G9, G1): a cyan point-lattice
hologram head that visibly idles/listens/thinks/talks, lip-syncs to the streamed speech, blinks and makes
eye contact, with the memory galaxy behind it doubling as a data view (G4). It replaced the retired
Wav2Lip neural video path with something that runs at 60 fps on the iGPU while the 12 GB dGPU does real
work — embodiment at near-zero VRAM cost (G6).

**Current implementation** — `static/jarvis3d.js` (~1 545 lines): the three.js "facecap" GLB (52 ARKit
blendshapes, KTX2 texture stripped offline by `scripts/build_facecap_hologram.py`) rendered three ways
off one shared geometry (occluder mesh + additive wireframe + morph-aware ShaderMaterial dots),
EffectComposer → half-res UnrealBloomPass → OutputPass; vendored r160 addons in
`static/vendor/threejsm/`. States idle/listening/thinking/talking via `MODE_TINT` multipliers. Lip sync
is TEXT-ALIGNED: `app.js` registers a live per-sentence record via `Jarvis3D.speak({text,start,end,done},
audioCtx)`; `updateVisemes()` (jarvis3d.js:444) lazily runs the vendored TalkingHead `lipsync-en.mjs`
(MIT, NRL-7948 letter-to-sound rules) → Oculus viseme timeline in relative units, stretches it UNIFORMLY
over the sentence's real audio window (`scale = (end-start)/vt.total`, self-correcting as PCM chunks
land), applies attack/release envelopes (50/120 ms) through the `VISEME_ARKIT` map, and gates by the live
RMS envelope from the same AnalyserNode (`gate = 0.25+0.75*env`) so true pauses close the mouth. Eyes:
saccade/fixation state machine + Trutoiu blink dynamics. Memory galaxy + matrix backdrop render behind;
`toggleGalaxy()` flies through the head. Torso parked (`SHOW_TORSO=false`, jarvis3d.js:114). Fallback
ellipsoid bust if the GLB fails.

**The proper way (web-researched)** — This is the TalkingHead family of approach, and it is the standard
browser pattern — but upstream TalkingHead is explicit that its viseme timelines are meant to be scaled
by WORD-LEVEL timestamps from the TTS engine ("essential for accurate lip-sync"; Google TTS `<mark>`
events or ElevenLabs WS timestamps), and it ships two fallbacks when timestamps don't exist: direct
viseme scheduling (`speakAudio` with `vtimes/vdurations`) and the HeadAudio add-on — audio-driven
realtime viseme classification (MFCC features + Gaussian prototypes) needing no text or timestamps at all
[TalkingHead — https://github.com/met4citizen/talkinghead (accessed 2026-07-13)]. The rule-based English
module is itself only ~80 % accurate vs a phoneme dictionary (same source). The neural end of the
spectrum is now open: NVIDIA Audio2Face-3D (open-sourced 2025) converts audio directly to time-aligned
ARKit blendshapes with regression and diffusion variants [NVIDIA Open Sources Audio2Face Animation Model
— https://developer.nvidia.com/blog/nvidia-open-sources-audio2face-animation-model/ (accessed
2026-07-13)] — but it costs real GPU, which is wrong for a cosmetic layer on a box where VRAM is the
scarcest resource. Uniform sentence-stretch is the weakest of the recognized alignment options: Piper's
pacing is not uniform across words, so mouth shapes drift mid-sentence on long or number-heavy sentences;
the RMS gate hides pauses but not phase drift.

**Verdict: PARTIAL** — right approach family, wrong alignment tier: it uses the text-rules module without
the word timestamps that module was designed around.
- Adopt the audio-driven path for in-sentence timing: port TalkingHead's HeadAudio pattern
  (MFCC/band-energy → viseme class) onto the AnalyserNode graph `app.js` already runs, and blend it with
  (or replace) the stretched text timeline in `updateVisemes()`; keep the text timeline as the no-audio
  fallback (HTTP WAV path).
- Cheaper half-step if that's too much: split the sentence timeline per word and allocate the audio
  window by per-word viseme-duration weights with RMS-detected pause snapping — still heuristic, but
  bounds drift to one word instead of one sentence.
- Explicitly do NOT chase Audio2Face-class neural lipsync on this hardware (VRAM contention for a
  cosmetic feature); note it as the quality ceiling in docs.

### Vision (analysis + generation)
**Intended goal & added value** — Local eyes and hands for JARVIS (G9, G7): webcam/screen frames become
searchable visual memory ("when did I show you the red box?"), any image can be described in chat despite
the Z.AI key having no vision models (verified error 1113), and images can be generated into the file
exchange — all $0 and private (G6). Vision context auto-rides into chat turns as [JARVIS EYES] text (G2).

**Current implementation** — `vision.py` + `vision_worker.py` (runs in ~/ml-env). Indexing:
`ingest_frame()` thumbnails to 768 px → worker `embed_image` (SigLIP so400m-384 fp16 on GPU ~1 GB,
1152-dim pooled) + RapidOCR → qdrant `jarvis_vision` with per-user payloads; near-dup skip vs previous
frame (cos > 0.985), per-user cap 4 000 frames (`_prune_old`). Search: `search_frames()` = SigLIP text
embedding + OCR keyword boost (0.12/term, cap 0.3) — hybrid, Screenpipe-style. Understanding:
`describe_image()` via ollama qwen3-vl:8b (`num_predict` 256, `vision.vlm_keep_alive` 60 s, inside
`gpu_lock.gpu_section_async`); chat injects the description as [JARVIS EYES] text and pins the exact
frame (`pin_looked_frame`). Generation: `POST /api/jarvis/imagine` → worker `generate` = SDXL-Turbo fp16
with `enable_sequential_cpu_offload()` (~2-4 GB peak, 3 steps, guidance 0), VLM evicted first
(keep_alive:0). Worker discipline: JSON-lines pipe, `_worker_lock`, kill-and-respawn on timeout
(`_kill_and_respawn_worker`), idle-kill after `vision.idle_timeout` (600 s) — process exit is the VRAM
guarantee; SigLIP OOM → CPU-for-worker-life fallback (`_siglip_op_with_fallback`). Routes:
`/api/jarvis/see`, `/api/jarvis/vision/frame|search|status`, `DELETE /api/jarvis/vision`. Capture is
browser-side: webcam/screen buttons index a frame every 4-5 s while the JARVIS tab is open.

**The proper way (web-researched)** — The retrieval design matches the reference product: Screenpipe
(20k+ stars) does continuous capture → OCR/accessibility text + embeddings → local natural-language
search, but captures 24/7 event-driven in the background rather than only while a tab is open [Screenpipe
— https://github.com/screenpipe/screenpipe (accessed 2026-07-13)]. On models: SigLIP 2 (Feb 2025) keeps
the exact so400m architecture ("easily swap encoder weights") and beats SigLIP v1 across zero-shot
retrieval and dense tasks [SigLIP 2: A better multilingual vision language encoder —
https://huggingface.co/blog/siglip2 (accessed 2026-07-13)] — a near drop-in upgrade (same dim per size
class). qwen3-vl:8b as the local VLM is current-generation practice. Image generation is the stale layer:
SDXL-Turbo (2023) is fast but weak on prompt adherence and in-image text; the 2026 12 GB-class
recommendation is FLUX.1-schnell (Apache-2.0, fp8 ≈8-15 s/image on 12 GB) for quality, with SDXL-class
models kept only for LoRA/ControlNet ecosystems [Best Local AI Image Models 2026 —
https://localaimaster.com/blog/best-local-image-models-compared (accessed 2026-07-13); SDXL vs FLUX —
https://localaimaster.com/blog/sdxl-vs-flux-local (accessed 2026-07-13)].

**Verdict: PARTIAL** — architecture (hybrid recall, worker isolation, co-residency/eviction discipline)
is on-pattern; the models and some worker hygiene lag.
- Swap SigLIP → SigLIP 2 so400m in `vision_worker.py` (`SIGLIP_ID`): same architecture/dim, better
  retrieval; requires re-embedding or a versioned qdrant collection for old frames.
- Offer FLUX.1-schnell (fp8/GGUF) as the `generate` backend beside SDXL-Turbo; keep sequential offload +
  `gpu_lock`; SDXL-Turbo stays as the low-VRAM fast path.
- Apply the STT worker's hardened pipe discipline to the vision worker: `_spawn_worker()` (vision.py:77)
  sends stderr to DEVNULL — the exact anti-pattern voice.py:124 documents ("NEVER devnull; respawn loops
  must be diagnosable") — and the protocol has no keepalive, so a first-use SDXL/SigLIP HuggingFace
  download (~7 GB) can blow the 300 s/180 s timeouts into a kill-respawn loop; add a stderr log file +
  load keepalives (mirror stt_worker's F4 fix).
- If "visual memory" is meant seriously (G8), the bar is background capture (Screenpipe-style
  event-driven), not tab-bound 4-5 s polling — decide and document which product this is.

### Dictation (system-wide voice typing)
**Intended goal & added value** — Wispr-Flow-class system-wide voice typing (G8), absorbed from the
user's local WisprFlow into Nexus so the whole machine has ONE STT stack: press the hotkey anywhere on
the desktop, speak, and cleaned-up text is typed into the focused window. Fully local (privacy, $0), with
LLM cleanup that removes fillers/punctuates without rephrasing (G6, G2), plus note mode and language
cycling.

**Current implementation** — `dictation.py` (1 028 lines) runs as threads inside the server: evdev hotkey
listener (keycode 425, two-device duplicate collapse + 80 ms hard floor + re-arm-on-release debounce,
device rescan; `_hotkey_loop` dictation.py:930), Unix control socket
(`$XDG_RUNTIME_DIR/nexus-dictation.sock`, one-word protocol: toggle/cancel/status/meeting/note/lang,
per-connection threads + 5 s timeout). Recording: callback-based capture into a bounded queue (~30 s,
overflows counted, #9), `max_seconds`=300 is a CHAIN boundary (+15 s grace to find a pause) — segments
type out while recording continues (#2); optional energy-VAD auto-stop. STT: `voice.transcribe_pcm` →
shared worker (beam 5, `vad_filter=True`), warm-on-hotkey, mid-transcription language-switch re-run.
Cleanup: gemma3:4b on the ISOLATED second ollama :11435 (`nexus-cleanup-llm.service`, keep_alive 2 m) —
pattern-completion framing (`Input:/Output:`), temperature 0, stop sequences, preamble strip, off-script
regex backstop, expansion/collapse word-count guards, `llm_max_words`=1800 skip (gemma's 4 096 context
silently front-truncates, #10); raw transcript on ANY failure. Injection: layout-aware ydotool typing
(`dictation_layout.build_charmap` per current XKB layout, chunked argv, 4 ms key delay) with
paste/clipboard fallbacks and every external call time-bounded (#8). tkinter overlay pill subprocess
(`dictation_overlay.py`), ~35 `dictation.*` settings.

**The proper way (web-researched)** — The 2026 open-source Wispr-Flow-alternative bar (OpenWhispr, Handy,
LinuxWhispr, whisper-local) is: global push-to-talk hotkey typing into any app, fully-local Whisper OR
Parakeet models, and an LLM "agent/reformat" pass on the raw transcript [OpenWhispr —
https://openwhispr.com/compare/wisprflow (accessed 2026-07-13); 7 Best Open Source Wispr Flow
Alternatives in 2026 — https://openalternative.co/alternatives/wisprflow (accessed 2026-07-13)]. Nexus
meets every plank, and its cleanup-LLM isolation on a second ollama instance is a sound answer to the
VRAM co-residency problem (the cleanup model can never evict the main stack's models mid-task). The
deltas the field has moved on: dictation apps now default to Parakeet-TDT for English — ~10× faster than
Whisper-large with better WER, and as a transducer it "produces silence during silence" instead of
hallucinating during pauses, a dictation-specific failure mode of Whisper decoders [Parakeet V3 vs
Whisper — https://whispernotes.app/blog/parakeet-v3-default-mac-model (accessed 2026-07-13)]; and the
Linux ecosystem treats ydotool/wtype + clipboard fallback exactly as implemented here [Voice Dictation
for Linux: 7 Best Open-Source Tools (2026) —
https://weesperneonflow.ai/en/blog/2026-06-18-voice-dictation-linux-open-source-tools-2026/ (accessed
2026-07-13)]. Streaming partial injection (typing while you speak) exists in the commercial product but
is not the open-source norm; batch-per-segment is standard.

**Verdict: PROPER** — meets or exceeds the 2026 open-source dictation feature bar (push-to-talk, local
STT, guarded LLM cleanup, layout-aware injection, fail-soft everywhere); the only meaningful upgrade — a
Parakeet-TDT English backend for speed and silence-safety — belongs to the shared `stt_worker.py` (see
the voice-pipeline entry) rather than this module.

### Meetings intelligence
**Intended goal & added value** — Turn real meetings into work products (G8, G4): live speaker-labeled
transcripts of any call/audio without a bot, then one-click Summarize, Requirements extraction,
Add-to-memory (mem0, project/client-tagged) and Create-workflow — closing the loop from a client
conversation to a dispatched task DAG (G2). Local capture keeps client conversations private (G6).

**Current implementation** — Capture: `dictation_meeting.py` records TWO channels via ffmpeg PulseAudio —
the mic ("Me") and the default sink's monitor ("Client") — labeling by SOURCE, no ML diarization;
per-channel energy VAD (floor 0.02, silence 700 ms, min speech 300 ms, max seg 24 s) → bounded queue →
the shared whisper (`voice.transcribe_pcm`, beam 3, `vad_filter=False`) → speaker-labeled markdown in
`~/wf-meetings` (same-speaker merge, atomic tmp+replace flush). Robustness: supervised channels (node
re-resolve + exponential-backoff ffmpeg restarts, visible marker lines, give-up after 8),
temporal-overlap mic-bleed dedup (overlap ≥ 50 % of shorter AND similarity ≥ 0.82 → keep the Client
copy). Intelligence (server.py:2668-2993, all admin-only): `GET /api/meetings` (list + meta flags
computed in SQL), `PATCH /{name}/meta` links a transcript to a project/workflow (`meeting_meta` table,
race-free upsert), `POST /{name}/summarize` and `/requirements` = one throwaway Hermes turn
(`_meeting_llm_turn`) with fixed framings, cached vs file mtime, transcript capped at 40 k chars by
dropping the MIDDLE (`_meeting_transcript_text`); requirements are operator-editable (PATCH) and read
back non-triggering (GET, with `stale` flag); `POST /{name}/memory` pushes the summary (≤4 000 chars)
into mem0 with project/client tags; Create-workflow prefills the normal task wizard from cached
requirements (client-side `describeTaskUI`).

**The proper way (web-researched)** — The 2026 meeting-assistant pipeline is: audio ingestion (bot or
system-audio capture — Granola-style local capture, as here, is a recognized architecture), Whisper-class
STT, SPEAKER DIARIZATION, then LLM summaries/action items, with CRM/task handoff as the differentiator
[The 10 best AI meeting assistants in 2026 — https://zapier.com/blog/best-ai-meeting-assistant/ (accessed
2026-07-13)]. The open-source diarization standard is pyannote 3.1 (DER ~11-19 %) — "for combined
transcription + diarization, use WhisperX", which wraps faster-whisper + pyannote + word-level alignment
[Best Speaker Diarization Models Compared 2026 —
https://brasstranscripts.com/blog/speaker-diarization-models-comparison (accessed 2026-07-13); WhisperX
2026 guide — https://localaimaster.com/blog/whisperx-guide (accessed 2026-07-13)]. Source-labeling two
channels is a clever zero-VRAM diarization for 1:1 calls, but every remote participant collapses into one
"Client" voice, below the feature bar for multi-party meetings. Long-transcript handling in practice is
chunked map-reduce summarization, not middle-omission. The workflow handoff (meeting → requirements →
task DAG on the user's own agent fleet) matches the CRM-handoff differentiator of commercial tools and is
the strongest part of this feature.

**Verdict: PARTIAL** — capture robustness and the meeting→workflow loop are strong; speaker resolution
and long-meeting handling sit below the 2026 bar.
- Add an optional post-meeting diarization pass over the Client channel: after `stop()`, run pyannote 3.1
  (or WhisperX) offline on the saved audio/segments to split "Client" into "Client 1/2/…" — no realtime
  constraint, GPU is free after the meeting, fits the existing gpu_lock discipline. (Requires persisting
  per-channel audio, which `MeetingSession` currently discards after transcription.)
- Replace the 40 k-char middle-omission in `_meeting_transcript_text` (server.py:2707) with chunked
  map-reduce (per-chunk summaries → merge turn) so 2-hour meetings don't lose their middle in
  Summarize/Requirements.
- Guard the monitor channel against non-speech: energy VAD passes music/notification audio to whisper
  with `vad_filter=False` (dictation_meeting.py:284) — a known hallucinated-text source; flip to
  `vad_filter=True` for Client segments (or gate with Silero) and verify the bleed-dedup still fires.
- Feature-bar nicety: a structured action-items extraction (owner → action → due) beside `requirements` —
  the summary prompt has an "Action items (who → what)" section but nothing machine-readable feeds the
  wizard.
## Cluster D6 — Developer Productivity & Output Tools

### Code review v2 (in-app diff review)
**Intended goal & added value** — A PR-review experience for EVERY output type (code, reports, PDFs, images), inside Nexus, so the operator can inspect what an agent changed and feed line-anchored feedback straight back into the retry loop. Serves G1 (one organized review surface), G3 (see exactly what the tool did, round by round), G5 (judge/critic findings as first-class review comments), G8 (code review properly implemented). Value: the operator never leaves the app to review, and no judge/critic finding can silently vanish — every comment either anchors to a diff line or lists in the findings panel, and open comments ride the next retry.
**Current implementation** — `app/review.py`: `build_task_review()` (review.py:334) returns `mode='git'` for repo tasks (parses `changes.diff`) and `mode='workspace'` otherwise; `snapshot_workspace()` (review.py:34) copies output to `_history/vN/` on every retry (since 2026-07-13 repo tasks snapshot too — server.py ~6263 dropped the repo guard); `compare_dirs()` (review.py:237) diffs directory states per file — text via difflib, PDFs by pypdf-extracted text, images/binaries by metadata; `parse_unified()` carries real old/new line numbers per hunk line so comments anchor; Pygments per-side hunk highlighting (`highlight_file`, the `h` field is the only raw HTML the frontend injects). Routes: `GET /api/tasks/{id}/review` (server.py:10520) + comment CRUD (server.py:10544-10631, `review_comments` table with `source` user/judge/critic and a `patch` column); `GET /api/workflows/{id}/review` (server.py:10634) aggregates per-task counts only. Drain-to-retry: `_retry_task` (server.py ~6212) numbers open comments `[F#]`, tags `[CRITIC]/[JUDGE]/[REVIEWER]`, attaches critic patches verbatim, then marks them `consumed`. UI (`app/static/app.js`): `reviewTaskUI` (3359), unified⇄split toggle (`setReviewMode`, localStorage-persisted), per-line ＋ composer (`rcAnchor`).
Phase-4 target design (landing 2026-07-13, commit 2b7200a; part of the current implementation tree): per-round capture — `_capture_repo_result` appends `{round, head_sha, ts}` to `<ws>/_history/rounds.json` at every finalize (hermes_dispatch.py:1742-1762); `worktree.capture_diff_between()` (worktree.py:179) renders the round-over-round two-dot diff, the DEFAULT once ≥2 rounds exist (`pairs` round/base, review.py:349-367); `_report_entry` (review.py:307) diffs `deliverable.md` prev-version-vs-live for repo tasks (before this, 44/44 judge comments on one live task anchored to a file the branch diff never contained — invisible); findings panel `rvFindingsHTML` (app.js:3487) lists ALL judge/critic/user comments, anchored rows jump to the diff (`rvJump`), unanchored rows list plainly, status chips open/addressed; repo-aware anchor validation resolves findings against workspace AND the repo worktree with ±2 line drift (`_insert_critic_comments`, server.py:5328-5378). Old remnants: the plan wrote the pair API as `?from=&to=` but it landed as `?pair=` + `from_v`/`to_v`, and the UI's workspace selector only ever sends `from_v` (to = live) — both now RECORDED deviations in `app/docs/SPEC-JUDGE-LOOP.md` §13; the gate updates are committed (`f999047`, review checks in `verify_judge_loop_e2e.py` §8 + block2 48/48+21/21 green at HEAD).
**The proper way (web-researched)** — Gerrit is the reference model for iteration-aware review: each upload is a patchset, and the diff screen lets the reviewer select ANY two patchsets to compare, with inline comments bound to a specific patchset [Review UI Overview — https://gerrit-review.googlesource.com/Documentation/user-review-ui.html (accessed 2026-07-13); Patch Sets — https://gerrit-review.googlesource.com/Documentation/concept-patch-sets.html (accessed 2026-07-13)]. GitHub's weaker equivalent ("changes since your last review") marks comments "outdated" and effectively loses anchors on force-push — a long-standing complaint [Improve workflow when force-pushing during code reviews — https://github.com/orgs/community/discussions/3478 (accessed 2026-07-13)]. Nexus's design sidesteps the rebase problem entirely: the task branch is append-only, so two-dot SHA-pair diffs are exact — closer to Gerrit than to GitHub. For agent-generated-code review, the 2026 tools (CodeRabbit, Copilot code review) converge on: incremental per-push reviews, findings as inline comments with severity, and closing the loop by having an agent apply the fix — CodeRabbit's Autofix "spawns its own coding agent to write the fix and commit to the branch" [AI Code Review Tools Compared — https://www.deployhq.com/blog/ai-code-review-tools-compared-coderabbit-copilot-sourcery-ellipsis (accessed 2026-07-13); CodeRabbit vs GitHub Copilot Code Review (2026) — https://www.morphllm.com/comparisons/coderabbit-vs-copilot (accessed 2026-07-13)]. Nexus's drain-to-retry + verbatim critic patches is the same pattern. What the state of the art has that Nexus lacks: threaded conversations per finding with an explicit resolve/verify state, and reviewer-visible confirmation that a finding was actually fixed (not just "consumed").
**Verdict: PARTIAL** — the Phase-4 design is genuinely state-of-the-art in shape (Gerrit-style pair selection without the rebase problem; findings always visible); the gaps are in follow-through:
- Declare `pygments` and `pypdf` in `app/requirements.txt` — both are load-bearing for this feature (highlighting, PDF text diffs), both are only ad-hoc installed in the live venv; a fresh `install.sh` run yields a review with silently-degraded rendering (review.py:136-141/202-208 swallow the ImportError).
- Build the deferred finding-resolution loop (plan §4.3 tie-in): flip "addressed" chips to "verified fixed" from the reworker's `## Fixes applied` [F#] echo + delta re-judge verdicts — "consumed" currently only means "sent", not "fixed".
- `GET /api/workflows/{id}/review` returns counts, not a reviewable cross-task diff — either render the union diff or relabel the UI (it currently reads as a review).
- Comments are single-shot (no replies); fine for solo use, a real gap for G10 multi-user review discussions.
- Reconcile the plan's `?from=&to=` naming with the landed `?pair=/from_v/to_v` in docs + block2 e2e so the campaign tests the real contract.

### Git integration: worktrees, branch artifacts, PR flow, per-user GitHub
**Intended goal & added value** — Let agents do real work on real repos without ever touching the operator's checkout, make the branch diff itself the deliverable, and close the loop to GitHub (publish/push/tag/PR) under each user's own identity. Serves G2 (fully automated repo work), G3 (branch-files/diff visibility), G8 (PR flow as a real productivity tool), G10 (per-user GitHub attribution). Value: parallel pipelines on one repo can't stomp each other, uncommitted agent work is never lost, and binary outputs created on a branch still surface in the UI.
**Current implementation** — `app/worktree.py`: two worktree systems — per-agent `create_worktree()` (branch `session/<short>`, worktree.py:30) and per-pipeline `ensure_task_worktree()` (branch `nexus/<slug>`, idempotent, stages of one workflow share the branch so implement→review→fix see each other; self-ignoring `.worktrees/.gitignore`, worktree.py:76-104). `base_branch()` = the operator's HEAD; `snapshot_commit()` (worktree.py:115) safety-commits anything the agent left uncommitted (junk pathspecs excluded, author `nexus <nexus@local>`); `capture_diff()` uses three-dot `base...HEAD` (fork-point/merge-base semantics, immune to the base moving on); `changed_files_range()` uses `--no-renames --diff-filter=AM`; `head_sha()`/`capture_diff_between()` power the Phase-4 round diffs. Branch surfacing: `GET /api/tasks/{id}/branch-files[/{name}]` (server.py:4583-4632) lists the branch's diff set and serves single files via `git show` (membership-gated); `_copy_branch_artifacts` (hermes_dispatch.py:1690) mirrors `ARTIFACT_EXTS` files (pdf/docx/pptx/images/…, 50MB/20-file caps, hermes_dispatch.py:1683-1687) into `workspace/artifacts/` at EVERY finalize. PR flow: `POST /api/tasks/{id}/pr` (server.py:11150) verifies branch/origin/commits-ahead, pushes, builds a PR body with review stats + line-comment audit count, `pr.cmd` template (default `gh pr create …`) stubs for gates, stores `pr_url`. `POST /api/projects/publish|push|tag` (server.py:11072/11098/11118). Per-user GitHub: `_github_ctx`/`_github_env` (server.py:10740-10780) — PAT from the encrypted credentials store (provider `github`), `users.github_username/git_email`, token travels ONLY as `GH_TOKEN`/`GITHUB_TOKEN` env + an inline credential helper (never argv or .git/config), https-github origins only, machine `gh` auth as fallback; `GET /api/github/whoami` tests it. Deliverables tab stars the ⭐ primary output client-side (app.js:9875-9889: code→`changes.diff`, else first non-md artifact).
**The proper way (web-researched)** — Worktree-per-agent is the 2026 mainstream pattern for parallel coding agents: one shared object store, one checkout per agent, merge via normal branches — Claude Code ships native `isolation: worktree`, Grok Build runs up to 8 concurrent worktree-isolated subagents [Git Worktrees for Parallel AI Agents: 2026 Guide — https://noqta.tn/en/blog/git-worktrees-parallel-ai-coding-agents-guide-2026 (accessed 2026-07-13)]. The known industry caveat is that worktrees give FILE isolation only — runtime state (ports, dbs, caches) needs its own layer [Git Worktrees Need Runtime Isolation — https://www.penligent.ai/hackinglabs/git-worktrees-need-runtime-isolation-for-parallel-ai-agent-development/ (accessed 2026-07-13)] — which Nexus partially addresses via the separate preview subsystem. For automation identity, best practice has moved from PATs to GitHub Apps with short-lived (1h) installation tokens, app-attributed audit trails and higher rate limits; fine-grained PATs are the accepted middle ground for personal/self-hosted setups, with env-only delivery exactly as done here [Still Using PATs in 2025? Time to move to GitHub Apps — https://bmterra.eu/articles/010625-using-github-apps/ (accessed 2026-07-13); Why GitHub Apps Are Better Than PATs for Automation — https://dev.to/patelaryan66/why-github-apps-are-better-than-personal-access-tokens-for-automation-1lg9 (accessed 2026-07-13)]. Standard hygiene the ecosystem also expects: worktrees are pruned when their branch is merged/abandoned, and machine-made commits carry explicit bot/co-author attribution.
**Verdict: PARTIAL** — the diff mechanics (three-dot capture, snapshot-commit safety net, junk pathspecs, membership-gated file serving) are textbook; lifecycle and identity coherence are not:
- `remove_worktree()` (worktree.py:56) has ZERO call sites — task worktrees under `<repo>/.worktrees/nexus-*` accumulate forever (each with a full checkout); add a prune step on workflow done/delete (project delete already handles the repo dir, not foreign-repo worktrees).
- Attribution mismatch: snapshot commits are authored `nexus <nexus@local>` (worktree.py:125-126) while the push/PR runs as the user's PAT — the PR shows the user, the commits show a non-identity. Author agent commits as the user (`gctx` name/email already exists, server.py:10756-10757) with a `Co-Authored-By: <agent>` trailer, the emerging convention for AI-authored commits.
- Two overlapping worktree systems (`session/<short>` per agent vs `nexus/<slug>` per pipeline) — the per-agent one predates real dispatch; verify it still has a live caller and retire it if not.
- `_run_git` hard-caps at 30s (worktree.py:16) — `capture_diff` on a large branch/repo will silently return "" (caller logs but the review shows nothing); raise per-call timeouts for diff/log operations.
- G10 note: per-user PATs are defensible self-hosted, but the PR body/audit trail should record WHICH user identity performed the push (currently only the activity log line).

### App preview (▶ Test app / Test project)
**Intended goal & added value** — "The task built a program — run it now": one click starts the agent's output on a local port and opens it in a tab; project-level preview runs the WHOLE assembled project at any historical state, side by side with the current one, to spot regressions. This is the strongest G3 feature (see what the tool actually built, live), plus G1 (state picker/logs in one modal), G8 (automated use of dev tooling: npm, venvs, alembic, docker compose). Value: closes the trust gap — the operator verifies behavior, not file listings.
**Current implementation** — `app/app_runner.py`: `detect_app()` (app_runner.py:98) cascades package.json dev/start → `npm install` + `npm run` / app.py|main.py|server.py (+requirements → `.venv-preview`) / index.html → `python -m http.server`; each preview is its own process group (`start_new_session`, killpg on stop) on a dedicated 127.0.0.1 port from 8790-8820, max 3 concurrent, 30-min TTL, `NEXUS_PREVIEW=1` env marker gives PID identity across restarts, registry persists to `workspaces/.preview-apps.json`, `reaper_thread` kills boot orphans + enforces TTL + truncates the 5MB-capped `_preview.log`. Port truth (v3.4): vite scripts get `-- --port <p> --strictPort --host 127.0.0.1` appended (app_runner.py:398) because vite ignores the PORT env and auto-increments a busy config port; any other PORT-ignoring server is adopted from the URL it prints (`_adopt_logged_port`, app_runner.py:345 — ANSI-stripped, `[backend]` lines excluded, last announcement wins). Full stack (v3.5): `detect_backend()` finds a fastapi/uvicorn sibling, starts it in the SAME process group on the frontend's proxy-target port (`_frontend_proxy_port` reads vite `server.proxy`/CRA `proxy`), env seeded from the project's own `.env(.example)`, alembic migrations first, compose infra (image-only services) via the project's own docker-compose.yml with foreign-held host ports remapped through a patched `_preview.compose.yml` + env URL rewrite (`_compose_plan`, app_runner.py:222-261). `app/project_preview.py` (v3.6): repo projects — states = commits `merge-base..nexus/<slug>` + fork-point baseline anchor, materialized read-only via `git archive` (immutable → cached); workspace projects — state vK = overlay of first K done task workspaces, fingerprint-cached on contributors' `updated_at`; runs under registry key `wf:<id>:<state>` so old+new run concurrently; `gc()` deletes unused materializations. Routes: `GET/POST /api/tasks/{id}/app(/start|/stop|/log)`, same for `/api/workflows/{id}/app`; UI `testAppUI`/`projectAppUI` (app.js:3733/3817) with state picker + live log; JARVIS deck ▶ Test reuses `testAppUI`.
**The proper way (web-researched)** — Ephemeral per-change preview environments are now the expected review tool ("expected by every reviewer" in 2026), and the industry standard implementation is container-based: full-stack copy per PR (Okteto/Uffizzi model), virtual clusters, or request-level isolation on a shared baseline, with Docker Compose named as the right starting rung before k8s [Ephemeral Environments — Preview Environment for Every PR — https://core.cz/en/blog/2026/ephemeral-environments-2026/ (accessed 2026-07-13); The Definitive Guide to Preview Environments — https://www.uffizzi.com/preview-environments-guide (accessed 2026-07-13); Best platforms for on-demand preview environments in 2026 — https://northflank.com/blog/best-platforms-for-on-demand-preview-environments (accessed 2026-07-13)]. The key design questions the field has settled: per-preview isolated data vs shared seeded db (Nexus deliberately shares backend+db across states of one project), readiness = HTTP health not TCP, and hard resource ceilings per environment. On the port question, Vite's docs confirm exactly what v3.4 encodes: default behavior auto-increments a busy port and `strictPort: true` is the way to pin it; the PORT env is not part of Vite's contract [Vite server options — https://vite.dev/config/server-options (accessed 2026-07-13)]. Nexus's process-group-on-host approach is the legitimate lightweight LOCAL tier of this practice — the trade-off it accepts is no runtime/resource isolation, the exact gap the worktree-isolation literature flags [penligent, cited above].
**Verdict: PARTIAL** — the port-truth and time-travel engineering is above-industry for a local tool (log-URL adoption, compose port remap, immutable-state caching are all correct and unusual); the gaps are robustness tiers, not wrong design:
- No resource ceilings: an `npm install` + dev server + uvicorn + compose stack runs uncapped in the server's cgroup — three heavy previews can starve Nexus itself. Wrap the process group in `systemd-run --user --scope -p MemoryMax= -p CPUQuota=` (machine already runs systemd user units) or add a container tier for node apps.
- Package-manager blindness: `npm install` is hardcoded (app_runner.py:400) — a pnpm/yarn/bun lockfile project gets a wrong or failed install; detect `pnpm-lock.yaml`/`yarn.lock`/`bun.lockb` and use the matching tool.
- Readiness = TCP `_listening()` only; a server that binds then 500s shows "ready". Add an HTTP GET probe before flipping state (the field's standard health semantics, per the preview-environment guides above).
- Detection cascade stops at node/python/static; agents also produce go/rust/compiled outputs on this stack's roadmap (G7) — at minimum surface "detected nothing runnable, here's why" per marker checked (currently one flat error string, app_runner.py:384).
- The designed backend/db sharing across two states of one project (app_runner.py:408 comment) is a correct cost trade but silently makes "old vs new" comparisons lie when the schema changed — the modal should badge shared-backend mode (the state is already known: `backend_port` answering before start).

### Document & artifact generation (PDF/docx/pptx/xlsx)
**Intended goal & added value** — Agents deliver real office/binary artifacts (decks, spreadsheets, PDF reports, images), not just markdown — BY DESIGN with no dedicated export route: the dispatch framing tells the agent which document libraries are preinstalled and the agent writes per-task Python against them. Serves G8 (PDF creation, image generation/analysis as productivity tools), G7 (any output type), G2 (no human conversion step). Value: one mechanism covers every format, and outputs surface automatically (⭐ primary chip, artifact mirroring, JARVIS deck ▶ Test).
**Current implementation** — No generation endpoint exists; the contract lives in the dispatch framing: `DOC_TOOLS_PY` = this install's own `.venv/bin/python` (hermes_dispatch.py:573), and the framing instructs "If the task calls for binary output formats (pdf, docx, xlsx, pptx, png), produce them as files next to deliverable.md using {DOC_TOOLS_PY} — python-docx, openpyxl, python-pptx, reportlab, pypdf, pillow and markdown are preinstalled there" (hermes_dispatch.py:1056-1058); the mirror-image extraction path tells agents to READ attached pdf/docx/xlsx/pptx the same way (hermes_dispatch.py:1197-1198). Repo-mode tasks additionally copy final deliverable files into the workspace (hermes_dispatch.py:1035) and `_copy_branch_artifacts` mirrors `ARTIFACT_EXTS` binaries (hermes_dispatch.py:1683-1718) into `workspace/artifacts/` at every finalize. Surfacing: `GET /api/deliverables` (server.py:9466) lists workspace files per task; the UI stars the ⭐ primary output (first non-md artifact, or `changes.diff` for code — app.js:9875-9889); PDFs review-diff by extracted text (review.py:261-268); images render in the review; JARVIS deck offers ▶ Test on recent deliverables. Verified library state: the LIVE venv contains reportlab 5.0.0, pypdf 6.14.2, python-docx, openpyxl, python-pptx, pillow, markdown (+pygments) — but `app/requirements.txt` declares only fastapi/uvicorn/psutil/cryptography/sounddevice/evdev, and `install.sh` installs only requirements.txt. The doc stack exists on this machine by ad-hoc pip installs only.
**The proper way (web-researched)** — The "LLM writes Python against openpyxl/python-docx in a code-execution environment" pattern is validated at the frontier: Anthropic's production docx/pptx/xlsx/pdf Agent Skills do exactly this — but each skill pairs the libraries with a workflow spec plus a script toolkit and validation (explicit create/read/edit paths, tracked-changes handling, OOXML structure validation), rather than a bare "libs are preinstalled" sentence [anthropics/skills — https://github.com/anthropics/skills (accessed 2026-07-13); Agent Skills — Claude Platform Docs — https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview (accessed 2026-07-13); Analyzing Anthropic's docx Agent Skill — https://knightli.com/en/2026/04/04/analyze-docx-agent-skill/ (accessed 2026-07-13)]. For the dominant "written report → polished PDF/docx" case, the field uses deterministic converter pipelines, not LLM-coded layout: pandoc (md→docx/pdf/epub, the universal converter), the rising typst engine, or HTML+CSS→PDF via weasyprint/headless-chromium — three engine families with known trade-offs [Pandoc — https://pandoc.org/ (accessed 2026-07-13); Markdown to PDF: The Complete Guide (8 Methods Compared, 2026) — https://mdclaudy.com/blog/markdown-to-pdf (accessed 2026-07-13)]. Best practice mid-2026 is therefore two-tier: LLM produces CONTENT (markdown/structured data) → a template/converter pipeline owns layout and brand consistency; LLM-written generation code is reserved for genuinely bespoke artifacts (complex spreadsheets, custom decks) and is scaffolded by skill recipes + a post-generation validation step (reopen/parse the file before calling it done).
**Verdict: PARTIAL** — the architecture choice (in-workspace generation by the agent, mirror-to-artifacts, no bespoke export routes) is the right pattern and Anthropic-validated, but three concrete gaps undercut G8:
- Undeclared dependencies (hard fresh-install breakage): add reportlab, pypdf, python-docx, openpyxl, python-pptx, pillow, markdown (+pygments for review) to `app/requirements.txt` — today the framing PROMISES libraries that `install.sh` (line 40: `pip install -r requirements.txt`) never installs, so on any machine built from this repo's own runbook, every binary-deliverable task fails at import time.
- No recipe layer: one framing sentence vs Anthropic's per-format skill files means the GLM executor re-derives docx/pptx layout code from scratch every task — ship small per-format recipe snippets (create/edit/validate skeletons) into the framing or as a Hermes skill, mirroring the skills repo's structure.
- No converter tier for reports: `deliverable.md → PDF/docx` should be a deterministic pipeline (pandoc or markdown+weasyprint — weasyprint is pip-installable into the same venv, no LaTeX), with reportlab reserved for bespoke layouts; today reportlab canvas coding is the ONLY pdf path, the weakest-quality/highest-variance option per the toolchain comparisons above.
- No output validation: nothing reopens the generated file (pypdf/python-pptx parse, or LibreOffice --convert-to smoke) before the finalize marks it a deliverable — a truncated/corrupt pptx surfaces only when the operator opens it; wire a cheap parse check into `_copy_branch_artifacts`/finalize.
## Cluster D7 — Multi-User, Settings & Platform UX

### Multi-user accounts & per-user environments
**Intended goal & added value** — G10 is the headline: two real people (owner + one member) share one machine and one
agent fleet, but each gets their own board, projects, deliverables, JARVIS space, models, API keys and learning
ledgers, while lessons/improvements stay shareable. Also serves G3 (admin visibility of member state) and G4
(per-user knowledge overlays feed per-user framing). Value today: the member works without seeing or clobbering the
owner's work, and the single-user machine behaves exactly as before — no login until user #2 exists.
**Current implementation** — `app/auth.py`: login required only when ≥2 active users or `auth.force=1`
(`auth_required()`, 2s-TTL cache); scrypt password hashes; sessions are random 256-bit tokens stored only as sha256
with 30-day sliding expiry (`create_session`/`resolve_session`); in-memory login throttle; `seed_default_user()`
guarantees `u_owner` so every DB row is user-scoped ("no unscoped code path"). A pure-ASGI `AuthMiddleware`
(`app/server.py:33-95`) resolves cookie→user into a contextvar per request, 401s `/api/*` when unauthenticated, and
accepts the per-boot `INTERNAL_TOKEN` + `x-nexus-user` header so in-process engines act AS a task's owner instead of
bypassing scoping; `/ws` authenticates at handshake and `mgr.broadcast(user_id=…)` filters events per user.
Config layers per user: credentials resolve user row → global row → machine env (`secrets_store.resolve_key`);
models resolve per-user `user_models` rows + `model_assignments` over a `'global'` scope (`db.resolve_assignment`);
knowledge resolves member overlay `~/knowledge/users/<uid>/` over owner-canonical files (`onboarding.target_dir`).
Verified per-user surfaces: JARVIS files `workspaces/jarvis/<uid>/files/` (`server.py:2236`); GitHub identity
(`users.github_username/git_email` + credentials provider `github`, PAT tested server-side via `/api/github/whoami`);
per-user feedback ledgers with `/api/feedback/adopt` + `feedback.cross_user_visible` kill switch; admin sees all
users' known-issues (filer join); `POST /api/users` enforces the no-lockout rule (admin must set their own password
first, `server.py:540`); `project_owners` maps project paths to users (untagged paths default to `u_owner`).
**The proper way (web-researched)** — The canonical small-team pattern is exactly this shape: single shared
database, shared schema, a non-negotiable tenant/owner discriminator column on every scoped table, all access
filtered by it — cheapest to operate, simplest to onboard into [Multitenant SaaS Patterns — Azure SQL Database —
https://learn.microsoft.com/en-us/azure/azure-sql/database/saas-tenancy-app-design-patterns (accessed 2026-07-13)].
Best practice adds defense in depth: enforce the filter below the endpoint layer (Postgres RLS, or a single scoped
query/repository layer in app code), because the app "should still filter by tenant, but RLS catches any cases where
that filtering is missed" [Multi-Tenant Data Isolation and Row Level Security — DZone —
https://dzone.com/articles/multi-tenant-data-isolation-row-level-security (accessed 2026-07-13)]. Config layering
with most-specific-wins precedence and automatic fallback to the next layer is the standard model [Learn Layered
Configuration and Overrides — Codefinity — https://codefinity.com/courses/v2/fff6da48-3405-4507-a82d-4863fce92534/46367f55-3285-44f3-855b-de3121eb9493/ea491c96-d99b-4090-84e3-c13bd50c0453
(accessed 2026-07-13)]. Per-user credential handling norm: centralized encrypted storage, per-scope keys, least
privilege, rotation support [Secrets Management — OWASP Cheat Sheet Series —
https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html (accessed 2026-07-13)].
**Verdict: PARTIAL** — the layering architecture (user → global → machine default; overlay → canonical) is textbook
and unusually complete, but isolation rests on hand-written per-endpoint `WHERE user_id=?` clauses across an
11k-line `server.py`, and the owner identity is structurally overloaded.
- Centralize scoping: add owned-row query helpers (e.g. `db.owned_one/owned_all`) and migrate endpoints onto them —
  SQLite has no RLS, so one choke point is the only systematic guard against the next forgotten filter (per the
  DZone/Azure guidance); today `notes_list`, `known_issues_list`, `credentials_delete` each re-implement the rule.
- Decouple "owner" from "shared/General": `u_owner` is simultaneously a person, the canonical knowledge target
  (`onboarding.target_dir`), the General feedback bucket (`list_feedback`), and default owner of untagged projects —
  give shared assets their own scope id so owner handover or a second admin doesn't require data surgery.
- Add an offboarding path: `PATCH /api/users/{id}` deactivates (`server.py:553-577`) but nothing reassigns or exports
  a departed member's tasks/workspaces/credentials/overlay; a "deactivate + reassign to X" flow completes G10.
- `auth.current_user()`'s background fallback to the sole user silently changes meaning once user #2 exists
  (`auth.py:237-246`); audit background writers (scheduler, sweeps) to always carry an explicit user id.

### Onboarding (business-brain wizard)
**Intended goal & added value** — G4: the tool must know the business so outputs fit; the wizard turns the pristine
`~/knowledge` templates (BUSINESS-CONTEXT.md, STYLE-VOICE.md) into filled, agent-readable ground truth via a guided
in-app interview instead of hand-edited markdown. G10: the owner's answers become the canonical files every
agent/judge/eval reads; each member gets a personal overlay so outputs fit *their* context. Value today: the
highest-leverage configuration in the system, with per-section explanations of what agents do with each answer.
**Current implementation** — `app/onboarding.py`: templates carry `{{FILL: hint}}` slots; `parse_template()` derives
positional slot ids (`context:07`), section titles from headings, and labels; `schema()` groups them with
`FILE_INTRO`/`SECTION_EXPLAIN` impact text (the "hand-holding layer"). Answers are per-user rows in
`onboarding_answers` (partial upsert, `na` toggle, un-answer via empty save — `POST /api/onboarding/answers`,
unknown slot ids rejected); `GET /api/onboarding` returns schema + saved answers for resume; `status_for()` powers
the dashboard CTA, with file truth winning once target files exist so hand edits count. `apply_for()`
(`POST /api/onboarding/apply`) renders template+answers (unanswered slots stay `{{FILL}}` to keep inviting
completion), snapshot-commits a dirty knowledge repo FIRST, writes owner→canonical `~/knowledge` vs
member→`~/knowledge/users/<uid>/`, then git-commits per user. UI: `openOnboardingWizard()` modal in
`app/static/app.js` (~729+) with auto-save on Next, section explanations, review counts, confirm-gated apply, and a
dashboard CTA banner. Gates: `verify_onboarding_e2e.py` (27 checks) + `verify_onboarding_ui.py` (12 checks).
**The proper way (web-researched)** — 2026 reference products capture org context by *ingesting artifacts first,
asking questions second*: Jasper Brand Voice builds the voice from up to 8 uploaded examples/files/URLs the AI
analyzes, and Jasper IQ ingests "source of truth" documents (strategy PDFs, style guides) so every output adheres to
them [Brand Voice — Jasper Help Center — https://help.jasper.ai/hc/en-us/articles/18618693085339-Brand-Voice
(accessed 2026-07-13)]; [AI-powered brand voice management — Jasper — https://www.jasper.ai/brand-voice (accessed
2026-07-13)]. Wizard mechanics best practice: progressive steps, a persistent completion checklist (20-30%
completion lift), save/resume across sessions, minutes to first value [SaaS Onboarding Flow: 10 Best Practices That
Reduce Churn (2026) — https://designrevision.com/blog/saas-onboarding-best-practices (accessed 2026-07-13)];
explain each question's value at the point of capture and keep required input minimal [Best User Onboarding
Experiences in 2026 — Userpilot — https://userpilot.com/blog/best-user-onboarding-experience/ (accessed 2026-07-13)].
**Verdict: PARTIAL** — interview mechanics (resume, n/a, impact explanations, git-safe apply, canonical-vs-overlay)
match or beat SaaS wizard practice; missing are the 2026 ingest-first pattern and template-evolution safety.
- Add "AI pre-fill from what you already have": accept a website URL / uploaded docs / past deliverables, one
  drafting call proposes per-slot answers, human confirms per slot — mirrors Jasper's analyze-examples flow and cuts
  the ~37-slot interview to a review pass; the research-then-draft pattern already exists in `models_describe`
  (`server.py:10062`).
- Positional slot ids (`context:07`) silently re-attach answers to the wrong question if a template ever gains or
  reorders a slot (`onboarding.py:141-165`); derive stable ids (hash of section+label) or version templates with a
  migration check — "frozen source of truth" is a convention, not enforced.
- The quarterly-goals section says "update every quarter" but nothing re-prompts once `status_for()` reaches done;
  add a staleness nudge (applied_at age → the CTA reappears for that section only).
- Member overlays cover only the two context files; domain PLAYBOOK/RUBRIC personalization goes through the separate
  lessons pipeline — state that boundary on the wizard's final screen so members know what they did NOT personalize.

### Settings v2 + credentials + model registry
**Intended goal & added value** — G3 (every operational knob visible and editable with plain-language help), G2
(settings drive the automation: dispatch caps, judge/critic loops, autopilot presets), G6 (budgets/price tables),
G10 (per-user credentials + per-user model rows/purpose assignments so each person's work runs on their own key and
model choices). Value today: one generically-rendered Settings tab covers ~100 keys across 13 sections with zero
per-key UI code, and a fresh install behaves identically to pre-registry defaults.
**Current implementation** — `app/settings_registry.py`: declarative `SECTIONS` (dispatch/judge/super/plan/
quality[feedback+autopilot+lessons+exemplars]/agentmem/integrations/paths/auth/voice/vision/dictation/watchdog);
items typed bool/int/float/str/enum/command/path with min/max/options/help/env/restart; `conf()` resolves
settings→env→registry default; `validate()` type-checks; `PREFIXES` derives the endpoint whitelist from the registry
so a new section can't miss it. `GET /api/settings/schema` renders the tab generically; `PATCH /api/settings` is
admin-only and empty value = back-to-default with explicit pinning because "code-site fallbacks are not all
identical" (`server.py:9840-9853`). Credentials: `app/secrets_store.py` Fernet-encrypts per-user + global rows under
the machine key `app/secret.key` (0600, race-safe create); the API returns metadata + 4-char hint only — plaintext
exits solely via `resolve_key()` on execution paths (dispatch bridge `~/.hermes/session-keys.json`, written
0600/atomic by `hermes_dispatch._rewrite_session_keys` and read per request by the zai plugin; judge subprocess
env). Machine defaults rotate through a fixed provider→env allowlist (`DEFAULT_PROVIDERS`, anchored atomic rewrite
of `~/.hermes/.env`). Model registry: `user_models` (global NULL rows + per-user; seeded GLM trio + Opus judge) +
`model_assignments` (purposes complicated/easy/mechanical/frontier_judge/spec_model/escalation_model; user scope
over `'global'`); `PUT /api/models/assignments` validates route compatibility (worker purposes need `hermes`,
judge-class need `cli`); ✨ `POST /api/models/{id}/describe` web-researches a reviewable routing description draft.
**The proper way (web-researched)** — Config-driven UI with the schema as single source of truth is the current
pattern: define structure/validation once, render generically, derive whitelists/defaults from the same artifact so
interface and implementation can't drift ("interface-as-code") [Mastering Config-Driven UI — dev.to —
https://dev.to/lovishduggal/mastering-config-driven-ui-a-beginners-guide-to-flexible-and-scalable-interfaces-3l91
(accessed 2026-07-13)]; [REGAL: A Registry-Driven Architecture for Deterministic Grounding — arXiv —
https://arxiv.org/pdf/2603.03018 (accessed 2026-07-13)]. The LLM-specific reference is LiteLLM's gateway model: a
model registry with per-user/team key scoping, model-access lists and budgets attached to virtual keys, raw provider
keys never exposed, admin UI showing spend per key [Virtual Keys — LiteLLM —
https://docs.litellm.ai/docs/proxy/virtual_keys (accessed 2026-07-13)]; [Budgets, Rate Limits — LiteLLM —
https://docs.litellm.ai/docs/proxy/users (accessed 2026-07-13)]. Credential UX norm: write-only secrets, masked
display with short hint, in-place rotation, per-scope resolution [Secrets Management — OWASP Cheat Sheet Series —
https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html (accessed 2026-07-13)].
**Verdict: PARTIAL** — the registry, credential UX and purpose-routing genuinely match the 2026 pattern
(registry-derived whitelist, masked hints, route validation exceed typical); the stub-hook settings class and split
default resolution are real, historied defects.
- Sweep the stub/test-hook class: `judge.cmd`, `super.critic_cmd`, `evals.stub`, `evals.improve_cmd`, `plan.stub`,
  `plan.critique_cmd`, `agentmem.stub`, `lessons.cmd` are production settings doubling as gate stubs with only a
  "restore after testing" help note — the judge-stub leak (2026-07-08→11, silent instant-REVISE on every task)
  proved the failure mode. The hardened pattern already exists for `dispatch.stub_stream` (honored only with
  `NEXUS_GATE_STUB=1` in-process AND boot-cleared — `server.py:168-176`, `hermes_dispatch.py:2018`); apply the same
  env-gate + boot-clear to every stub knob, or move stubs out of the settings table entirely.
- Kill dual default resolution: many call sites read `db.get_setting(key, "literal")` with their own hard-coded
  default instead of `sreg.conf(key)` (e.g. `dispatch.daily_cap` at `server.py:6496`, `feedback.cross_user_visible`
  at `server.py:6114`); the registry itself admits the drift — make `sreg.conf` the single read path and lint raw
  two-arg `get_setting` calls in verify.sh.
- Settings changes log one activity line but keep no old→new history; add a small `settings_audit` table
  (key, old, new, user, ts) so "who turned the judge off" is answerable — LiteLLM-class admin UIs expose this.
- Per-user model rows exist but per-user *budgets* don't (budgets are global dispatch settings); for G10 parity with
  the gateway pattern, add per-user daily caps resolved like model assignments.

### Notes + Known Issues + User Manual + guided tour
**Intended goal & added value** — G8 (notes: capture ideas without leaving the current view, optionally pinned to
the project in focus) and G1/G3 (known issues: an in-app improvement queue carrying interaction context; manual +
tours: the system explains itself so a non-technical member can operate it — directly serving G10's "member can use
it" requirement). The value of these small features is reduced tool-switching and less support-by-owner.
**Current implementation** — Notes: `notes` table (user_id, text ≤8k, project_path/name, workflow_id/name;
`server.py:10177-10221`, user-scoped CRUD, 500-row cap); the 📝 fixed button opens a bottom-left NON-modal panel
(`notesPanelEl`, app.js ~3185) saving as General or to the current focus context; a Notes tab offers
date/project/workflow sort + filters. Known Issues: `known_issues` table (view, feedback ≤4k, `context` JSON ≤20k,
status new/in_progress/resolved, user_id); the frontend `api()` wrapper records recent non-GET calls as breadcrumbs
filed as context with each report (app.js ~103); nav badge; admins see/edit/delete ALL users' reports with a filer
chip, members their own (`server.py:10226-10289`). Manual: `viewManual()` (app.js 1930+) is a 13-chapter in-app
plain-language document (first steps → quality machinery → users & remote access → costs → troubleshooting → full
technical architecture). Tour: the `TOURS` registry keys steps by view plus popup contexts (task-detail/task-create/
wizard modals, agent drawer); `startTour()` filters steps to selectors present in the DOM, renders a spotlight +
positioned card with back/next, and falls back to the manual when a view has no steps; the topbar `?` is
context-aware (`tourContext()`), and modals get their own `?` (app.js 2253+, 8725).
**The proper way (web-researched)** — 2026 guidance: help should be contextual and embedded rather than a static
external repository; new users need tours/checklists, existing users tooltips, searchers reactive help — and short
tours win decisively (3-step tours ~72% completion vs ~16% at 7 steps) [Contextual Help UX in 2026 — Chameleon —
https://www.chameleon.io/blog/contextual-help-ux (accessed 2026-07-13)]; [Product Tours: The Ultimate Guide to
In-App Guidance — Adoptkit — https://www.adoptkit.com/posts/product-tours-ultimate-guide-in-app (accessed
2026-07-13)]. In-app resource centers measurably cut support load (e.g. −25% chat requests) [How to Use In-app Help
to Improve Customer Onboarding — Userpilot — https://userpilot.com/blog/in-app-help/ (accessed 2026-07-13)].
Bug-report widgets should auto-capture visual/technical/environment/user/behavior context so engineers reproduce
without asking, while keeping the first response lightweight [In-App Bug Reporting: The Complete Guide — Gleap —
https://www.gleap.io/blog/in-app-bug-reporting-guide (accessed 2026-07-13)].
**Verdict: PARTIAL** — all four earn their place (correctly user-scoped, non-modal capture, context-carrying
reports, per-view tours mostly ≤4 steps — this IS the recommended embedded-help shape for a 2-user deployment);
the gaps are maintenance and loop-closure, not existence.
- The manual and `TOURS` are hand-maintained static strings in `app.js` — every feature batch risks silent drift
  (the manual already references `scripts/setup_tailscale.sh`/`auth_reset.py` that live server-side only); add a
  verify.sh check that each nav view has a TOURS entry and manual chapter anchors resolve, so drift fails the gate.
- Known issues are a dead-end queue: nothing downstream reads them (Q2 distillation reads `edit_evidence`, not
  `known_issues`) and there's no export; feed resolved/new issue text into the evidence pipeline or add a one-click
  "copy as task" so the improvement queue actually drains (Gleap-class tools route reports into the tracker).
- Notes have no free-text search and no markdown rendering (`viewNotes` filters/sorts only); at the 500-row cap a
  search box is a small fix with daily G8 impact.
- Tour steps silently vanish when selectors are missing (`filter(s => document.querySelector(s.sel))`, app.js 2256)
  — graceful, but add a dev-mode console warn so selector rot gets noticed.

### Observability & usage
**Intended goal & added value** — G6 (economics visibility: where tokens/dollars go across GLM, the Claude
subscription, Hermes, and the quality loop) and G3 (live system visibility: activity feed, monitor, Langfuse
traces). Value today: the Usage tab is the only place the frontier judge/critic/escalation spend — which bills the
Claude subscription invisibly — surfaces as its own line; `/api/quota` shows burn against the daily cap and
per-model in-flight slots.
**Current implementation** — Observability tab: `GET /api/observability` (`server.py:1062`) proxies the self-hosted
Langfuse `/api/public/metrics/daily` with Basic auth from credential rows or `HERMES_LANGFUSE_*` env, aggregates
totals/daily/per-model, and fails soft (`configured:false` / `error` → the UI shows setup guidance or "is the stack
running?" plus an Open-Langfuse deep link; app.js 6774-6842). Usage tab: `tools_hub.get_usage()` (60s cache) merges
three sources — Claude-Code transcript JSONLs (`~/.claude-glm`, `~/.claude`; deduped usage snapshots, cache-token
pricing), Hermes `state.db` sessions' real billing counters, and the C3 `frontier_ledger` rendered as the "Quality
Loop" split (judge/judge_screen/critic/escalation/judge_eval/premortem, per-day, labeled as billing the
subscription) — plus provider cards, 14-day trend, per-model table, top projects (`viewUsage`). `GET /api/quota`
(`server.py:6486`): backoff state, today's dispatch tokens vs `dispatch.daily_cap`, blocked tasks, per-model
in-flight vs caps. Monitor tab: psutil CPU/mem/net/disk with live Chart.js incl. per-agent CPU (`viewMonitor`,
app.js 5172). Activity: `activity` table via `db.log_activity(user_id=…)`; `GET /api/activity` returns own + system
rows; `/ws` broadcasts are user-filtered; `broadcast_threadsafe` bridges sync threads (`server.py:306-351`). No
in-app service-log viewer exists — `journalctl` remains terminal-side; worker stderr lands in `app/logs/*.log`.
**The proper way (web-researched)** — The 2026 LLM-observability baseline is traces + metrics + events: per-request
traces across prompts/tools, aggregated cost/latency/quality metrics, and alert-type events; cost tracking must
capture input/output tokens, model and USD per call, with budget alerts at 50/80/100% thresholds because "one
runaway prompt can burn thousands overnight" [LLM Monitoring Best Practices: Complete Guide for 2026 — OpenObserve —
https://openobserve.ai/blog/llm-monitoring-best-practices/ (accessed 2026-07-13)]; [The complete guide to LLM
observability for 2026 — Portkey — https://portkey.ai/blog/the-complete-guide-to-llm-observability/ (accessed
2026-07-13)]. Per-user/per-key cost attribution is the norm (spend per key/team, per-user threshold alerts) [From
Bills to Budgets: How to Track LLM Token Usage and Cost Per User — Traceloop —
https://www.traceloop.com/blog/from-bills-to-budgets-how-to-track-llm-token-usage-and-cost-per-user (accessed
2026-07-13)]. Langfuse self-hosted is a first-class trace layer; note its current API direction is Metrics API v2,
with the daily-metrics endpoint absent from current docs — fine for a pinned self-hosted version, a version-upgrade
risk [Langfuse Public API — https://langfuse.com/docs/api-and-data-platform/features/public-api (accessed 2026-07-13)].
**Verdict: PARTIAL** — the stack shape is right (Langfuse for traces, a ledger for frontier spend, a spend
dashboard, hard caps + backoff), but the dashboard's headline dollars come from two contradictory price tables and
the alerting third of the baseline is absent.
- Reconcile the price tables: `tools_hub.PRICE_TABLE` (glm-5.2 $0.5/$0.5, claude-opus $15/$75) contradicts
  `database.MODEL_PRICES_SEED`/`cost.model_prices` (GLM-5.2 $1.40/$4.40, Opus 4.8 $5/$25) — the Usage totals and the
  Quality-Loop ledger on the SAME page price the same models differently (up to ~9× on GLM output); make
  `db.model_prices()` the single source and delete `PRICE_TABLE`, whose "Configurable via settings" comment is false
  (`tools_hub.py:424-434, 588-595` never read settings).
- Add threshold alerting: `/api/quota` computes `pct_of_daily_cap` but nothing notifies at 50/80/100% (only the hard
  block at the cap); wire a decisions-inbox card or activity WARN + toast at thresholds, including the
  `frontier.task_cost_cap_usd` ledger (OpenObserve/Portkey guidance above).
- Per-user attribution is missing from Usage (G10×G6): transcripts and Hermes counters are machine-global while
  `dispatches` and `frontier_ledger.user_id` already carry user ids — add a per-user split so the owner sees member
  spend (Traceloop pattern).
- Surface service logs read-only in-app (tail `app/logs/worker-*.log`, plus a bounded `journalctl --user -u nexus`
  subprocess) or drop the troubleshooting manual's implication that the app covers it — today log access requires
  SSH, contradicting the G3 no-terminal-visibility goal.
- Pin/verify the Langfuse endpoint: probe `/api/public/metrics/daily` at boot and log a warning when a future
  self-hosted upgrade removes it in favor of Metrics API v2 (Langfuse docs above).
## Cluster D8 — Substrate: Hermes Seam, Frontend, Data, Ops

### Hermes integration seam
**Intended goal & added value** — Hermes (the GLM executor runtime) is Nexus's entire execution engine: every task
dispatch, JARVIS turn, wizard call and eval run is a session turn against the gateway on :8642. G2 (full automation)
and G5 (frontier techniques on connected models) stand directly on this seam; G10 rides the per-user key bridge.
The seam's added value is everything upstream lacks: per-session models that actually apply, a task stop that
actually aborts the run, per-user keys/effort on the wire, specialist memory scoping — plus a frontier-judgment
layer (Claude CLI bridges) bolted onto a cheap GLM executor. Without it, routing/stop/multi-user billing are cosmetic.
**Current implementation** — Upstream pinned at Hermes v0.18.0 commit `048270fa069f` (`setup/CLAUDE.md` Step 1).
All Nexus→Hermes traffic goes through `app/hermes_dispatch.py` against `http://127.0.0.1:8642` (setting
`hermes.api_base`); its docstring records source-verified API facts (SSE contract, orphan-run harvest, session
persistence in `~/.hermes/state.db`) — a de-facto adapter boundary. 18 specialist definitions in
`setup/hermes/agents/*.md` (+`archive/`). The guardian (`setup/guardian/guardian.py`, `hermes-guardian.timer`
boot+15min) tracks 8 core-source patches in `setup/guardian/core-mods.json`, each a git patch with a unique
sentinel; it is PASSIVE by default (verify+report), re-asserts only when the Hermes repo's HEAD moved
(`was_update`), holds same-line conflicts for a human decision in the Guardian tab, and honors standing decisions
(`accept_upstream` / one-shot `keep_ours` via `git apply --3way`) — see `reconcile_core_mods()`. Keystone mods:
`session-model-api-server` (per-session models become real), `session-run-stop` (⏹ aborts the upstream run),
`zai-prompt-fingerprint` (rewords the phrase Z.AI 429-blocks), four mem0/specialist scoping mods, langfuse fixes.
A same-name override plugin `setup/hermes/plugins/model-providers/zai/__init__.py` (survives `hermes update` in
`~/.hermes/plugins/`) adds `reasoning_effort` on the wire and reads per-session keys/efforts from the mtime-cached
`~/.hermes/session-keys.json` bridge published by dispatch. Vendored frontier CLIs `setup/bin/{cjudge,cverify,
cexec,cspec,creview,cdistill,cimprove}` are bash wrappers each driving one headless `claude` turn.
**The proper way (web-researched)** — Downstream-patch practice for building on moving OSS: keep changes as atomic
commits, rebase against upstream frequently (even automated in CI), and upstream what you can — "from the moment
upstream adopts those changes, they are no longer yours to maintain" [How to fork: Best practices and guide —
https://joaquimrocha.com/how-to-fork/ (accessed 2026-07-13)]. A patch stack frozen against one pinned commit is the
weakest variant: it never exercises forward compatibility, so conflict debt stays invisible until an upgrade is
forced. Isolating a foreign runtime behind an adapter/anti-corruption layer — translating its model at one boundary
— is the standard architecture for this dependency shape [Anti-Corruption Layer pattern — Azure Architecture Center
— https://learn.microsoft.com/en-us/azure/architecture/patterns/anti-corruption-layer (accessed 2026-07-13)].
On replacement: the mid-2026 landscape splits into provider-native SDKs (Claude Agent SDK, now a general-purpose
runtime) and independent frameworks (LangGraph as the durable-execution default, OpenHands as the open dev-agent
environment) [AI Agent Frameworks (2026 Update): 8 SDKs Compared — https://www.morphllm.com/ai-agent-framework
(accessed 2026-07-13)]; [2026 AI Agent Framework Showdown — https://qubittool.com/blog/ai-agent-framework-comparison-2026
(accessed 2026-07-13)]. Swapping executors means re-implementing the exact semantics Nexus encodes (session
persistence, disconnect-survives-run harvest, synchronous delegate) for no new capability.
**Verdict: PARTIAL** — pin + sentinel-checked patches + a passive conflict-surfacing guardian is a sound way to
build on a moving OSS runtime (better than a hard fork or loose edits), but it is a *frozen* fork today: no upgrade
story, no patch-shrinking effort.
- Convert the 8 patches into commits on a fork branch of `~/.hermes/hermes-agent` (today they exist only as
  `.patch` files valid against `048270fa069f` in `setup/guardian/patches/`); run a periodic rebase drill onto
  upstream HEAD in a scratch clone so conflict debt is measured, not discovered [joaquimrocha.com].
- Propose `session-model-api-server` and `session-run-stop` upstream to Nous — both are bugfix-shaped (upstream
  ignores stored per-session models; upstream's stop misses session-chat runs); each accepted PR permanently
  deletes a guardian patch and its `impact_if_dropped` risk.
- Do NOT replace Hermes with LangGraph/Claude-Agent-SDK/OpenHands at 2-user scale: `hermes_dispatch.py`/`worker.py`
  already deliver harvest/resume/stop semantics a swap would have to rebuild, and GLM subscription economics are
  the point. Keep `hermes_dispatch.py` as the single adapter boundary (it already is for dispatch traffic).
- Give the pin an owner and review cadence in `setup/CLAUDE.md`: it says "pin" but names no condition under which
  the pin ever moves, so upstream bug fixes never flow in by default.

### Frontend architecture
**Intended goal & added value** — G1 (organized modern GUI) and G3 (visibility) are delivered by one hand-rolled
vanilla stack; the deliberate house rule is "No build step... no npm, no bundler, no node_modules"
(`app/CLAUDE.md` Key Design Rules) so any agent session can edit a file and reload — no toolchain to break
mid-campaign. One `app.js` renders the whole OS: 23 sidebar views, live board, streaming JARVIS, settings,
guardian panel. The value is edit-latency and zero toolchain risk, at the cost of one very large file.
**Current implementation** — `app/static/app.js` is 11,578 lines: 514 top-level `function`/`async function`
declarations and ~100 top-level `const/let/var` globals. `index.html` (112 lines) is the shell: 23 `data-view`
nav items (Command/Intelligence/System/Insights groups + JARVIS); `render()` (app.js ~614) is an if/else chain
dispatching to `viewX()` + `bindX()` pairs; `switchView()` (586) manages per-view rebuild flags
(`agentsBuilt`/`dashBuilt`/`monBuilt`). Live layer: WS `/ws` (312) feeds `softRender()` (378), which re-renders
only when `uiLocked()` (393 — modal/drawer/drag guards) allows; `tick()` (501) runs every 3s and patches DOM
*in place* for dashboard/agents/monitor, re-rendering kanban/agentic only on data-hash change (house rule: no
blind innerHTML rebuilds on tick — they eat clicks/focus); JARVIS/chat streams read SSE via `fetch` +
`resp.body.getReader()` (8092); `/ws/jarvis/tts` (7350) streams raw PCM. `esc()` (app.js:30, `&<>"'` entity
encoding) has ~650 call sites — the "all server data through esc()" rule is followed and `scripts/verify.sh`
enforces the discipline. Cache-busting is a manual `?v=N` bump per asset (`style.css?v=27`, `app.js?v=109`).
three.js r160 addons + lipsync are vendored (`static/vendor/threejsm` 248K, `_VENDORING.md`), while Google Fonts
and `chart.js@4.4.1` still load from CDNs (index.html:7–11). Maintainability signals: `DEV_SPECIALISTS` is
hand-mirrored from `routing.py` with a literal "keep in sync by hand" comment (app.js:34–36); the 3D files
already load as `type=module` (index.html:107–109). No dead views: all 23 nav items have live render branches.
**The proper way (web-researched)** — Native ES modules + import maps are the mainstream no-build path in
2025/26: the browser resolves bare specifiers itself and the files in the editor are exactly the files delivered
[JavaScript Modules in 2025: ESM, Import Maps & Best Practices —
https://siddsr0015.medium.com/javascript-modules-in-2025-esm-import-maps-best-practices-7b6996fa8ea3 (accessed
2026-07-13)]; whole component stacks (Lit, Shoelace) run buildless through import maps [Buildless workflow through
import maps — https://dev.to/matsuuu/buildless-workflow-through-import-maps-featuring-lit-shoelace-and-more-4ill
(accessed 2026-07-13)]. MDN's guidance: programs of this complexity need splitting into modules; unbundled files
are also cache-friendly — only changed files invalidate, versus re-shipping one bundle for any change
[JavaScript modules — MDN — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Modules (accessed
2026-07-13)]. Buildless is a recognized deliberate stance whose real trade is minification/tree-shaking and
request waterfalls — immaterial on a localhost single-node app [Going Buildless — Max Böck —
https://mxb.dev/blog/buildless/ (accessed 2026-07-13)]. A build step earns its cost only when you need compilation
(types, JSX/Svelte), dependency-graph optimization at scale, or npm-ecosystem depth — none needed here.
**Verdict: PARTIAL** — no-build vanilla at this scale is defensible and the tick/softRender/esc discipline is
genuinely good; the unforced error is conflating "no build" with "one file" — the repo's own module-loaded 3D
files prove the constraint doesn't require an 11.5k-line monolith.
- Split `app.js` into ~12–18 native ES modules by view/domain (`core.js` for state+helpers+esc, `views/kanban.js`,
  `views/settings.js`, `jarvis/*.js`) loaded via `type=module` (+ import map if bare specifiers are wanted) —
  zero build retained; per-file `?v=` bumps replace the all-or-nothing `app.js?v=109` invalidation [MDN].
- Consolidate the ~100 top-level globals into one exported `state` object with explicit per-view ownership;
  today any of 514 functions can touch any global — the main correctness hazard for the fix campaign.
- Vendor `chart.js` and self-host the two fonts: `static/vendor/` + `_VENDORING.md` already establish the offline
  stance, and index.html:7–11 contradicts it (dashboard degrades on CDN outage while three.js was vendored).
- Serve `DEV_SPECIALISTS` (app.js:34) from the existing `/api/specialists/names` endpoint instead of the
  hand-sync mirror of `routing.DEV_SPECIALISTS`.
- Do NOT adopt a framework or bundler at 2-user scale: the Playwright gates (`verify_v3_ui.py` etc.) hold the UI
  contract, and a rewrite buys nothing G1/G3 need.

### Data layer
**Intended goal & added value** — `nexus.db` is the single source of truth for the whole OS: the kanban board
doubles as the dispatch queue, plus settings, encrypted credentials, review comments, the frontier cost ledger,
agent memory, users. G2 (automation), G3 (visibility) and G10 (multi-user) all read/write here; every other
cluster is state kept in this one file. SQLite keeps ops at zero for a single node — no server, no pool,
backup = a file (when done right).
**Current implementation** — `app/database.py` (1,130 lines). Connections are thread-local with
`PRAGMA journal_mode=WAL`, `foreign_keys=ON`, and an explicit `busy_timeout=10000` (lines 15–25). `init_db()`
(line 30) declares ~33 `CREATE TABLE IF NOT EXISTS` tables (agents, tasks, workflows, settings, credentials,
review_comments, frontier_ledger, memory, users, eval_runs/results, plan_sessions, notes, meeting_meta, …).
Migrations are hand-rolled and additive: ~20 `PRAGMA table_info(x)` probes each followed by
`ALTER TABLE … ADD COLUMN` when missing (e.g. lines 219, 234, 355, 493), plus one-time backfills (the `u_owner`
multi-user seeding, lines 514–549). No schema version stamp (`PRAGMA user_version` unused), no down-migrations,
no framework. Backups: **no code path exists** — grep for `backup|wal_checkpoint|integrity_check|VACUUM` across
`app/*.py` returns nothing; the six `nexus.db.bak-*` files (phase1/3/5/7, pre-quality-program, pre-block1;
gitignored via `app/.gitignore:15`) are manual `cp` snapshots taken WITHOUT the companion `-wal` file. The live
`-wal` is currently 4.15MB against a 4.6MB db — a plain-cp snapshot can silently miss roughly half the recent
state. Artifacts are correctly OUT of the DB: `workspaces/task-<8hex>/` (258 dirs today),
`workspaces/workflow-wf-*/`, `_critic/` sandboxes, `evals/`, `jarvis/<uid>/files/` — the DB stores paths/state only.
**The proper way (web-researched)** — Copying a live WAL database with `cp` is the canonical anti-pattern:
grabbing the `.db` without its `.wal` loses recent transactions, and copying both at different instants produces
temporal mismatches; the safe primitives are the Online Backup API (`.backup`) or `VACUUM INTO`, both consistent
under concurrent writers [Ensuring Consistent Backups in SQLite WAL Mode —
https://sqlite.work/ensuring-consistent-backups-in-sqlite-wal-mode-without-disrupting-writers/ (accessed
2026-07-13)]; [Backup strategies for SQLite in production — https://oldmoe.blog/2024/04/30/backup-strategies-for-sqlite-in-production/
(accessed 2026-07-13)]. For continuous protection, Litestream tails the WAL and streams it to S3/SFTP with
point-in-time restore, as one systemd service with a small YAML — the 2025 default for production SQLite on one
node [Litestream — https://litestream.io/ (accessed 2026-07-13)]; [LiteFS vs Litestream vs rqlite on VPS in 2025 —
https://onidel.com/blog/sqlite-replication-vps-2025 (accessed 2026-07-13)]. Long-running services should keep the
WAL bounded (auto-checkpoint runs at commit by default; periodic `wal_checkpoint(TRUNCATE)` off the hot path;
long-lived readers pin the WAL) [SQLite Write-Ahead Logging — https://sqlite.org/wal.html (accessed 2026-07-13)].
Hand-rolled migrations are respectable for SQLite when versioned via `PRAGMA user_version`; Alembic's batch
move-and-copy only pays off with SQLAlchemy models and non-additive changes [suckless SQLite schema migrations in
python — https://eskerda.com/sqlite-schema-migrations-python/ (accessed 2026-07-13)].
**Verdict: PARTIAL** — engine configuration (WAL, busy_timeout, FK on) and the DB-vs-filesystem artifact split
are right; backup practice and schema-version hygiene are below par, and backup is the one that can lose the substrate.
- Replace manual `cp` snapshots with a scheduled `VACUUM INTO 'backups/nexus-<date>.db'` (or `sqlite3 .backup`)
  job on the EXISTING `scheduler.py` cron thread + retention sweep — consistent-by-construction, ~15 lines,
  direct payoff at 2-user scale [oldmoe.blog; sqlite.work].
- Add Litestream replicating to any off-box/off-disk target if the operator wants disaster recovery at all —
  today `nexus.db` has zero copies off this one disk, the exact failure mode the owner already flagged for
  unpushed git work [litestream.io].
- Stamp `PRAGMA user_version` at the end of `init_db()` and gate the additive blocks on it: turns ~20 per-boot
  `table_info` probes into a one-shot ordered path and gives the campaign a place for non-additive changes [eskerda.com].
- Add a weekly `PRAGMA integrity_check` + `wal_checkpoint(TRUNCATE)` scheduler job that files a Known Issues card
  on failure — the 4.15MB WAL suggests checkpoints only barely keep up under the always-on `/ws` reader load
  [sqlite.org/wal.html].
- Do NOT move to Postgres/rqlite: two users, one node, one writer process — SQLite is the correct engine [onidel.com].

### Service topology & ops
**Intended goal & added value** — The runtime substrate everything else stands on: G2 needs services that come up
in order, drain cleanly, and self-heal; G3 needs the dashboard reachable; the load-bearing symlink makes the repo
the live tree (edit → commit → running code, no snapshot step). The manual-start posture (NOTHING autostarts) is
a deliberate product decision for a shared 12GB-GPU desktop — the machine is a workstation first, an agent host
on demand.
**Current implementation** — systemd *user* units in `setup/systemd/`: `nexus.service` (WorkingDirectory
`~/nexus-agent-os` → `start.sh`, which sets CUDA `LD_LIBRARY_PATH` and `exec .venv/bin/python main.py`;
`Restart=on-failure`, `TimeoutStopSec=25` paired with app-side `timeout_graceful_shutdown=8`; `After/Wants`
gateway + ydotool + cleanup-llm, all documented fail-soft), `hermes-gateway.service` (`Restart=always`,
`KillMode=mixed`, `ExecStopPost` cgroup cleanup, explicit venv PATH incl. `~/.npm-global/bin`),
`nexus-cleanup-llm.service` (a second fully-isolated ollama on :11435 with own models dir, f16 KV cache,
`OLLAMA_KEEP_ALIVE=2m`), `hermes-guardian.timer` (boot + 15min, `Persistent=true`) + reflect/prune timers.
Bring-up: `setup/bin/nexus-up` — idempotent, flock single-instance, logs to `~/.local/state/nexus-up.log`, ONE
sudoers-scoped root action (`systemctl start ollama.service`), docker containers `restart:no` started by name
with a compose-label fallback filtered to own projects, a health probe that counts 401 as alive, then opens the
HTTPS self-signed dashboard on :8777 (`cert.pem`/`cert.key` in `app/`). The symlink
`~/nexus-agent-os → …/Nexus-Agentic-Coding-Setup/app` (verified) is load-bearing: unit paths, absolute workspace
paths in nexus.db, and venv shebangs resolve through it; the worktree rule exists because a bare `git checkout`
swaps the RUNNING code. Restart-prep ⏻ (`/api/system/prepare-restart`) pauses dispatch and drains in-flight work;
startup restores (reboot-tested 2026-07-12). `watchdog.py` respawns dead/stuck agent lanes, with a
`SHUTTING_DOWN` event so a stopping service never resurrects its own SIGTERM'd workers. GPU co-residency on the
12GB card: `gpu_lock.py` is a cross-process fcntl-flock arbiter (acquire timeout → run unserialized — "degrade,
never deadlock"; the kernel releases on process death); STT worker killed after 300s idle, vision worker after
600s (process exit is the VRAM guarantee), VLM `keep_alive` 60s, dictation model 2m, ollama capped at 2 models.
**The proper way (web-researched)** — systemd hardening directives (NoNewPrivileges, ProtectSystem, PrivateTmp,
tight capability sets) are the free robustness layer for long-running services, applied via drop-ins and measured
with `systemd-analyze security` [systemd service sandboxing and security hardening 101 —
https://www.ctrl.blog/entry/systemd-service-hardening.html (accessed 2026-07-13)]. Live-service deploys on one
node use immutable `releases/<n>/` directories with an atomic symlink swap (`mv -T`, a single rename(2) syscall)
and N old releases kept for instant rollback [The atomic symlink swap — Deployer —
https://deployer.org/blog/atomic-symlinks (accessed 2026-07-13)]; [Atomic Deployments from Scratch —
https://stevegrunwell.com/blog/atomic-deployments-from-scratch/ (accessed 2026-07-13)]. GPU model lifecycle
practice for ollama-class hosts: per-request `keep_alive` overrides + `OLLAMA_MAX_LOADED_MODELS` sized to VRAM,
with short keep-alives to juggle more models than the card holds at once [Ollama FAQ —
https://docs.ollama.com/faq (accessed 2026-07-13)]; [Ollama model reloading & VRAM fix (2026) —
https://www.runaihome.com/blog/ollama-model-keeps-reloading-vram-fix-2026/ (accessed 2026-07-13)]. Single-node
ops also expects automated backup/DR (covered in the Data layer entry above).
**Verdict: PARTIAL** — bring-up, drain/restore, lane self-healing and especially the GPU lifecycle are unusually
strong and match researched practice; the gaps are deploy safety around the load-bearing symlink and hang (not
crash) detection for the server itself.
- Formalize deploy-as-release using tools already in use: run the service from a dedicated release worktree and
  make "deploy" = `git worktree add releases/<sha>` → repoint `~/nexus-agent-os` atomically (`ln -sfn`/`mv -T`)
  → `systemctl --user restart nexus`. Same symlink contract, but the "bare checkout swaps running code" footgun
  becomes impossible by construction and rollback is re-pointing to the previous worktree [deployer.org].
- Add hang detection for `nexus.service`: `Restart=on-failure` catches exits and `watchdog.py` watches the
  *lanes*, but nothing watches the server process itself — either `WatchdogSec=` + sd_notify pings from the main
  loop, or a 1-min systemd timer curling `/api/health` and restarting the unit on repeated timeouts.
- Apply the basic hardening block (NoNewPrivileges, PrivateTmp, ProtectSystem with `ReadWritePaths` for `app/` +
  `~/.hermes`) to the three user units and check with `systemd-analyze security` — near-zero effort, real
  fault-containment payoff even at 2 users [ctrl.blog].
- Replace hardcoded `/home/sinep` paths in `nexus.service`/`hermes-gateway.service` with the `%h` specifier —
  `nexus-cleanup-llm.service` already uses `%h`, so the fleet is inconsistent and `install.sh` must rewrite the
  others per machine.
- GPU management: no change — the flock arbiter + differentiated keep-alives + kill-the-worker VRAM guarantees
  already meet or exceed documented practice for a 12GB single card; a GPU scheduler daemon would be
  over-engineering at this scale [docs.ollama.com/faq].
