# Nexus Agent OS — JARVIS Module

## Project Overview
Nexus Agent OS is a FastAPI + SQLite agent dashboard at /home/sinep/nexus-agent-os.
The JARVIS feature is an AI assistant interface integrated into the dashboard.
It connects to Hermes Agent API (localhost:8642) for LLM, Piper TTS for voice, and faster-whisper for STT.

## Architecture
- `server.py` — FastAPI server (port 8777, **HTTPS** — cert.pem/cert.key exist), serves API + static frontend
- `hermes_dispatch.py` — **real-execution engine (v2)**: runs a kanban task as a REAL Hermes
  API session (create session → SSE stream → deliverable files in `workspaces/<task-id>/` →
  real token usage). Budget/quota guardrails + resume/harvest live here. See SPEC-REAL-AGENTS.md.
- `worker.py` — agent-lane worker process (v2): claims ONE task at a time (atomic CAS) and
  executes it via hermes_dispatch. **The v1 simulation is gone** — no fake task strings, no
  random tokens (verify.sh enforces this). A lane exits when its agent is retired/stopped.
- `scripts/migrate_real_agents.py` — one-time migration (ran 2026-07-06): archived sim data,
  retired the SelfHealTest zombie, deleted seed demo agents/tasks, flipped dispatch.enabled=1.
- `voice.py` — GPU TTS (Piper) and STT (faster-whisper) pipeline
- `static/index.html` — Main dashboard HTML (grouped sidebar, inline SVG icons, toast/drawer roots)
- `static/app.js` — Frontend JS (vanilla, no build step), view router + all views
- `static/style.css` — Design system v3: glass panels over aurora backdrop, Inter UI font + JetBrains Mono for data, CSS variables
- `static/nexus3d.js` — ES module; dynamically imports Three.js from CDN and renders the dashboard 3D agent constellation (window.Nexus3D = mount/update/dispose)

## Key Design Rules
- **No build step.** All frontend is vanilla JS/HTML/CSS loaded via <script> and <link> tags.
- **Three.js must NEVER be referenced from index.html** (verify.sh gate rejects the string "three" there). It is dynamically `import()`ed inside `static/nexus3d.js` only.
- **No npm, no bundler, no node_modules.** Pure browser-side code.
- Dark theme tokens: --accent #7c5cff, --accent-2 #5eead4, --cyan #22d3ee, --bg #07070d, panels are translucent rgba glass. Fonts: --font-ui (Inter), --font-mono (JetBrains Mono), loaded from Google Fonts CDN.
- All server data interpolated into HTML goes through `esc()`. API errors surface via `toast()`.
- Live updates: tick() every 3s patches the DOM **in place** for dashboard/agents/monitor and only re-renders kanban/agentic when their data hash changes and no modal/drawer/drag is active (`uiLocked()`); WS events use `softRender()`. Don't reintroduce blind innerHTML rebuilds on tick — they eat clicks and input focus.
- The JARVIS view is rendered by `renderJarvisView()` in app.js which sets `$('#content').innerHTML`

## JARVIS Voice Flow
1. Browser captures mic audio via `MediaRecorder` (audio/webm; codecs=opus)
2. Audio sent to `POST /api/jarvis/stt` as multipart form upload
3. Transcribed text sent to `POST /api/jarvis/chat/stream` (SSE proxy to Hermes Agent API)
4. Reply text split into sentences, each sent to `POST /api/jarvis/talk` (ONE call per sentence)
5. `/talk` returns a single muxed MP4 (TTS audio + Wav2Lip video). The SAME blob plays in a
   muted `<video>` (face) + persistent `<audio>` (voice). Prefetch pipeline renders sentence
   N+1 while N plays. **See `docs/JARVIS-VOICE.md` for full details.**

## Avatar Requirements
The avatar is a NEURAL TALKING-HEAD (Wav2Lip), NOT a 3D mesh or cycling frames.
**Full implementation docs: `docs/JARVIS-VOICE.md` — READ THIS before editing JARVIS voice/avatar code.**
Key points (current architecture):
- Source face: `static/avatar/reference.jpg` (MUST be ≤512×512 JPEG or Wav2Lip face-detector OOMs)
- The browser calls `/api/jarvis/talk` ONCE per sentence → returns a single muxed MP4 with
  BOTH audio (TTS voice) + video (lip-synced face). Do NOT fetch /tts and /talk in parallel
  (causes /talk to 500 under GPU pressure → face delayed 2-3 sentences).
- The SAME MP4 blob plays in a MUTED `<video id="jAvatarVideo">` (face) + a persistent
  `<audio>` element (voice). Muted video = autoplay never blocked by Chrome. Persistent audio
  element = unlocked by user gesture, reused every clip.
- State-driven: idle, listening, thinking, talking. Avatar resets to idle picture after speaking.
- Inference runs in `/home/sinep/ml-env` (torch+CUDA). Wav2Lip repo at `/home/sinep/Wav2Lip`.
- **Idle model unloading:** after 60s with no voice activity, Piper TTS + faster-whisper STT
  are unloaded from memory (frees VRAM). They reload lazily on next use. Config: `voice.py`
  `IDLE_TIMEOUT = 60.0`, checked every 15s by a background thread in `server.py`.
- **Cache-busting:** when editing `app.js`, `style.css` or `nexus3d.js`, bump `?v=N` in
  `index.html` or the browser serves stale cached code (currently style v=4, app v=8, nexus3d v=1).
- TTS voice: Piper "ryan" (male). Backup of old female voice at `models/piper_voice_female_backup.onnx`.

## Python Environment
- Venv at `.venv/` (Python 3.14) — the nexus server + Playwright for tests
- Start server with `bash start.sh` (sets LD_LIBRARY_PATH for CUDA, then runs main.py)
- HTTPS: if `cert.pem` + `cert.key` exist, server auto-enables HTTPS (needed for mic on non-localhost)
- Piper TTS model at `models/piper_voice.onnx`
- faster-whisper (medium.en, CUDA) uses CUDA libs from `/usr/local/lib/ollama/cuda_v12/`

## Test / Verify (canonical commands)
- **Static gate (fast, every edit):** `bash scripts/verify.sh` — JS/Python syntax, no debug leftovers, function integrity, Agentic capabilities integrity, + real-dispatch/judge/health integrity incl. sim-is-dead negatives (the gate prints its own count — 107 checks as of v2.2). Must pass before commit; the git pre-commit hook enforces it.
- **The server runs as a systemd user unit:** `systemctl --user restart nexus` is THE way to
  restart it (unit: ~/.config/systemd/user/nexus.service → start.sh). Don't nohup start.sh
  manually — a stray instance blocks port 8777 and bypasses the unit.
- **Runtime gate — REAL dispatch (v2):** `.venv/bin/python scripts/verify_real_dispatch_e2e.py` — spawns a real lane, drives a task through a REAL Hermes `api_*` session (claim → queue → worker executes → deliverable file + tokens + transcript), budget block, injected-429 quota block + auto-retry, kill-worker→resume, retire→no-respawn. GLM-dependent steps fail while Z.ai load-sheds (error 1305) — that's upstream, not the gate.
- **Runtime gate — API (integration):** `.venv/bin/python scripts/verify_agentic_e2e.py` — exercises all 9 agentic endpoints (claim/verify/approvals/memory/scheduler/cost/messages/worktree) via HTTP. 30 checks.
- **Runtime gate — UI (Playwright):** `.venv/bin/python scripts/verify_agentic_playwright.py` — loads the Agentic view in a real headless browser, asserts all subsystem cards render, exercises the approval + scheduler flows from the UI, captures console errors. 11 checks. This catches frontend↔backend contract drift the static gate cannot.
- **Runtime gate — v3 UI features:** `.venv/bin/python scripts/verify_v3_ui.py` — agent detail drawer (memory/messages/cost tabs + add/delete memory), kanban task create/edit/delete + search filter, memory-hub subtabs, specialists learning pipeline, watchdog config modal, JARVIS still boots. 24 checks.
- **Screenshot sweep:** `.venv/bin/python scripts/screenshot_all_tabs.py <suffix>` — screenshots all 14 tabs to `~/.hermes/cache/screenshots/nexus-<suffix>/`, fails on any console error.
- All runtime scripts target **https://127.0.0.1:8777** (self-signed → `verify=False` / `ignore_https_errors=True`).
- **Runtime gate — JARVIS:** `.venv/bin/python scripts/verify_jarvis_e2e.py` — full Playwright run: page renders, reply streams (SSE), lip-sync video plays, state transitions, returns to idle.
- **Runtime gate — Block 3 (replanning/evals/plan-editor):** `.venv/bin/python scripts/verify_block3_e2e.py` —
  revalidate round-trip, replan detect→dismiss→re-arm→apply (archival, rewiring, loop reset,
  approval expiry), eval run lifecycle on a scratch corpus with stubbed generation+judge,
  per-user isolation. 33 checks, self-cleaning.
- **Runtime gate — Block 3 UI (Playwright):** `.venv/bin/python scripts/verify_block3_ui.py` —
  drives the plan editor inside the proposal modal (edit/add/revalidate without creating),
  the replan review modal, and the Specialists→Evals tab. 15 checks.
- **Per-edit gate:** `.claude/check.sh` (auto-run by Claude Code PostToolUse on Write|Edit).
- Playwright is installed in `.venv`. Screenshots save to `~/.hermes/cache/screenshots/`.

## Real Dispatch (v2 — added 2026-07-06, SPEC-REAL-AGENTS.md is source of truth)

The Agents fleet is now the REAL execution layer of Hermes — the v1 simulation is deleted.
- **Agent = executor lane**: a `worker.py` subprocess per agent row; claims one task at a
  time; opens ONE fresh Hermes session per task (`nexus:<task-id>`, an `api_*` session id);
  streams the work (SSE → live preview, tool events → activity feed, `run.completed` → real
  token counts); writes `workspaces/<task-id>/deliverable.md` (+ `_dispatch.json` audit).
- **Dispatch is queue-only**: `POST /api/tasks/{id}/dispatch` claims + marks `queued`; the
  lane worker is the SOLE executor (no server-thread execution — race designed out).
  Feature flag: settings `dispatch.enabled` (now default ON). Budgets: settings
  `dispatch.default_task_budget` (1M) / `dispatch.daily_cap` (10M) / per-task `budget_tokens`.
- **dispatch_state lifecycle** (orthogonal to kanban columns): none → queued → dispatching →
  streaming → finalizing → completed | failed | blocked_budget | blocked_quota.
- **Self-heal resumes, not restarts (R3)**: dead worker → watchdog respawns it → new worker
  harvests the orphaned-but-finished Hermes run from session history (free), else sends a
  continue-turn into the SAME session; fresh re-dispatch only if the session is gone.
- **`retired` is a terminal agent status** — watchdog never touches it (`POST
  /api/agents/{id}/retire`). This is how the SelfHealTest zombie ended (10,954 respawns).
- **ONE kanban**: Nexus's (nexus.db) is the single source of truth + dispatch queue.
  Hermes's `~/.hermes/kanban.db` is RETIRED (was empty; its toolset is disabled) — do not
  bridge or revive it.
- **Quota reality**: Z.ai 429 error 1305 = probabilistic load-shedding at peak, NOT quota
  exhaustion. blocked_quota + exponential backoff (settings `dispatch.quota_backoff_until`,
  `dispatch.quota_consecutive`); test injection knob `dispatch.force_429`.
- Hermes API facts (verified against source): sessions persist in `~/.hermes/state.db` and
  survive gateway restarts; `delegate_task` is SYNCHRONOUS on the api_server platform;
  client disconnect does NOT kill a run (it finishes orphaned → harvestable); per-request
  `system_message` = ephemeral framing; **session titles must be UNIQUE** (create_session
  retries with a `~hex` suffix on collision). NO Hermes-side changes are needed or wanted.

### v2.1 additions (2026-07-06, user-testing round 3)
- **Workflows (= "Projects" in the UI, nav `data-view="workflows"`)**: `workflows` table +
  `tasks.workflow_id`/`tasks.depends_on` (JSON id list). A task runs only when all
  dependencies are `done` (worker skips claiming; manual dispatch 409s); done predecessors'
  `deliverable.md` paths are injected as INPUT into the dispatch framing. Endpoints:
  GET/POST/PATCH/DELETE `/api/workflows(/{id})`. Example-campaign creator in the UI.
- **Deliverables tab** (nav `data-view="deliverables"`): `GET /api/deliverables` aggregates
  every task's workspace files; inline .md preview; follow-up chaining sets a real dependency.
- **Per-model concurrency slots**: Z.ai allows ~10 concurrent PER MODEL, Hermes 10 total.
  `hermes_dispatch.slot_available()/slots_in_use()` count live dispatches (fresh heartbeats);
  workers WAIT instead of erroring. Settings: `dispatch.max_concurrent_per_model` (8),
  `dispatch.max_concurrent_total` (8). `/api/quota` exposes `in_flight` per model.
- **Per-task model** (`tasks.model`): glm-5.2 default / glm-5.1 / glm-4.5-air — session is
  created with that model; lighter tasks use a separate concurrency pool.
- **Skill wizard**: `/api/hermes-skills` list/get/save + `/api/hermes-skills/wizard` (AI
  drafts SKILL.md → human reviews → save writes `~/.hermes/skills/<name>/SKILL.md`).
  Specialist wizard: `/api/specialists/wizard` (same pattern; eval gate on save stays).
- **App preview (v3.3)**: ▶ Test a task's program output live. app_runner.py detects the
  runnable in the workspace (package.json dev/start → npm install+run; app.py/main.py
  (+requirements→.venv-preview) → python; index.html → python -m http.server), runs it as
  its own process group on a dedicated 127.0.0.1 port (8790-8820, max 3 concurrent, env
  marker NEXUS_PREVIEW=1 for pid identity), logs to <ws>/_preview.log, auto-stops after
  30 min (reaper thread also kills restart-orphans; registry workspaces/.preview-apps.json).
  Endpoints: GET/POST /api/tasks/{id}/app(/start|/stop|/log). UI: ▶ Test app in the
  Deliverables rows + task detail → modal with live log → opens the app in a new tab when
  it answers. Caveat: dev servers that ignore the PORT env (vite without --port) show as
  'starting' forever — the log tells the truth.
- **Looping (v3.2)**: per-task and per-project improve-and-recheck loops.
  `tasks.loop_config` / `workflows.loop_config` (JSON: enabled, mode open|closed,
  preference quality|speed, auto_judge, triggers[] with per-trigger max_rounds/used).
  `POST /api/loop/design {kind, id?|meta, preference, mode}` — DETERMINISTIC designer
  (loop_engine.design_loop, no LLM): inspects the item's real shape (verifier stage?
  domain rubric? high-stakes?) and emits the config + plain-language reasoning.
  RUNTIME: loop_engine.loop_engine_thread (started like the watchdog) sweeps every 20s;
  closed mode only: verify-FAIL on a looped project → retry fix task with the verifier's
  findings + re-verify; judge REVISE/REWRITE on this deliverable version → auto-retry
  (judge findings auto-attach); quality mode auto-runs the judge on fresh high-stakes
  deliverables. Bounded: per-trigger round caps (regenerating resets them), 3 actions per
  sweep, budgets still apply. Open mode = engine does nothing (checkpoints wait for the
  human — the pre-v3.2 behavior, now an explicit choice). UI: enable + quality/speed
  cards in task-create and wizard project modals; 🔁 View/edit loop in task/project
  detail opens the loop modal (flow diagram, trigger cards with round counters,
  reasoning, open↔closed switch, regenerate, disable).
- **Attachments (v3.1)**: operators attach input files (pdf/office/images/text, ≤25 MB)
  to a task (`workspaces/<task-id>/attachments/`) or a whole project
  (`workspaces/workflow-<id>/attachments/`) via the task-detail / project-detail modals;
  endpoints `GET/POST/DELETE /api/{tasks|workflows}/{id}/attachments(/{name})`. Dispatch
  framing lists them as MUST-READ input; extraction + binary OUTPUT formats (pdf, docx,
  xlsx, pptx, png) run through the nexus `.venv` python, which has python-docx, openpyxl,
  python-pptx, reportlab, pypdf, pillow, markdown preinstalled.
- **Task wizard** (v3): `POST /api/tasks/wizard {instruction, answers?}` — two-phase.
  Phase 1 may return `{type:"questions"}` (ONE round, ≤6 — ask-when-in-doubt; each option carries pros/cons + a ★ recommended best-practice pick; unknowns that change the
  plan's SHAPE — stack/platform, acceptance criteria, real-money blast radius; every
  question carries a default so it is skippable). Phase 2 (body has `answers`) must return
  a plan; a second questions reply is retried once with defaults, then 502.
  Plans carry `assumptions` (also embedded into the description / task 0) and `repairs`.
  CODING GOALS get the house pipeline template: spec&plan (tech-lead-orchestrator) →
  implement+tests (code-implementer) → code review (code-reviewer) → fix findings
  (code-implementer, NO-OP if review clean) → acceptance verification (acceptance-verifier,
  high_stakes ALWAYS). `_repair_workflow()` then deterministically enforces it: whitelists
  specialists against the live roster, forces glm-5.2 on dev stages, inserts missing
  review/fix/verify gates (append-only → acyclic by construction), moves the verifier to
  the end as unique sink, chains orphans, and falls back to a sequential chain on any
  repair error. Non-coding: research→create (2-3 tasks) or single task; the frontier judge
  is the review stage for high-stakes content — no extra review task.
  UI entry points: Kanban "✨ Describe a task", Projects "✨ Describe a goal"; the proposal
  modal shows stages (parallel tasks grouped), assumptions, auto-repairs, and lets the
  operator untick optional tasks (quality gates are locked; skipped tasks are spliced out
  of the DAG so dependents inherit their dependencies).

### Block 3 (2026-07-08, docs/SPEC-BLOCK3.md is source of truth)
- **Plan editor in the proposal modal (R1)**: every wizard-proposed task is editable in place
  (title/brief/specialist/domain/model/stakes/budget/deps — deps only from EARLIER tasks, so
  the DAG stays acyclic in the UI), tasks can be added/removed, quality gates stay locked.
  An EDITED plan goes through `POST /api/tasks/wizard/revalidate` (same `_repair_workflow`,
  `max_raw=7`) before creation; repairs re-render for one more confirm. Shared editor
  functions `planEd*` in app.js are reused by the replan review modal.
  `GET /api/specialists/names` = light roster for pickers (no qdrant scroll).
- **Mid-run replanning (R2)** — three separate gates BY DESIGN: (1) the loop engine only
  DETECTS (`_sweep_replan_detection`: terminal `dispatch_state='failed'`, or verifier FAIL
  with no automatic fix round left) and flags `workflows.replan` (JSON status
  needed/drafting/proposed/applied/dismissed); (2) DRAFTING is operator-triggered
  (`POST /api/workflows/{id}/replan/draft`, judge-style background thread; boot resets
  orphaned `drafting`→`needed`); (3) APPLY (`.../replan/apply`) is operator-approved after
  editing in the plan editor — refuses while a stage executes (409), archives superseded
  non-done tasks (`status='archived'`: kept for audit, excluded from rollups/board/engine),
  creates recovery tasks in Backlog (roots inherit every DONE task as INPUT deps), expires
  stale approvals, resets loop rounds. Dismissed failures don't re-flag; a NEW failed task
  re-arms. The engine NEVER rewrites a pipeline itself.
- **Eval corpus (R3, remediation #6)**: fixed briefs in `~/knowledge/domains/<domain>/evals/*.md`
  (27 cases, format in `~/knowledge/domains/EVALS-README.md`) run through the REAL dispatch
  framing (`hermes_dispatch.build_framing`) and scored by the frontier judge against the
  domain RUBRIC — `evals.py` runner (sequential daemon thread, one run at a time), tables
  `eval_runs`/`eval_results` (user-scoped), config fingerprint per run (playbook/rubric/
  style/context/specialist hashes) so score deltas map to config changes. UI: Specialists →
  📏 Evals (domain cards + trends, run history, per-case judge output). The task judge and
  the eval runner share `evals.run_judge_cmd` (settings `judge.cmd` stays the stub hook);
  gate-only hooks `evals.corpus_root`/`evals.stub` default off.

## Agentic OS Capabilities (v1 — added 2026-07-04)

First-class features implementing the agentic-coding harness concepts + competitive
research (amux, arXiv "Code as Agent Harness", SuperAGI, Microsoft Agent Framework).
All map to the 5-layer orchestration stack (Runtime/Isolation/Communication/Coordination/Observability).
**v2 note:** the fake workload behind these mechanics is gone (see Real Dispatch above); the
mechanics themselves (claiming, watchdog, approvals, cost, worktrees, scheduler) stand.

### Coordination layer
- **Atomic task claiming** — `POST /api/tasks/{id}/claim` uses SQLite CAS (UPDATE...WHERE
  status IN ('backlog','todo') + ownership verify). Two agents can never grab the same task;
  second claimer gets 409 with the owner named. Release via `/release`.

### Quality layer (Plan-Execute-Verify)
- **Verify loop** — `POST /api/verify` runs a command, captures exit code + stdout/stderr tail,
  persists to `verify_runs` table. Runtime runs update the task's `verify_status`
  (passing/failing). `GET /api/verify/runs` lists history. This is the OS-level version of the
  static+runtime verify-gate from the coding harness.

### Safety layer
- **Approval gates** — `POST /api/approvals` creates a pending request (agent asking permission
  for sensitive actions: deploy, sudo, destructive ops). `PATCH /api/approvals/{id}` decides.
  Pending count shows as a nav badge. Mirrors SuperAGI's Action Console.

### Resilience layer
- **Self-healing watchdog** — background thread (watchdog.py) every 10s: restarts dead agents
  (PID gone), detects stuck agents (stale heartbeat past watchdog.stale_threshold_s, default 150s) and restarts them, enforces cost caps.
  Configurable via settings table. `GET /api/watchdog/status` for config + recent actions.
  Dead agents are marked 'crashed' (not silently 'idle') so the watchdog heals them. Verified:
  a killed agent is auto-restarted with a new PID in ~3s, same agent ID preserved.

### Isolation layer
- **Git worktree isolation** — `POST /api/agents/{id}/worktree` creates an isolated git worktree
  + branch (session/<short>) so parallel agents never stomp each other's files (the amux pattern).
  worktree.py handles create/has-changes/remove (never force-removes a dirty worktree).

### Memory layer
- **Agent memory** — `memory` table with STM/LTS/experience/longterm scopes.
  `POST/GET/DELETE /api/agents/{id}/memory`. `GET /api/agents/{id}/memory/context` returns a
  condensed context blob (LTS summary + recent experience) — the SuperAGI two-part model.

### Automation layer
- **Cron scheduler** — `scheduled_jobs` table + scheduler.py background thread.
  Minimal cron parser (*, */N, single value, comma lists) across the 5 standard fields.
  `GET/POST/PATCH/DELETE /api/scheduler`. Verified: a */1 job fires within ~70s.

### Cost layer
- **Cost guardrails** — `GET /api/agents/{id}/cost` returns tokens + pct of max_tokens cap +
  projected_usd (configurable via NEXUS_COST_PER_1M_TOKENS). Watchdog force-sets status to
  'cost_capped' when an agent exceeds its max_tokens. Per-agent caps live in the config JSON.

### Communication layer
- **Inter-agent messaging** — `messages` table. `POST /api/agents/{id}/message` sends agent→agent.
  `GET /api/agents/{id}/messages?direction=` lists sent/received. Agents discover peers via the
  agents table (no external service discovery).

### Frontend
- **Agentic view** — new nav item "⚙ Agentic" renders a dashboard of all subsystems: approval
  gates (with Approve/Reject buttons + nav badge), watchdog status + recent actions, verify runs,
  cron scheduler (create/toggle/delete jobs), cost guardrails summary.
- **Enhanced kanban** — task cards now show claimed_by (⚑ owner), verify_status badge, and the
  claim flow is wired through the WS broadcast.
