# Nexus Agent OS + Hermes — Complete System Documentation

*Canonical single-document reference, 2026-07-15. This file documents the whole
system — every feature, the architecture behind it, and an honest assessment of
its added value, strengths, and weaknesses. It supersedes
`app/docs/PROJECT-DOCUMENTATION.md` (2026-07-07). The in-app **User Manual**
tab carries the plain-language operator version; per-subsystem specs (listed in
§15) remain the source of truth for implementation invariants.*

---

## Contents

1. [What this is](#1-what-this-is)
2. [Architecture](#2-architecture)
3. [The task execution pipeline](#3-the-task-execution-pipeline)
4. [The planning layer](#4-the-planning-layer)
5. [The quality machinery](#5-the-quality-machinery)
6. [Repo-native coding](#6-repo-native-coding)
7. [Memory and learning](#7-memory-and-learning)
8. [Multi-user and security](#8-multi-user-and-security)
9. [JARVIS: voice, vision, dictation](#9-jarvis-voice-vision-dictation)
10. [The user interface](#10-the-user-interface)
11. [The Hermes environment (setup/)](#11-the-hermes-environment-setup)
12. [Installation and operations](#12-installation-and-operations)
13. [Added value, strengths, and weaknesses — the honest assessment](#13-added-value-strengths-and-weaknesses--the-honest-assessment)
14. [Open work](#14-open-work)
15. [Repository map and document index](#15-repository-map-and-document-index)

---

## 1. What this is

A **self-hosted AI-agent operating system** for a small (two-person) business.
The operator describes work in natural language; the system plans it, executes
it with specialized AI agents, quality-gates the results, and delivers files,
documents, and code. Everything runs on the operator's machine; the only
external calls are to the LLM providers — Z.AI GLM for execution, Anthropic
Claude (Opus) for the judgment tier (judge / spec critique / escalation).

Two cooperating systems, deliberately separate processes:

| System | Role | Tech | Port |
|---|---|---|---|
| **Nexus Agent OS** (`app/`) | Control plane: UI, kanban, dispatch queue, planning, budgets, quality loops, judge, memory, voice | FastAPI + SQLite + vanilla JS (no build step) | 8777 (HTTPS) |
| **Hermes Agent** (`setup/`) | Execution engine: sessions, tools (terminal/files/browser/LSP), 18 specialists, skills, mem0 memory | Python agent runtime + gateway, pinned v0.18.0 @ `048270fa` | 8642 |

Supporting services: **qdrant** (vector store, Docker, server mode),
**ollama** (embeddings, mem0 extraction, local VLM, dictation cleanup),
**hermes-guardian** (integrity: verifies/repairs every customization by
SHA-256 manifest + git patches), optional **Langfuse** (LLM observability).

### The added-value proposition

What this buys over a chat window or a single CLI agent:

- **Autonomy at scale.** Queue many tasks; agent lanes execute them
  unattended (including overnight), with budgets, per-model concurrency
  caps, self-healing, and automatic recovery from crashes, restarts, and
  provider quota storms.
- **Process and auditability.** Every pipeline leaves a trail: SPEC,
  per-stage DECISIONS.md, versioned deliverables, round-over-round diffs,
  judge verdicts with findings. Nothing ships without an inspectable record
  of *why*.
- **Independent quality gates.** A deterministic pre-gate, a GLM screening
  judge, a frontier (Opus) judge graded against domain rubrics, and an
  optional sandboxed grounded critic (Super Result) that re-verifies claims
  against the real files.
- **Learning loops.** Specialist lessons, a WINS/LESSONS ledger injected
  into future work, an eval corpus with an improvement loop, and routing
  telemetry that tunes model selection.
- **Privacy and cost model.** Local-first: data, memory, voice, and vision
  stay on the machine. Execution runs on a flat-rate GLM subscription;
  frontier calls are metered and capped per task.
- **One workspace.** Kanban, agent fleet, deliverables with in-place app
  preview, memory browser, meetings, notes, and a voice assistant in a
  single dashboard.

Section 13 tests this proposition against measured benchmark data — including
where it currently falls short.

---

## 2. Architecture

```
┌─────────────────────────────  YOUR MACHINE  ─────────────────────────────┐
│                                                                          │
│  Browser ── HTTPS ──▶ NEXUS server.py (FastAPI, 8777, 248 API routes)    │
│                         │   ├── nexus.db (SQLite WAL, 32 tables: tasks,  │
│                         │   │   agents, workflows, dispatches, settings, │
│                         │   │   users, frontier_ledger, plan_sessions …) │
│                         │   ├── workspaces/<task-id>/ (deliverables,     │
│                         │   │   _history/vN, _judge/round-N.json)        │
│                         │   └── background threads: loop engine (20s),   │
│                         │       watchdog (10s), scheduler, metrics       │
│                         │                                                │
│      agent lanes: worker.py subprocesses (one per agent row)             │
│                         │  claims ONE task (SQLite CAS) → dispatch       │
│                         ▼                                                │
│  hermes_dispatch.py ── HTTP+SSE ──▶ HERMES gateway (8642)                │
│      create session → stream turn → harvest results                     │
│                         │                                                │
│                         ├──▶ Z.AI GLM-5.2/5.1/4.5-air/5-turbo (exec)    │
│                         ├──▶ claude CLI: cjudge/cverify/cexec (judgment) │
│                         ├──▶ tools: terminal, files, browser (playwright │
│                         │    MCP), serena (LSP), context7 (docs)         │
│                         ├──▶ mem0 ──▶ ollama (embed) + qdrant (vectors)  │
│                         └──▶ specialists (~/.hermes/agents/*.md)         │
│                                                                          │
│  hermes-guardian (systemd timer): manifest-verify + core-mod repair      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Design principles (each one is enforced, not aspirational)

1. **Control/execution split.** Nexus restarts never kill running AI work.
   A Hermes session survives its client; a respawned lane *harvests* the
   orphaned-but-finished run from session history — verified repeatedly in
   production, zero token waste.
2. **SQLite is the single source of truth.** One WAL database
   (`nexus.db`) holds tasks, queue, budgets, verdicts, users, ledgers.
   Task claiming is an atomic compare-and-swap — double-claims are
   impossible. Hermes's own kanban.db is retired; never bridged.
3. **Everything is user-scoped.** An ASGI middleware resolves the request
   user once into a contextvar; internal automation (loop engine, workers)
   calls back through the server's own HTTP API with an internal token +
   `x-nexus-user` header, so no code path is unscoped (§8).
4. **Deterministic cores, LLM edges.** The decision logic of planning
   (`plan_engine`), presets (`autopilot`), routing (`routing`), and quality
   loops (`loop_engine`) is deterministic and unit-testable; LLM calls sit
   at the edges (interview turns, verdicts, drafts).
5. **Cheap → expensive cascade.** Quality checks escalate in cost order:
   free deterministic pre-gate → one-turn GLM screen → frontier judge →
   frontier escalation rework — each tier bounded by rounds, convergence
   detection, and per-task dollar caps.
6. **Localhost + HTTPS + manual-start.** Everything binds to loopback;
   remote access is Tailscale-only. Nothing autostarts at boot; `nexus-up`
   starts the stack deliberately.
7. **Guardian-pinned customizations.** Every Hermes modification ships as
   one of 8 tracked core-mod patches or golden files; drift is detected
   and repaired, so `hermes update` is survivable.
8. **No-build frontend.** Vanilla JS/HTML/CSS; three.js is lazy-imported
   inside the 3D modules only; all interpolation escaped; live updates
   patch the DOM in place.

### Backend inventory (app/, ~29k lines of Python)

| Module | Lines | Purpose |
|---|---|---|
| `server.py` | 11,476 | FastAPI monolith: 248 REST routes + 2 WebSockets, static SPA, JARVIS SSE chat, hosts the background engines |
| `hermes_dispatch.py` | 2,136 | Real-execution engine: task → Hermes session → deliverable; framing, budgets, quota, resume/harvest |
| `evals.py` | 1,922 | Eval corpus + all frontier CLI plumbing (judge/critic/premortem/escalation), pre-gate, cost recording |
| `loop_engine.py` | 1,349 | Autonomous quality-loop driver (20s sweep): judge loop, Super Result, escalation, replan detection |
| `database.py` | 1,130 | SQLite layer: 32 tables, migrations, CAS claim, model registry, cost ledgers |
| `dictation*.py` | 1,936 | System-wide voice typing + dual-channel MeetingMode |
| `settings_registry.py` | 806 | Declarative settings registry: 13 sections, ~133 keys, schema-driven Settings UI |
| `plan_engine.py` | 691 | Deep Plan mode deterministic core (triage, interview scaffolds, spec merge, divergence) |
| `tools_hub.py` | 711 | Live tool/skill/project/usage scanners |
| `app_runner.py` / `project_preview.py` | 825 | Run generated apps locally; materialize whole-project previews with time-travel |
| `voice.py` / `stt_worker.py` / `lipsync.py` | 972 | Piper TTS, the machine's ONE faster-whisper worker, Wav2Lip |
| `vision.py` / `vision_worker.py` | 588 | SigLIP+OCR visual memory, qwen3-vl describe, SDXL-Turbo generation |
| `review.py` | 402 | PR-style review builder for every output type (diffs, highlights, comment anchors) |
| `lessons.py` / `feedback_log.py` | 704 | Lesson distillation to the knowledge base; WINS/LESSONS ledger |
| `routing.py` | 354 | Deterministic model routing + telemetry + learned params |
| `worker.py` | 306 | One lane subprocess per agent; claim → dispatch → finalize loop |
| `auth.py` | 293 | Multi-user auth, cookie sessions, scrypt, internal token |
| `agent_manager.py` / `watchdog.py` / `scheduler.py` | 757 | Lane lifecycle, self-healing, cron jobs with task templates |
| `agent_memory.py` / `onboarding.py` / `secrets_store.py` / `worktree.py` / `jarvis_brain.py` / `autopilot.py` / `gpu_lock.py` | ~1,500 | Agent memory scopes, business-brain onboarding, encrypted credentials, git worktrees, JARVIS domain packs, autopilot presets, GPU arbitration |

---

## 3. The task execution pipeline

### 3.1 Two orthogonal state machines

**Kanban status** (what the operator sees):
`backlog → todo → in_progress → review | done → archived`.
High-stakes tasks finish into `review` (an approval card); everything else
goes straight to `done`.

**dispatch_state** (what the machinery does), mirrored on the `dispatches`
table:

```
none → queued → dispatching → streaming → finalizing → completed
                                  │
                                  ├─▶ failed          (terminal: error, runaway)
                                  ├─▶ blocked_quota   (provider backoff; auto-clears)
                                  ├─▶ blocked_budget  (token caps; operator raises)
                                  └─▶ cancelled       (operator ⏹ stop)
```

### 3.2 Agent lanes (worker.py)

One OS subprocess per agent row. Every 2 seconds a lane walks a strict
priority ladder: (1) resume/harvest its own interrupted dispatch,
(2) run its queued tasks, (3) retry blocked tasks whose budget/quota
cleared, (4) claim new `todo` work whose dependencies are satisfied.
Claiming is a single atomic SQLite compare-and-swap. A per-model slot gate
(`_slot_ok`) enforces concurrency caps per model. When dispatch is disabled
(drain posture before a restart), lanes only heartbeat and harvest — they
start nothing new. Lanes exit cleanly when their agent row is retired,
pause when the watchdog cost-caps them, and demote SIGTERM to a clean exit.

### 3.3 A dispatch, end to end

Each task runs as **one fresh Hermes session** (`nexus:<task-id>`) with an
ephemeral system framing assembled by `build_framing`:

- workspace path and the deliverable contract;
- attachments (marked MUST-READ) and dependency deliverables as inputs;
- the specialist's domain playbook pointer + golden exemplars;
- a recent WINS/LESSONS excerpt for the domain (the learning loop, §7);
- repo-mode contract and code-map when the task targets a repository (§6);
- agent memory (long-term rules + rolling summary) for the executing lane.

Model resolution happens at dispatch: `resolve_task_model` applies the
task's routed model (§4.4), and a session-keys bridge
(`~/.hermes/session-keys.json`) carries the per-task **reasoning effort**
(smart/high-stakes → xhigh; eco → medium; Balanced content → high) into the
Hermes zai plugin. Per-session models only work because of guardian
core-mod #6 (`session-model-api-server`) — upstream Hermes ignores them.

Token usage is real: it comes from the SSE `run.completed` event, and
budgets count input+output per turn (agentic sessions resend context per
tool call). Per-deliverable-type caps bound both turn seconds and default
budgets (eco/Balanced/smart content = 1M/2M/4M tokens baseline × the
autopilot multiplier). On finalize: deliverable written, tokens booked,
`status = review` (high-stakes) or `done`, retry feedback cleared.

### 3.4 Stopping, self-healing, and resilience

- **Stop** (⏹): sets `cancel_requested`; the dispatch loop raises
  `DispatchCancelled` → `_finalize_cancel` (back to backlog,
  `dispatch_state='cancelled'`). Core-mod #8 makes Hermes
  `POST /v1/runs/{id}/stop` actually abort session-chat runs (live-verified
  3.9s abort). The flag deliberately stays set until an explicit re-dispatch
  (race guard against a lane mid-claim).
- **Watchdog** (10s): restarts dead lanes (PID gone), detects stale
  heartbeats, recycles lanes at `max_tasks`, enforces per-agent token caps
  (`cost_capped`), and drives dispatch reconciliation.
- **Orphan harvest ladder**: lane death ≠ run death. On resume, the lane
  classifies the orphan run — *active* (wait + refresh heartbeat),
  *finished* (harvest the result from session history), *dead* (supersede
  with a continue-turn). Runaway is declared only at 2× the turn cap, and a
  cut is non-terminal: cut → wait → harvest.
- **Quota storms** (Z.AI 429 / error 1305 — probabilistic load-shedding,
  not quota): retry ONCE on the registry fallback model, then
  `blocked_quota` with exponential backoff and once-per-storm logging.
  The frontier tier has its own quota backoff and never counts an
  interrupted judge run as a round.
- **Stranded claims**: self-resurrected by the owning worker (dependency-
  gated), reassigned on operator dispatch, >1h backstop release.

---

## 4. The planning layer

Four cooperating pieces decide *what* runs, *how thoroughly*, and *on which
model* — all before a single execution token is spent.

### 4.1 Wizard v3 ("✨ Describe a task / goal")

Two-phase natural-language planning. Triage may ask ONE round of up to six
clarifying questions, each with pros/cons per option, a ★ recommended pick,
and a default. The proposal is an editable task or a full pipeline. Coding
goals get the enforced house pipeline **spec → implement → review → fix →
verify**; `_repair_workflow()` deterministically re-inserts missing gates,
whitelists specialists, restores the implement→spec dependency, and keeps
the DAG acyclic. The proposal card carries the two **autopilot** questions
("how much should I ask you?" / "how much should this cost?") and a
🧭 recommended spend profile (`plan_engine.recommend_spend`: mechanical →
eco; complexity ≥6 or blast radius → smart; else Balanced). The wizard only
auto-assigns a repository to dev-shaped tasks (a content deck once became
invisible because it landed on a branch).

### 4.2 Deep Plan mode (✦)

Conversational planning for larger goals — `plan_engine.py` + the
`/api/plan/sessions` surface, sessions persisted in `plan_sessions`.

Flow: **triage** (heuristics + family detection: `software`,
`analysis-audit`, `content`, `research`) → soft-gated offer → **scaffolded
interview** (per-family SPEC template; answers merge into the spec until
required slots fill) → **draft** (task DAG from the spec, acceptance
criteria distributed per stage with a coverage guarantee) → **premortem
critique** (structural checks + an external `spec_model` pass) →
**revise loop** (one automatic round via `plan.auto_revise`; operator
questions land in a universal notes slot; 🔧 manual rounds; 600s cap).
Sessions can attach a `repo_path`, so interview/draft/revise see the
existing project state — plans describe *changes*, not greenfield. The
whole wizard/draft/revise framing is tools-off (⛔) — planning never
executes anything. The finished SPEC travels downstream: it rides into
dispatch framing and (round 1 only) into the judge's context.

### 4.3 Quality Autopilot — two knobs instead of twenty

`autopilot.py` derives every quality/cost knob from two orthogonal axes,
set per task/workflow (defaults: assisted + Balanced):

| Axis | Values | Drives |
|---|---|---|
| **Involvement** | `full_auto` / `assisted` / `manual` | checkpoint style, auto-approve-on-SHIP (full_auto only, after a configurable delay), decision-card behavior |
| **Spend** | `eco` / `optimal` (Balanced) / `smart` | judge tier & scope, Super Result on/off, round caps (1/2–3/3), budget multiplier (0.5×/1×/2×), pipeline depth, escalation mode (off / rewrite / rewrite_or_cap), model floor |

A hard **risk floor** overrides the profile: high-stakes work always gets
the frontier judge and full pipeline depth, whatever the spend setting.

### 4.4 Model auto-routing

The model registry (Settings → seeded with glm-5.2 / glm-5.1 / glm-4.5-air
/ glm-5-turbo / claude-opus-4-8) maps six **purposes**:

| Purpose | Seeded model | Used for |
|---|---|---|
| `complicated` | glm-5.2 | default; hard thinking; ALL dev-pipeline stages (hard floor) |
| `easy` | glm-5.1 | light/simple tasks |
| `mechanical` | glm-4.5-air | formatting, extraction, conversion |
| `frontier_judge` | claude-opus-4-8 (CLI) | deliverable verdicts |
| `spec_model` | claude-opus-4-8 (CLI) | Deep-Plan premortem critique |
| `escalation_model` | claude-opus-4-8 (CLI) | Super-Result escalated rework |

`routing.select_model_for_task` runs deterministically at task creation
(gated by `models.auto_route`, default ON): keyword heuristics pick the
base purpose; each enabled model's "Best for:" phrases can upgrade it and
"Avoid for:" phrases veto; eco floors to the light tier; high-stakes/smart
never route below `complicated`. The plain-language rationale is stored in
`tasks.model_reason`. Telemetry (`routing_outcomes`) is recorded at every
terminal state; every ~100 tasks a no-LLM sweep proposes threshold tweaks
as an admin decision card and watches for router collapse. A cascade
escalation exists for the light tier: a light-tier attempt whose judge says
REVISE retries once on `complicated` (never for high-stakes/dev).
`glm-5-turbo` is the peak-hours fallback via the registry's
`FALLBACK_MODELS` safety net — rotation edits the registry, never the code.

---

## 5. The quality machinery

This is the system's central bet: that layered, mostly-deterministic
verification can push cheap-model output toward shippable quality. (§13
reports how that bet is doing.)

### 5.1 The judge loop (overhauled 2026-07-13 — `app/docs/SPEC-JUDGE-LOOP.md` is binding)

Every finished quality deliverable enters a cheap→expensive cascade,
driven by the loop engine's 20-second sweep (≤3 actions per sweep):

```
[0] closed-family check      already operator-closed? → skip forever until reject
[1] hard caps                judge_round ≥ judge.max_runs (4) | frontier $ cap → close
[2] tier resolution          high_stakes/smart → frontier · eco → none ·
                             Balanced → frontier for SINKS, GLM screen for interior
[3] deterministic pre-gate   FREE checks: stub/short deliverable, <2 headings,
                             TBD/TODO, empty repo diff → free retry with fix list
[4] verdict run              frontier: cjudge (Opus, domain rubric)
                             screen:   one GLM turn, same verdict contract
[5] on REVISE/REWRITE        retry: round 1 CONTINUES the original session
                             (targeted revision + mandatory "## Fixes applied");
                             round ≥2 runs fresh
[6] delta re-judge           round ≥2 judges get prior fix-list + version diff,
                             criteria FROZEN at round 1, only changed regions scanned
[7] closure                  convergence (finding keys ⊆ previous) | round cap |
                             max_runs | $ cap | error → ONE decision card
```

Key semantics:

- **Verdicts: `SHIP` / `REVISE` / `REWRITE`** — with **SHIP-with-notes**:
  only *blockers* block (an in-scope must-pass gate at FAIL, or a
  critical/high finding — unmarked-false claim, contradiction with the
  stage contract/SPEC, unmet binding "Done when:"). Polish, style, and
  extra-depth wishes are notes, never blockers. The revision brief is a
  numbered `[F1]..[Fn]` fix-list of blockers only.
- **Stage contracts.** Pipeline stages are judged against *their own*
  "Done when:" lines (`JUDGE_TASK`), not the whole-project SPEC — gate
  states include `N-A (owned by a later stage)` and `UNVERIFIABLE-HERE`.
  Artifacts are copied (size-capped) so file claims are verifiable. (Both
  were hard-won fixes: an earlier judge refuted every file claim it
  couldn't see and enforced project criteria against a spec-only stage,
  producing an unwinnable REVISE loop.)
- **The GLM screen** (Balanced interior stages) inlines the same verdict
  contract into one cheap GLM turn; a screen REVISE without any
  critical/high finding stores as SHIP, unparseable output stores as SHIP —
  a screen must never block on its own failure. Screen SHIPs never count as
  frontier SHIPs (no auto-approve, no golden exemplars).
- **Bounds.** `judge.max_runs` (default 4) counts stored verdicts per
  version family; convergence closes when a round's finding keys are a
  subset of the previous round's; `frontier.task_cost_cap_usd` (default $3,
  × 0.5/1/2 by spend profile) caps judge dollars per task.
- **Closure.** Every exhausted path files exactly ONE `deliverable`
  decision card. Approve = accept-with-notes and closes the family forever;
  reject (with feedback) re-arms the loop as a new version family
  (judge_round and keys reset). Screened interior members close silently
  as notes. The manual "Judge" button bypasses caps and pre-gate — operator
  intent wins.
- **Findings are first-class.** Judge findings land as anchored review
  comments (`source='judge'`, validated ±2 lines against workspace and
  worktree); open comments are drained into the next retry as `[F#]`
  feedback and marked consumed.

### 5.2 Super Result — the grounded critic (optional, per task)

When `super_result` is on, the judge cascade is REPLACED by a sandboxed
critic loop (the two never stack): the deliverable is copied into a
disposable sandbox where a critic with full tool access **re-verifies every
claim against the real files**, then verdicts SHIP/REVISE/REWRITE with the
same key-based convergence. SHIP quiet-stops (no residual polish round).
Closed mode auto-retries with the revision brief; contradictions
(empty-findings REVISE), convergence, or the round cap raise a human
checkpoint. In assisted mode the loop runs closed with terminal checkpoints
only.

**Escalation ladder** (armed 2026-07-13): on REWRITE — or round-cap with
open critical/high findings — the frontier `escalation_model` rewrites the
final version in the real workspace, budgeted by `super.escalation_max`
(default 1 paid run). Tri-state dispatch (sent / wait-on-quota / no); a
SHA-256 pre/post hash guard reverts on failure or a byte-identical result
so an escalation can never fake a SHIP.

### 5.3 Honest cost accounting

Every frontier subprocess run (judge, screen, spec, critic, escalation)
books one `frontier_ledger` row — real dollars from the `claude -p` JSON
envelope when available, transcript estimate otherwise. GLM usage is priced
via `effective_task_model` + blended rates. `task_cost_ledger` /
`workflow_cost_ledger` combine both currencies into an **API-equivalent
USD** figure — explicitly a comparison figure, not a bill (execution runs
on subscription).

### 5.4 Loops v3.2, replanning, and the app's own gates

- **Improvement loops** (`loop_engine.design_loop`): deterministic
  designer; triggers `verify_fail` (verify-FAIL → retry with findings →
  re-verify), `judge_revise`, `super_result`. Closed or open mode, bounded
  per-trigger round caps; projects inherit loops to member tasks with
  per-task counters.
- **Replan detection** (Block 3): stage failures in a workflow raise a
  replan draft (detection-only by default; `replan.auto_draft` optional) —
  the operator applies or dismisses.
- **The app's own verification**: `scripts/verify.sh` — **488 static
  checks**, self-counting, pre-commit enforced — plus ~20 runtime gates
  (Playwright UI suites, real-dispatch e2e, judge-loop e2e, multiuser e2e,
  mode-coherence, stop, autopilot, deep-plan, settings, JARVIS/STT…), all
  listed in `app/CLAUDE.md`.

---

## 6. Repo-native coding

Tasks with a `repo_path` run INSIDE an existing repository instead of
scaffolding a fresh workspace project:

- **Idempotent git worktree per pipeline**, branch `nexus/<slug>` under
  `<repo>/.worktrees/` (self-ignoring). Pipeline stages share one branch so
  implement → review → fix → verify build on each other; parallel pipelines
  get isolated worktrees; the operator's checkout is never touched.
- **Repo-mode framing**: follow repo conventions (AGENTS.md/CLAUDE.md
  excerpt injected directly — no Hermes core-mod needed), a code-map of the
  repository, run the repo's own gates, commit on the branch, never
  push/merge.
- **The diff is the deliverable.** After each turn: snapshot-commit of
  uncommitted work (junk-excluded), then `changes.diff` (three-dot vs base)
  captured into the workspace. Artifacts committed on the branch are also
  copied back (`_copy_branch_artifacts`) so non-code deliverables (e.g. a
  .pptx) surface in the UI. Humans merge; PR creation is available for repo
  tasks (Block 2).
- **Review v2** renders every output type as a PR: per-file unified diffs
  with server-side Pygments highlighting, per-line comments that anchor to
  old/new positions, PDFs diffed by extracted text, images side-by-side.
  Repo tasks default to **round-over-round diffs** once a judge/critic
  rework happened (`rounds.json`), with `deliverable.md` riding alongside
  so judge findings anchor. Open comments feed the next retry.
- **Dev specialists** (tech-lead-orchestrator, code-implementer,
  code-reviewer, debugger, acceptance-verifier) carry `mcp-serena` (LSP
  symbol navigation — deterministic retrieval instead of embedding client
  repos) + `mcp-context7` (live library docs) + Big-Code rules:
  blast-radius first; done = repo gates green AND every touched symbol's
  usages re-searched; schema changes always escalate to the human. They are
  pinned to glm-5.2 — routing never downgrades them.
- **Test the result**: `app_runner.py` launches generated apps/websites
  locally (disposable venvs, port remapping, 30-minute auto-stop);
  `project_preview.py` materializes a whole assembled workflow result —
  including **time-travel** (before-vs-current) from branch commits or
  `_history` versions — without ever mutating the live worktree.

---

## 7. Memory and learning

Five distinct memory systems, each with a specific writer and consumer:

1. **mem0 semantic memory** (Hermes side, via core-mods #1–4): two-scope
   (user + agent) with per-specialist `mem0_agent_id`. Specialists recall
   their private lessons layered read-only on the shared base. Storage:
   qdrant collection `mem0` — dense 768-dim (nomic-embed-text) + BM25
   sparse vectors, payload with attribution/channel/timestamps.
2. **Specialist lessons**: the `hermes-reflect` timer (every 30 min) turns
   operator feedback into candidate lessons queued for human approval;
   approved lessons bind to the specialist; `hermes-prune` (weekly)
   soft-archives stale ones.
3. **Agent (lane) memory** (`agent_memory.py`): four scopes — `stm`
   scratchpad (48h TTL), `experience` (one line per dispatch, 90d),
   `lts` (hourly rolling summary, one cheap-model call per lane),
   `longterm` (operator-taught standing rules, never expire, always
   injected into that lane's framing).
4. **WINS / LESSONS ledger** (`feedback_log.py`): per-user Business-Brain
   feedback files; entries are AI-drafted from real outcomes (never
   numbers invented), a LESSON requires a correction; recent domain-
   matching entries ride into every dispatch framing; wins can be promoted
   to golden exemplars. Cross-user adopt copies with origin-key dedupe.
5. **Knowledge-base distillation** (`lessons.py`): deterministic evidence
   collection from operator edits/comments/accepted diffs → one
   judgment-tier call proposes durable deltas to the domain
   STYLE-VOICE/PLAYBOOK/RUBRIC → filed as an **admin approval**; on
   approve, applied to `~/knowledge` and git-committed. Proposal is
   autonomous; writing is always gated.

On top: the **eval corpus** (Block 3) runs fixed per-domain briefs through
the real dispatch framing, scores them with the frontier judge against the
domain rubric, and the `cimprove` loop turns low-scoring cases into
proposed improvements (same approval path). Evals are deliberately
agent-less and auto-route-less — config-pure measurement.

**The memory galaxy** (`/api/memory3d`): all mem0 vectors, PCA (numpy SVD)
to 3 axes, top-3 cosine links ≥0.45, k-means clusters labeled with
tf-idf-style distinctive terms. The frontend renders a navigable star
field with signal pulses, search dimming, hover reading, and click-to-edit
(edit/merge/delete are confirm-gated) — it doubles as the dashboard
centerpiece and sits behind the JARVIS avatar (camera fly-through).

---

## 8. Multi-user and security

**Multi-tenancy (Block 1).** Every row and query is user-scoped; a seeded
`u_owner` owns all pre-multiuser data, so no unscoped code path exists.
With 0–1 users there is NO login — the single-operator machine behaves as
before. Adding user #2 turns the login screen on for everyone; each user
gets their own board, workflows/projects, deliverables, known issues,
notes, focus context, JARVIS conversation, and mem0 scope (session
user-tagging via `~/.hermes/client-scopes.json`; reads post-filter). Shared
by design: the agent fleet, scheduler, approvals, watchdog, settings
(admin-write), specialists/lessons/skills, shared context.

**Auth mechanics** (`auth.py`): scrypt passwords (n=16384, r=8, p=1,
constant-time verify), 256-bit tokens in HttpOnly + SameSite=Lax cookies
(DB stores only the SHA-256), 30-day sliding expiry, 5-failures/15-min
login throttle, admin/member roles. WebSocket handshakes authenticate the
cookie; events broadcast only to the owner's sockets. In-process engines
authenticate with a per-boot internal token. Emergency:
`scripts/auth_reset.py` returns the box to single-user.
Proof: `scripts/verify_multiuser_e2e.py` — 55 checks probing HTTP/WS/
JARVIS/mem0 isolation against the live server.

**Security posture:**

- HTTPS-only UI (self-signed cert; mic requires HTTPS off-localhost);
  loopback binding everywhere; remote access **Tailscale-only** via
  `tailscale serve` — never port-forwarded (`app/docs/TAILSCALE.md`).
- **Encrypted credential store** (`secrets_store.py`): Fernet with a
  machine-local 0600 `secret.key`; the API only ever returns metadata + a
  4-character hint; plaintext resolves exclusively on execution paths.
  Machine secrets live in `~/.hermes/.env` (never in git; template +
  credential scanner ship in the repo).
- **No command-allowlist auto-approval** (guardian enforces its ABSENCE);
  approval gates for sensitive actions; tirith pre-exec security hook
  fail-closed; secret redaction on.
- **Guardian** pins every customization (8 core-mods, plugins, goldens,
  config values, pinned package versions) by SHA-256; drift is flagged and
  repaired.
- XSS discipline: all interpolation through `esc()`; the single deliberate
  raw-HTML channel (Pygments-highlighted diffs) is server-generated.

---

## 9. JARVIS: voice, vision, dictation

**Voice turn**: browser mic → `/api/jarvis/stt` (the machine's ONE
faster-whisper large-v3, CUDA with CPU self-heal, killable worker
subprocess) → `/chat/stream` (SSE proxy to Hermes) → sentence-split →
`/api/jarvis/talk` per sentence (Piper TTS on CPU — zero VRAM — plus
Wav2Lip lip-synced MP4) → muted face `<video>` + persistent `<audio>`,
2-deep prefetch. Barge-in, silence-VAD conversation mode (CONV toggle),
JSON errors on all endpoints, 120s render timeout, idle unload.

**The brain** (`jarvis_brain.py`): every turn folds a compact excerpt of
the `~/knowledge` business brain into the framing — domain detection across
nine business domains, rubric gate titles + playbook headers (voice-compact,
not full documents), business facts, and an always-on AI-slop kill list.

**The avatar** (`jarvis3d.js`, 1,545 lines): holographic cyan point-lattice
head (three.js facecap GLB, 52 ARKit blendshapes) with bloom, research-
grounded blink, text-aligned visemes gated by live RMS, saccade gaze, idle
breathing; behind it the real memory galaxy (camera fly-through to orbit,
hover, click-to-edit). Reacts to real mic/speech amplitude via WebAudio
analysers. Falls back to an ellipsoid bust without the GLB.

**Vision** (`vision.py` + worker in `~/ml-env`): visual memory — SigLIP
(so400m-384) + RapidOCR into qdrant `jarvis_vision`, natural-language
recall with OCR keyword boost; understanding via ollama `qwen3-vl:8b`;
image creation via SDXL-Turbo. Worker processes are killed after idle —
**process exit is the VRAM guarantee** on the shared 12 GB card, with
`gpu_lock.py` (fcntl flock) serializing heavy loads across unrelated
processes (degrade-never-deadlock: on timeout it runs unserialized).

**Dictation** (absorbed from WisprFlow): system-wide voice typing —
hotkey → shared STT → LLM cleanup (isolated ollama `gemma3:4b` on :11435)
→ layout-aware typing, DPI-aware overlays. **MeetingMode** records
dual-channel (🎤 me / 🔊 client) transcripts that land in the Meetings view,
where a transcript assigned to a project unlocks summary / requirements /
memory / plan-work actions.

---

## 10. The user interface

Vanilla JS single-page app (`app.js`, ~11,700 lines), 24 views in four
sidebar groups plus pinned J.A.R.V.I.S:

| Group | Views |
|---|---|
| **Command** | Dashboard (galaxy hero, now-running ticker, stats, model traffic lights) · Projects (client/personal repos, remote-backup state, Publish→Push→Tag) · Workflows (pipeline diagrams + loop badges) · Tasks (the kanban; wizard entry; focus scoping) · Deliverables (preview/download; ▶ Test app) · Meetings · Agent Fleet (lane cards + drawer) · Decisions (all pending human calls as answerable cards) · Agentic Capabilities (approvals, verification, scheduler, guardrails) |
| **Intelligence** | Specialist Agents (Team + Evals tabs) · Memory Hub (3D map, mem0, agent memory, lessons, Wins & Lessons, shared context) · Skills |
| **System** | System Monitor · Tools Hub · Programs · Guardian (drift status, core-mods) |
| **Insights** | Usage & Cost (per-model tokens/$, 14-day trend) · LLM Observability (Langfuse) · Known Issues (🐞 reports with attached context) · Notes · Settings (registry-driven) · User Manual |

Cross-cutting: one `/ws` socket drives live updates (badges, toasts,
per-slice refetch + soft render); renders defer while a modal/input is
focused; context-aware **tours** (`?` in the topbar) spotlight every view;
decision cards, the findings panel, and the review modal carry the quality
loop into the UI; floating utilities — 🐞 file-a-known-issue with attached
interaction journal, 📝 quick notes, ⏻ restart-prep (drains agents).

Conventions (gate-enforced): no build step; `esc()` on all server data;
`?v=N` cache-busting; in-place DOM patching on tick; the string "three"
never appears in `index.html` (3D modules lazy-import three.js).

---

## 11. The Hermes environment (setup/)

Everything needed to reproduce the execution engine on a fresh machine.
Hermes itself is pinned (v0.18.0 @ `048270fa069f`) so core-mods apply
cleanly.

### 11.1 Specialists (18 active)

Dev pipeline: **tech-lead-orchestrator** (read-only exploration → PLAN/SPEC
with ordered tasks), **code-implementer**, **code-reviewer**, **debugger**,
**acceptance-verifier** (fresh-context final gate). Business/creative:
**brand-strategist**, **content-strategist**, **copywriter-specialist**,
**long-form-writer**, **social-content-creator**, **seo-strategist**,
**market-researcher**, **web-researcher**, **strategy-consultant**,
**ecommerce-merchandiser**, **marketplace-listing-optimizer**,
**music-producer**, **dj-set-curator**. Each carries a mandatory knowledge
protocol (read the domain PLAYBOOK/RUBRIC first) and a private
`mem0_agent_id`. 28 retired specialists are archived; the repo installer
additionally ships the 5 dev specialists in their LSP/Big-Code edition.

### 11.2 Skills (~80), plugins (6), core-mods (8)

- **Skills** (`setup/hermes/skills/`): quality gates (client-delivery-gate,
  frontier-judge, win-lesson-logging, goal-drift-discipline,
  project-ledger), agent delegation (claude-code, codex, opencode,
  hermes-api-server), 18 creative (diagrams, infographics, design systems,
  manim, p5js, ComfyUI…), 6 media, 9 MLOps (vllm, llama-cpp, HF hub…),
  11 productivity (powerpoint, google-workspace, notion, meeting-capture…),
  8 research (deep-research, claim-verification, arxiv…), 18 software-
  development (agentic-coding-harness, systematic-debugging, TDD,
  runtime-verification…). Three are guardian-enforced OFF.
- **Plugins**: specialist_router (keyword-gated forced delegation),
  brave_context (full-page web search), local_reader (keyless extraction),
  wayland_portal (computer-use on GNOME Wayland), mem0-client (user/client
  isolation provider), zai (GLM provider override).
- **Core-mods** — the 8 guardian-tracked patches to Hermes core:

| # | Mod | What it fixes/adds |
|---|---|---|
| 1 | mem0-per-agent-scoping | per-call agent_id, two-scope recall |
| 2–3 | specialist-mem gate (agent_init / run_agent) | scoped specialist memory, read-only recall |
| 4 | specialist-binding-delegate | playbook + memory + tool allowlist binding on delegation |
| 5 | langfuse-observability-fixes | GLM/DeepSeek reasoning capture |
| 6 | **session-model-api-server** | per-session/per-turn model honored — the keystone of all model routing |
| 7 | zai-prompt-fingerprint | rewords a system-prompt phrase Z.AI 429-blocks |
| 8 | session-run-stop | makes `/v1/runs/{id}/stop` real → the ⏹ button works |

**Guardian** is two-layer: `manifest.json` (config values, golden files,
pinned packages, services, containers — verify/restore) +
`core-mods.json` (git patches). Passive by default; auto-restores when a
Hermes update moves git HEAD.

### 11.3 Frontier bridge CLI and infrastructure

`setup/bin/` → `~/.local/bin`: **cjudge** (rubric judge), **creview**
(adversarial review vs SPEC), **cspec** (spec interview), **cverify**
(grounded critic sandbox), **cexec** (escalated rework), **cimprove**
(eval-driven improvement), **cdistill** (lesson distillation),
**nexus-up** (start the whole stack). All drive the logged-in `claude` CLI
— this is how Opus participates without an API key.

Infra: qdrant v1.18.2 in Docker **server mode** (gateway + Nexus read
concurrently), loopback-bound, `restart:"no"`; ollama in three roles
(mem0 models, vision VLM, isolated dictation-cleanup instance on :11435);
optional Langfuse. The **knowledge base** (`setup/knowledge/` →
`~/knowledge`) is the Business Brain: BUSINESS-CONTEXT, STYLE-VOICE, 10
domain PLAYBOOK+RUBRIC pairs, feedback ledgers, eval cases — installed
additively, never clobbered.

---

## 12. Installation and operations

**Full machine** (`setup/CLAUDE.md`, autonomous runbook): 0 preflight
(git/curl/docker/ollama) → 1 Hermes pinned install → 2 ollama models
(llama3.1:8b, nomic-embed-text) → 3 qdrant via compose → 4
`bash setup/install.sh` (configs, agents, skills, plugins, guardian,
Nexus from this repo's `app/`, systemd units, bridge CLIs, knowledge base)
→ **5 API keys — the ONLY manual stop** (`~/.hermes/.env` from
`setup/.env.example`; `GLM_API_KEY` required) → 6 Nexus venv → 7 start
services → 8 verify (guardian `overall=OK`, 8 core-mods). Optional 7b:
dictation packages. **Nexus-only** (Hermes already present): repo-root
`bash install.sh` (rsync `app/`, venv, Playwright, self-signed TLS cert,
dev specialists, disabled systemd units, `nexus-up` + desktop launcher;
refuses to overwrite an existing nexus.db).

Operational rules that matter:

- **Manual-start posture by design**: nothing autostarts at boot; start
  with `nexus-up` or the "Start Nexus" desktop icon. Don't "fix" this by
  re-enabling units.
- **Restart discipline**: `systemctl --user restart nexus` is THE way;
  check nothing is queued/dispatching/streaming/finalizing first (harvest
  recovers interruptions, but don't provoke them). The topbar ⏻ drains
  lanes; startup restores dispatch.
- **The live-tree symlink is LOAD-BEARING**: `~/nexus-agent-os` points into
  this repo's `app/`; the systemd unit, DB workspace paths, and venv
  shebangs resolve through it. Run the service from `main`; experiment in
  git worktrees.
- **Settings** (registry-driven, 13 sections / ~133 keys): budgets (default
  task budget, daily cap), per-model concurrency, per-model efforts
  (bridged live to Hermes via `~/.hermes/model-efforts.json`), judge/super/
  plan/autopilot knobs, voice/vision/dictation, paths, auth.
- **Backups**: config-only encrypted USB snapshot + Timeshift
  (system-only); the reproducible install IS this repository (secrets
  excluded by design).

---

## 13. Added value, strengths, and weaknesses — the honest assessment

This section is deliberately not marketing. The system has a benchmark
program (§13.4) and its own first real-world result is mixed. Users should
know both halves.

### 13.1 Structural strengths (design-level, verified in operation)

- **Resilience is real.** The control/execution split, orphan-harvest
  ladder, stall-based turn guards, and quota backoff have repeatedly
  survived service restarts, session kills, suspend/wake cycles, an
  overnight SSE stall mid-benchmark, and multi-hour provider quota windows
  — without losing paid work.
- **Auditability no direct agent has.** Specs, per-stage decision logs,
  versioned deliverables, round-over-round diffs, anchored judge findings,
  and API-equivalent cost ledgers mean every output can be explained after
  the fact.
- **The machinery catches real defects.** In benchmark run bench-02 the
  pipeline found and fixed a crash-grade bug (unbounded GPU count), data
  errors confirmed against three sources, and UX defects — via its own
  review/judge loop, unprompted.
- **Deterministic, tested core.** 488 self-counting static checks plus ~20
  runtime e2e gates run on every commit; the quality-decision logic is
  deterministic and unit-tested rather than prompt-hoped.
- **Interviews beat assumptions — sometimes.** The Deep Plan interview
  asked materially better requirements questions than either direct-agent
  baseline in bench-02 (which asked zero).
- **Genuinely private and cheap to run.** Local data/memory/voice/vision;
  flat-rate GLM execution; frontier spend metered and capped per task.

### 13.2 Measured weaknesses (bench-02, run 1 — n=1, directional)

The first full real-world benchmark (build a client-ready AI-hardware
webshop with an intelligent recommendation engine; operator answering as
the client; report at `benchmarks/bench-02-webshop/COMPARISON-REPORT.md`):

| Arm | Blind score | API-equiv cost | Active time |
|---|---|---|---|
| Claude Opus 4.8 direct | **44/50** | $13.71 | 51 min |
| Claude Fable 5 direct | 43/50 | $16.48 | 34 min |
| **Nexus (Smart, SR off, full-auto)** | **28/50** | **$241.23** | ~2.5–3.3 h |

Against the program's own success criterion ("system quality ≥ direct, at
cost below one direct pass") run 1 **missed on both axes**. The failure
anatomy matters more than the score:

1. **Spec-compliance beat product sense.** The pipeline froze a bad design
   early ("sort GPUs by VRAM descending") and then five stages, nine judge
   rounds, and 99 green tests faithfully defended it — shipping $31k
   "budget" builds as PASS. Verification machinery amplifies whatever
   objective it is given.
2. **A stage SAW the problem and had no route to a human.** Code review
   filed the cost-absurdity finding as "spec limitation → operator
   decides" — and no decision card ever reached the operator.
3. **No live-research habit.** The GLM implementer baked in training-data
   products and prices (two fabricated products, a two-year-stale model
   list, wrong-market prices); both direct arms did live web research
   unprompted.
4. **The cost overhead is structural.** Multi-stage pipelines re-send
   context per stage and per judge round; the spec stage alone out-cost an
   entire direct run 3.5×.

Three tool fixes are gated before scored runs 2–3: a product-sanity judge
axis (drive the app with personas, judge outcomes), spec-limitation
findings must raise decision cards, and mandatory live research for
data-bearing briefs (§14).

### 13.3 Structural weaknesses and risks (beyond one benchmark)

- **Executor ceiling.** Output quality is bounded by GLM-tier models; the
  frontier tier only judges and occasionally rewrites — it does not do the
  primary work. Where GLM is weak (live research reflexes, product taste),
  the gates can only bound the damage, not create the missing quality.
- **Judge economics are freshly rebuilt and not yet re-validated.** Before
  the 2026-07-13 overhaul the judge consumed 75%+ of frontier spend with a
  0% round-1 SHIP rate; the overhaul (SHIP-with-notes, pre-gate, screen
  tier, delta re-judge, caps) is shipped and gated, but its paid A/B replay
  (`benchmarks/judge-loop-ab/`) has not run yet.
- **Complexity concentration.** `server.py` is an 11.5k-line monolith and
  `app.js` an 11.7k-line SPA; the gate suites mitigate but the bus factor
  is 1.
- **Single-machine by design.** SQLite + subprocess lanes + one shared
  12 GB GPU. This is a deliberate scope choice, not an accident — but it is
  a hard ceiling.
- **Evidence base is thin.** Every benchmark so far is n=1 per arm;
  learning loops leak experience between Nexus runs, so improvements are
  config + learning + fixes, never cleanly attributable.
- **Operator posture required.** This codebase treats itself as
  junior-authored: nothing is assumed right by default, and the production-
  readiness review campaign (§14) exists precisely because of that.

### 13.4 When to use it — and when not to

Use Nexus when the work benefits from what it uniquely has: unattended
multi-task execution, auditable process, deliverable/versioning/review
infrastructure, domain memory and learning, privacy, or flat-rate
economics at volume. Prefer a direct frontier agent (Claude Code) for
one-shot, judgment-heavy builds where product taste and live research
dominate — that is what bench-02 measured, and the direct arms won it
decisively. The benchmark ladder (bench-01 objective coding probe,
bench-02 real-world build, bench-03 marketing/research, judge-loop A/B,
and the pre-registered 27-brief added-value campaign) exists to keep this
answer honest as the tool improves.

---

## 14. Open work

The queue as of 2026-07-15, in dependency order:

1. **Judge-loop A/B replay** (`benchmarks/judge-loop-ab/RUNBOOK.md`, paid,
   operator-triggered): success = ≥40% frontier-$ cut, non-inferior blind
   pairwise, ≤1.2× GLM tokens.
2. **Bench-02 gate fixes** before scored runs 2–3: product-sanity judge
   axis; spec-limitation findings → decision cards; mandatory live research
   + anti-fabrication spot-checks for data-bearing briefs.
3. **Bench-02 runs 2 (Balanced) and 3 (Super Result ON)** against the
   frozen direct-arm baselines; then **bench-03** (marketing).
4. **Phase 8 — the pre-registered added-value campaign**
   (`benchmarks/added-value/`, 27 briefs, locked thresholds).
5. **Production-readiness review campaign**
   (`PRODUCTION-READINESS-REVIEW-PLAN-2026-07-13.md`) — now unblocked.
6. Smaller deferred items: Super-Result C4/C1d, deep-plan Step-11
   benchmark, N5–N8/B4 leftovers, JARVIS torso (parked), Kokoro TTS
   (blocked on py3.14).

---

## 15. Repository map and document index

| Path | What it is |
|---|---|
| `app/` | The Nexus control plane — THE live working tree (`~/nexus-agent-os` symlinks here) |
| `setup/` | The complete Hermes environment: configs, agents, skills, plugins, guardian, systemd, infra, knowledge base, bridge CLIs |
| `docs/DOCUMENTATION.md` | **This document** |
| `docs/archive/` | Implementation plans/reports and audits (judge loop, Super Result, Quality Autopilot, Deep Plan, security sweeps…) |
| `benchmarks/` | bench-01, bench-02-webshop, bench-03-marketing, judge-loop-ab, added-value |
| `install.sh` / `setup/install.sh` | Nexus-only installer / full Hermes-environment installer |
| `patches/`, `files/`, `system/`, `scripts/` | Historical feature patches, dev-specialist variants, systemd units, repo tooling |

**Per-subsystem sources of truth** (read before changing that area):
`app/CLAUDE.md` (orientation + hard rules) · `app/docs/SPEC-JUDGE-LOOP.md`
(judge cascade + invariants) · `app/SPEC-REAL-AGENTS.md` (dispatch/lanes/
budgets) · `app/docs/SPEC-SETTINGS-V2.md` · `app/docs/SPEC-MULTIUSER.md` ·
`app/docs/SPEC-BLOCK2.md` (review v2, galaxy editing, PRs) ·
`app/docs/SPEC-BLOCK3.md` (replanning, eval corpus) ·
`app/docs/SPEC-ONBOARDING.md` · `app/docs/JARVIS-VOICE.md` ·
`app/docs/TAILSCALE.md` · `setup/CLAUDE.md` (install runbook).
