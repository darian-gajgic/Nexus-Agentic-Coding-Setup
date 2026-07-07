# SPEC — Real Agents: Nexus as the Hermes Control Plane (v2)

> Spec-driven build, 2026-07-06. Source of truth for this mission. Supersedes the *workload*
> of SPEC-AGENTIC.md (the simulation) while keeping its *mechanics* (claiming, watchdog,
> approvals, cost, worktrees) — that intent stands.
>
> **The one-sentence goal:** a kanban card created in the Nexus UI is executed by a real
> Hermes session (real specialists, real tokens, real files), visibly, safely, and
> recoverably — so two non-technical operators can run their whole AI workforce from one place.

## 0. Decisions already made (user-confirmed 2026-07-06)

| Decision | Choice | Why |
|---|---|---|
| Kanban source of truth | **Nexus kanban (nexus.db) only.** Hermes `~/.hermes/kanban.db` is retired — declared dead, left untouched, no bridge. | Inspected: the Hermes board is empty (0 rows in all 8 tables) and its toolset is disabled in the gateway. Nothing to migrate, nothing to sync. |
| Workspace location | **`~/nexus-agent-os/workspaces/<task-id>/`**, gitignored | One system owns everything about a task; the server serves the files trivially. |
| Budget defaults | **Generous: 1,000,000 tokens/task, 10,000,000 tokens/day** (both editable in the UI) | Runaway-loop protection, not money protection (GLM is quota-window based). |
| §3 extras in scope | **All six** (activity feed, templates, notifications, onboarding widget, quota dashboard, retry-with-feedback) | Each is small; they land in Stage 4 and get cut bottom-up if anything strains the core. |

## 1. Facts the design rests on (verified against Hermes source, 2026-07-06)

These were discovered by reading `~/.hermes/hermes-agent/gateway/platforms/api_server.py`
(4,892 lines) and `tools/delegate_tool.py`. If Hermes is ever updated and something breaks,
re-verify these first.

- **API server:** `http://127.0.0.1:8642`, auth `Authorization: Bearer $API_SERVER_KEY`
  (env loaded from `~/.hermes/.env` by `main.py` — the existing JARVIS pattern, keep it).
- **Sessions are persistent and resumable.** `POST /api/sessions` → id `api_<ts>_<hex8>`,
  stored in `~/.hermes/state.db`, survives gateway restarts; history via
  `GET /api/sessions/{id}/messages`.
- **Streaming:** `POST /api/sessions/{id}/chat/stream` → SSE with `run.started`,
  `assistant.delta`, `tool.started/progress/completed/failed`, `assistant.completed`,
  `run.completed {usage}`, `error`, `done`. Keepalive every 30s. `usage` carries real
  `input_tokens`/`output_tokens` per turn.
- **Per-request framing:** the stream endpoint accepts `system_message` — an *ephemeral*
  system prompt layered on top of the core prompt for that turn only (api_server.py:1913).
- **Specialist delegation is SYNCHRONOUS on this platform.** `delegate_task` defaults to
  blocking, and `background=true` is force-downgraded to synchronous because api_server
  sessions bind `async_delivery=False` (delegate_tool.py:2440, 2859-2877). The specialist's
  full result returns inside the same turn. (The WORKFLOW.md "async-only" warning applies to
  one-shot CLI sessions, NOT to this API path.)
- **There is NO API field to force a specialist.** Routing happens inside the agent via
  `delegate_task`; we steer it through the dispatch prompt ("delegate this to <name>").
- **Client disconnect does NOT kill the run.** On chat/stream disconnect the agent (and any
  in-flight delegation) runs to completion orphaned and flushes to state.db — a rebooted
  worker can harvest the finished result from `/messages`. This is the backbone of
  resume-based self-heal.
- **The dispatched agent can write files.** The `hermes-api-server` toolset includes
  `write_file`, `patch`, `terminal`, `execute_code`, `delegate_task` — unsandboxed, running
  as user `sinep`. It can write into the task workspace directly. It has NO kanban tools
  (by config) — fine: Nexus is the board.
- **Hermes-side changes required: NONE.** No config.yaml edits, no source edits.
- **Concurrency cap:** Hermes rejects >10 concurrent runs with a local 429 (fail-fast,
  `Retry-After: 1`). Fleet default of 2–3 agents leaves headroom for JARVIS.
- **Upstream Z.ai 429/quota** may surface as a run failure/partial (`finish_reason:"error"`,
  `run.failed`) rather than an HTTP 429 — quota detection must match error text, not just
  status codes.

## 2. Architecture (plain words)

**An agent = a named executor lane.** The `agents` table row is the lane; a rewritten
`worker.py` subprocess is its engine. The lane claims one task at a time from the kanban,
opens ONE fresh Hermes session per task, streams the work live into nexus.db, writes
deliverable files into the task workspace, and moves the card. The watchdog keeps lanes
alive; retiring a lane is a real lifecycle state the watchdog respects.

```
Kanban card (todo) ──atomic CAS claim──▶ worker.py (agent lane, real PID)
                                            │  POST /api/sessions        → api_* id stored on task
                                            │  POST .../chat/stream      → SSE consumed live:
                                            │     assistant.delta  → live preview, heartbeat
                                            │     tool.*           → activity feed entries
                                            │     run.completed    → real token usage
                                            ▼
                            workspaces/<task-id>/  (deliverable.md + any agent-written files)
                                            │
                        high_stakes? ──yes──▶ status 'review' + approval row → [Run frontier judge]
                                    └─no───▶ status 'done'
```

Why a subprocess per lane (instead of threads in the server): process isolation keeps a hung
HTTP stream from touching the server; the watchdog's PID-based healing, heartbeats, and the
whole existing fleet mechanic stay meaningful — they now guard real work.

**Dispatch prompt contract.** Every dispatch sends `system_message` (task framing) + `input`
(the task). The framing includes: the workspace absolute path ("write your final deliverable
to `<workspace>/deliverable.md`; put any additional files beside it"), the domain
(→ specialist knowledge protocol handles PLAYBOOK/RUBRIC itself), the specialist instruction
when one is chosen ("delegate this task to specialist '<name>' via delegate_task and include
its full result"), and the standing rules (end with the rubric self-score line and the
`**Learn:**` section). The worker ALWAYS writes `deliverable.md` from the final assistant
message itself if the agent didn't — a deliverable file must exist deterministically.

## 3. Requirements (numbered, testable)

### R1 — Real execution
1.1. A new module `hermes_dispatch.py` encapsulates the Hermes API client: create session,
     stream a turn (yielding parsed SSE events), fetch messages, health probe. Auth/env
     identical to the JARVIS pattern. Never logs or prints the key.
1.2. `worker.py` is rewritten as a real dispatch loop. The simulation (fake task strings,
     `random.randint` tokens) is deleted. Loop: poll → claim → dispatch → stream → finalize
     → idle. No fake data remains anywhere in the repo (gate-checked).
1.3. Claiming is the existing atomic CAS (`UPDATE … WHERE status IN ('backlog','todo')`),
     shared between the HTTP endpoint and the worker via one code path in `database.py`.
     A lane claims: tasks with `assignee_id = <me>` first, else unassigned `todo` tasks if
     the lane's `auto_claim` config is on (default on). Manual `POST /api/tasks/{id}/dispatch`
     assigns + queues a specific task.
1.4. One fresh Hermes session per task; `tasks.session_id` stores the `api_*` id; the session
     title is `nexus:<task-id>` so it's identifiable in Hermes tooling.
1.5. Task cards gain: `domain` (one of the 9 knowledge domains or `general`), `specialist`
     (optional, from `/api/specialists`), `high_stakes` (bool), `budget_tokens` (default from
     settings). The create/edit modal exposes them (R5 does the framing).
1.6. On successful completion: final assistant message stored as `tasks.result_summary`
     (truncated) + written to `workspaces/<task-id>/deliverable.md`; rubric self-score line
     and `**Learn:**` section parsed into `tasks.rubric_score` / `tasks.learn_section`;
     `high_stakes=0` → status `done`; `high_stakes=1` → status `review` + approval row (R4).
1.7. Feature flag: settings key `dispatch.enabled` (default `0` until Stage 2 ships). Flag
     off = workers idle without dispatching. The sim never runs again either way.

### R2 — Real telemetry
2.1. Heartbeat = real activity: the worker updates `last_heartbeat` on every poll tick and
     on every SSE line received (including 30s keepalives). No artificial heartbeats.
2.2. Tokens = real usage: `run.completed.usage` increments `tasks.tokens_used` and the
     agent's `tokens_in`/`tokens_out`. A new `dispatches` table records every dispatch
     (task, agent, session, start/end, state, tokens, error) — the audit trail and the
     daily-cap ledger. `/api/agents/{id}/cost` and `/api/stats` therefore report real numbers.
2.3. Logs = the real transcript: `GET /api/tasks/{id}/transcript` proxies the Hermes
     `/api/sessions/{sid}/messages` for the task's session; the task detail drawer and the
     agent drawer render it (roles, tool calls, timestamps).
2.4. Live status: during a stream, `agents.current_task` shows the task title + a rolling
     preview from `assistant.delta`; `tool.*` events append real rows to `activity`
     (this IS §3-feature-1, the real activity feed).

### R3 — Self-heal that resumes, not restarts
3.1. New agent status `retired`: terminal, set via `POST /api/agents/{id}/retire` (stops the
     PID, releases any claimed task back to `todo` — unless mid-dispatch harvesting applies).
     The watchdog and metrics loop NEVER restart or touch a retired agent. UI: Retire button.
3.2. The zombie `SelfHealTest` (agent-9693f66f) is retired by the migration script; a gate
     asserts it stays down (no new PID, status still `retired` after 2 watchdog sweeps).
3.3. On worker death mid-dispatch (watchdog restarts the lane): the new worker finds its
     `in_progress` task with a `session_id` and first checks `/messages` — because a
     disconnected run finishes orphaned, the result may already be complete → harvest it and
     finalize normally. Otherwise it sends a resume turn to the SAME session ("you were
     interrupted — continue; deliver as originally instructed"), keeping full context.
3.4. Only if the session is unusable (404 / unreadable) does it fall back to a fresh
     re-dispatch from the card (new session), and logs that it did.
3.5. `restart_count` and dispatch state transitions are visible in the agent drawer.

### R4 — Approval gates become real (flagship)
4.1. A `high_stakes=1` task never lands in `done` directly: on completion it moves to
     `review` and creates an approval row (`action_type='deliverable'`,
     `payload={"task_id": …}`) — surfacing in the existing approvals UI + nav badge.
4.2. The task drawer (and approval card) shows the deliverable (rendered `deliverable.md` +
     file list) and a **Run frontier judge** button → `POST /api/tasks/{id}/judge` runs the
     judge command asynchronously (it takes minutes); `GET /api/tasks/{id}/judge` polls
     status/result.
4.3. The judge command is the settings key `judge.cmd`
     (default `cjudge {file} {domain}`). The runner parses the output for the verdict line →
     `SHIP` / `REVISE` / `REWRITE` badge, extracts blocking items and the `Learning note:`
     line, stores raw output in `tasks.judge_output`. The gate uses a stub command via this
     key (CI speed); one real `cjudge` run is demonstrated manually at Stage-3 handoff.
4.4. Approve → task `done`, approval row `approved`. Reject → approval `rejected`, task back
     to `todo` with `retry_feedback` set (see R-X6); the deliverable stays in the workspace
     (history is never destroyed).

### R5 — Business Brain in the UI
5.1. Task creation: domain picker (9 domains + general), specialist picker (live from
     `/api/specialists`, optional), high-stakes toggle (pre-checked when the chosen domain's
     playbook escalation list matches — heuristic: a `templates.json` flag per template;
     manual toggle always wins), budget field (prefilled 1M).
5.2. Dispatch framing carries the domain so the specialist's own knowledge protocol does the
     PLAYBOOK/RUBRIC work (we do not re-implement it in Nexus).
5.3. Completed tasks render `rubric_score` and `learn_section` as first-class UI elements on
     the task drawer (score line as a badge, Learn as a highlighted panel) — not buried in
     the transcript.

### R6 — Deliverables are files
6.1. Every dispatched task gets `workspaces/<task-id>/` (created at dispatch;
     `workspaces/` gitignored). `tasks.workspace_path` stores it.
6.2. `GET /api/tasks/{id}/files` lists the workspace (name, size, mtime);
     `GET /api/tasks/{id}/files/{name}` downloads (path-traversal-safe: resolved path must
     stay inside the workspace). The drawer shows the file list with download links and an
     inline preview for text/markdown.
6.3. **Log as WIN / Log as LESSON** buttons open a small form (what happened + the real
     numbers — the form REQUIRES the numbers field for WINS, never invents them) →
     `POST /api/tasks/{id}/feedback {kind, note, numbers}` appends a dated, task-linked
     entry to `~/knowledge/feedback/WINS.md` / `LESSONS.md` in their existing format.

### R7 — Cost guardrails become real
7.1. At dispatch: if `tasks.budget_tokens` ≤ `tokens_used`, or today's fleet total (from
     `dispatches`) ≥ `dispatch.daily_cap`, the worker does NOT dispatch; the task's
     `dispatch_state` becomes `blocked_budget` (per-task) or `blocked_quota` (daily/window)
     — visible badge on the card, never a silent error. Operator can raise the budget on the
     card or wait; workers re-check periodically.
7.2. Settings keys `dispatch.default_task_budget` (1,000,000) and `dispatch.daily_cap`
     (10,000,000), editable via a small settings endpoint + the Agentic view.
7.3. 429/quota storm handling: on a Hermes-local 429, or a run failure whose error text
     matches rate-limit signatures (`429`, `rate limit`, `quota`), the worker sets
     `dispatch.quota_backoff_until` (now + backoff, exponential per consecutive hit, cap
     30 min), releases nothing, marks the task `blocked_quota`, and ALL lanes pause
     dispatching until the timestamp passes. `GET /api/quota` exposes state; the UI shows a
     global amber quota banner while backoff is active. A test-only settings key
     `dispatch.force_429` (default absent) makes `hermes_dispatch` simulate the failure so
     the gate can prove the whole chain without hammering Z.ai.
7.4. Mid-task: usage is accumulated per turn; a task that exceeds its budget between turns
     is not sent further turns (`blocked_budget`), partial work preserved in the workspace.

### R8 — Health panel
8.1. `GET /api/health/full` returns status lights for: hermes-gateway (systemd user unit
     active?), Hermes API (`GET :8642/health`), Qdrant (`:6333`), Langfuse (`:3000`), Ollama
     (`:11434`), and Nexus workers (live PIDs vs non-retired lanes) — each `{ok, detail,
     fix}` where `fix` is the exact copy-pasteable restart command (from MANUAL.md).
8.2. A Health card renders on the Agentic view (new card — existing card h3 texts untouched);
     red lights show the `fix` command next to them. Killing the gateway turns its light red
     within one refresh (demonstrated at handoff).

### R-X — §3 extras (all six, Stage 4, cut bottom-up if needed)
X1. **Real activity feed** — falls out of R2.4 (tool events + dispatch lifecycle in
    `activity`); dashboard feed shows them live.
X2. **Task templates** — `templates.json` in the repo (seeded from `~/knowledge/evals/cases/`
    + one per common deliverable: marketplace listing, social post, landing hero, research
    question, DJ set plan); `GET /api/templates`; template picker in the create modal
    prefills title/description/domain/specialist/high-stakes.
X3. **Desktop notifications** — server best-effort `notify-send` on task completion and on
    approval-needed (pattern from `~/.hermes/scripts/error-watchdog.sh`); silent no-op when
    unavailable.
X4. **Onboarding widget** — `GET /api/onboarding-status` counts `{{FILL:` slots in
    `~/knowledge/BUSINESS-CONTEXT.md` + `STYLE-VOICE.md`; dashboard shows a "run the
    onboarding" call-to-action until 0 remain.
X5. **Quota dashboard** — the Agentic/Observability area shows today's GLM tokens (from
    `dispatches` + Langfuse daily metrics) vs the 5-hour-window reality, plus backoff state.
X6. **Retry with feedback** — on a rejected/REVISE deliverable, one click re-dispatches the
    task in a FRESH session with the judge's blocking findings + operator note injected into
    the framing (`retry_feedback`); the old workspace is kept (`deliverable.md` →
    `deliverable.v1.md`).

## 4. Data model changes (additive only, via `scripts/migrate_real_agents.py`)

```
tasks    + session_id TEXT, dispatch_state TEXT DEFAULT 'none', domain TEXT,
           specialist TEXT, high_stakes INTEGER DEFAULT 0, budget_tokens INTEGER,
           tokens_used INTEGER DEFAULT 0, workspace_path TEXT, result_summary TEXT,
           rubric_score TEXT, learn_section TEXT, dispatch_error TEXT,
           judge_verdict TEXT, judge_output TEXT, judge_ts REAL, retry_feedback TEXT
agents   + (config JSON gains auto_claim; status set gains 'retired')
NEW      dispatches(id, task_id, agent_id, session_id, started_at, ended_at, state,
           tokens_in, tokens_out, error)
settings + dispatch.enabled, dispatch.default_task_budget, dispatch.daily_cap,
           dispatch.quota_backoff_until, judge.cmd
```

`dispatch_state` lifecycle: `none → queued → dispatching → streaming → finalizing →
(completed | failed | blocked_budget | blocked_quota | awaiting_approval)`. It is a badge on
the card, orthogonal to the kanban column — the board's columns/statuses do not change.

**Migration script also does the cleanup** (run once, server stopped, `nexus.db.bak-<date>`
snapshot first): retire `SelfHealTest`; delete the 7 seeded demo agents (pid NULL, fake
tokens) and the 12 seeded demo tasks; archive the sim-era `activity` (21,800 rows) and
`metrics` (9,256 rows) to `nexus_archive_<date>.db` before deleting; remove `_seed_if_empty`
demo data from `database.py` (fresh installs start empty — seeding fake data is the old
world). Everything is reported by the script, nothing silent.

## 5. Files touched

| File | Change |
|---|---|
| `hermes_dispatch.py` | NEW — Hermes API client (sessions, stream, messages, health, 429 detection) |
| `worker.py` | REWRITTEN — real dispatch loop (claim → session → stream → finalize → idle) |
| `database.py` | migrations (§4), shared claim helper, seed removal |
| `server.py` | new endpoints: dispatch, retry, transcript, files, judge, feedback, retire, health/full, quota, templates, onboarding-status, settings; approval-decide drives task outcome |
| `watchdog.py` | respect `retired`; resume-aware restart (worker self-resumes, watchdog just restarts the PID) |
| `agent_manager.py` | spawn/restart pass through; retire support; drop simulated metrics for pid-NULL agents |
| `scheduler.py` | unchanged (existing contract) |
| `scripts/migrate_real_agents.py` | NEW — §4 migration + cleanup |
| `scripts/verify_real_dispatch_e2e.py` | NEW gate (§7) |
| `scripts/verify.sh` | EXTENDED (new checks incl. sim-is-dead negatives; existing 53 untouched) |
| `scripts/verify_agentic_e2e.py` | EXTENDED (retire/no-respawn, blocked states) |
| `static/app.js` / `index.html` / `style.css` | task modal fields + templates, drawer (transcript/files/judge/rubric/Learn/WIN-LESSON/retry), health card, quota banner, onboarding widget; `?v=N` bumps; JARVIS blocks byte-identical |
| `templates.json` | NEW — task templates |
| `README.md`, `CLAUDE.md`, `docs/` | architecture + endpoint docs |
| `~/knowledge/MANUAL.md` | §Nexus rewritten for the new flow (plain language + German quick-guide addition) |

Frontend hard contracts preserved (from the memory file): function names
`viewAgentic`/`renderJarvisView`/`loadAgenticData`, `claimed_by` string, `#apprBadge`,
`.agentic-row`, `#jobModal/#jbName/#jbCron/#jbAction`, `a.nav-item[data-view=…]`, Agentic
card h3 texts, no "three" in index.html, tick() patches in place under `uiLocked()`.

## 6. Out of scope (explicit)

- Auth systems, multi-user accounts, cloud deploys, WebSocket rewrites of the polling model.
- Any redesign of tabs that already pass their gates; ANY change to the JARVIS blocks.
- Changes to Hermes source or `~/.hermes/config.yaml` (none are needed).
- A bridge to the Hermes kanban (retired instead — decision §0).
- Multi-turn interactive conversations with a dispatched task (one dispatch turn + resume
  turns; a "chat with this task" UI is a future mission).
- Parallel multi-task execution per lane (one task at a time per lane; scale by adding lanes).
- Worktree changes: the existing git-worktree isolation stays as-is (it guards *coding*
  tasks; deliverable tasks use workspaces).

## 7. Verification (exact commands, all must pass at every stage boundary)

Existing gates — extended, never weakened:
```
bash scripts/verify.sh                                  # 53 checks + new ones
.venv/bin/python scripts/verify_agentic_e2e.py          # 30 checks + new ones
.venv/bin/python scripts/verify_agentic_playwright.py   # 11 checks
.venv/bin/python scripts/verify_v3_ui.py                # 24 checks
.venv/bin/python scripts/verify_v3_interactions.py      # 24 checks
.venv/bin/python scripts/screenshot_all_tabs.py <stage> # all tabs, zero console errors
.venv/bin/python scripts/verify_jarvis_e2e.py           # JARVIS untouched proof (+ git diff of its blocks = empty)
```

New gate `scripts/verify_real_dispatch_e2e.py` (needs nexus server + hermes-gateway up;
uses the trivial prompt "Reply with exactly: OK" so a full run costs ~a few hundred tokens):
1. Create task via API (domain general, no specialist, budget default) → lane claims it
   atomically (second manual claim → 409 naming the owner).
2. `dispatch_state` reaches `streaming`; task gets an `api_*` `session_id`; that session is
   listable on the Hermes API.
3. Task completes: `deliverable.md` exists in the workspace; `tokens_used > 0`; transcript
   endpoint returns ≥2 messages; agent tokens grew by the same real amount.
4. High-stakes path with stubbed judge (`judge.cmd` → stub script): completion lands in
   `review` + approval row; judge run parses `REVISE` verdict + blocking items; reject →
   task back in `todo` with `retry_feedback`; re-approve path → `done`; badge counts correct.
5. Retire path: retire a test lane → PID gone, status `retired`, and after 25s (2+ watchdog
   sweeps) STILL retired with no new PID. (The SelfHealTest zombie stays dead forever.)
6. Resume path: kill a lane's PID mid-stream → watchdog restarts it → task finishes anyway
   (harvest or resume turn) with context preserved (same session id).
7. Quota path: set `dispatch.force_429` → next dispatch → task `blocked_quota`,
   `/api/quota` shows backoff, banner data present; clear flag → dispatch succeeds.
8. Budget path: create a task with `budget_tokens=1` → `blocked_budget`, never dispatched.

Manual demos at stage boundaries (operator checklist per the ship ritual): one REAL `cjudge`
run on a real deliverable; killing hermes-gateway turns its health light red (then restart).

## 8. Stages (each: implement → all gates green → screenshots → STOP, report + how-to-test → user approves → commit)

- **S1 — Beachhead.** `hermes_dispatch.py` + minimal schema migration + a thin manual
  dispatch path (`POST /api/tasks/{id}/dispatch` drives one task end-to-end from an
  existing agent lane) behind `dispatch.enabled=0` default-off. Sim untouched. Draft of the
  new gate covering steps 1–3.
- **S2 — Kill the sim.** worker.py rewrite, auto-claim loop, retired lifecycle +
  SelfHealTest retirement, resume-based self-heal, migration/cleanup script run, seed
  removal, kanban unification documented. Full new gate (steps 1–6). Flag flips to on.
- **S3 — Judgment & files.** Approval-gated deliverables, judge integration (stub + one real
  cjudge demo), workspace file endpoints + drawer UI (transcript, files, rubric, Learn),
  WIN/LESSON actions, retry-with-feedback. Gate steps as in §7.4.
- **S4 — Telemetry & polish.** Quota backoff + banner + `/api/quota` (gate step 7), budget
  states (step 8), health panel (+ manual red-light demo), templates, notifications,
  onboarding widget, quota dashboard, docs + MANUAL.md (incl. German).

## 9. Risks & mitigations

- **Long specialist runs vs stream read-timeout** → keepalives arrive every 30s; read
  timeout 120s, overall timeout none; if the stream still drops, the orphaned-run harvest
  path (R3.3) recovers the result. This is tested by gate step 6.
- **Z.ai quota exhaustion during build/test** → all e2e dispatch tests use the trivial
  prompt; the quota gate uses `dispatch.force_429` injection; if real 429s appear, pause
  dispatch testing (mission cost rule) — the backoff machinery makes that automatic.
- **Hermes update changes the API** → §1 facts list with file:line anchors; health panel
  turns red loudly; `hermes_dispatch.py` is the single place to fix.
- **Watchdog restarting a lane during a legitimately long quiet phase** → heartbeat on every
  SSE line (incl. keepalives) keeps `hb_age` < 60s while the stream is alive; if the stream
  died, a restart is exactly what we want (resume path keeps context).
- **Operators double-dispatching a task** → CAS claim + `dispatch_state` guard make the
  second dispatch a visible 409, never a duplicate session.

## 10. Definition of done

Verbatim the mission's §6 checklist — every box, including: real dispatch gate green; sim
gone; SelfHealTest retired with no respawn; ONE kanban; judge flow gate-tested + one real
cjudge demo; real tokens + budget enforcement + 429 banner demonstrated; health panel red-light
demo; all pre-existing gates at full counts (53/24/24/30/11); JARVIS diff-clean; user manually
tested and approved each stage; MANUAL.md updated (with German quick guide).
