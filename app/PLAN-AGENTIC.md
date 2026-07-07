# PLAN — Agentic OS Capabilities (v1)

> Implements SPEC-AGENTIC.md. Bite-sized tasks, exact paths, ordered by dependency.
> Primary model: GLM-5.2. Verify after each task.

## Phase 0 — Database migrations (foundation)

### Task 0.1: Extend database.py with new tables + columns
- File: `database.py`
- Add columns to tasks: `claimed_by TEXT`, `claimed_at REAL`, `verify_status TEXT DEFAULT 'unknown'`
- Add columns to agents: `worktree_path TEXT`, `worktree_branch TEXT`
- New tables: `verify_runs`, `approvals`, `memory`, `scheduled_jobs`, `messages`
- Migration pattern: mirror existing `existing_cols` ALTER pattern for new columns.
- Exit criteria: server boots, tables exist (PRAGMA check), seed data intact.

## Phase 1 — Backend: Coordination + Quality + Safety

### Task 1.1: Atomic task claiming endpoints
- File: `server.py`
- `POST /api/tasks/{id}/claim` (body: agent_id) -> SQLite CAS UPDATE + 409 on miss
- `POST /api/tasks/{id}/release` (body: agent_id) -> release claim
- Broadcast WS on claim/release.
- Exit: claim A ok, claim B -> 409.

### Task 1.2: Verify-run endpoint + task verify_status
- File: `server.py` (use subprocess + asyncio)
- `POST /api/verify` (body: command, task_id?, agent_id?, kind?) -> run, capture, persist, return
- `GET /api/verify/runs?task_id=&agent_id=&limit=`
- Failing runtime run sets task.verify_status='failing'; passing -> 'passing'.
- Exit: curl POST returns passed=true; task verify_status updated.

### Task 1.3: Approval gates
- File: `server.py`
- `POST /api/approvals`, `GET /api/approvals?status=`, `PATCH /api/approvals/{id}`
- Broadcast on create/decide.
- Exit: create pending, approve, list empty pending.

## Phase 2 — Backend: Resilience + Isolation + Memory

### Task 2.1: Self-healing watchdog module + thread
- File: `watchdog.py` (new) + wire into server startup
- Detect dead PID -> restart; detect stale heartbeat -> mark stuck/restart; enforce
  max_tasks recycle; enforce max_tokens cap -> 'cost_capped'.
- `GET /api/watchdog/status`
- Exit: kill agent PID -> restarted within ~10s, warn logged.

### Task 2.2: Git worktree isolation
- File: `agent_manager.py` (extend spawn_agent) + `worktree.py` (new helper)
- spawn(worktree=true, repo=...) -> create worktree+branch, store path/branch.
- stop_agent / delete_agent -> cleanup with dirty-check.
- Exit: spawn w/ worktree -> dir+branch exist; delete -> cleaned.

### Task 2.3: Agent memory endpoints
- File: `server.py`
- `POST/GET/DELETE /api/agents/{id}/memory`, `GET /api/agents/{id}/memory/context`
- Exit: CRUD round-trip works.

## Phase 3 — Backend: Automation + Cost + Comms

### Task 3.1: Cron scheduler
- File: `scheduler.py` (new) + wire into server startup
- minimal cron parser (*, */N, single value, comma lists)
- `GET/POST/PATCH/DELETE /api/scheduler`
- Exit: job with '*/1 * * * *' fires within ~70s.

### Task 3.2: Cost guardrails
- File: `server.py` + watchdog integration
- `GET /api/agents/{id}/cost` (tokens, pct of cap, projected_usd)
- Global cost in /api/stats.
- Exit: cost endpoint returns projection; cap enforced by watchdog.

### Task 3.3: Inter-agent messaging
- File: `server.py`
- `POST /api/agents/{id}/message`, `GET /api/agents/{id}/messages`
- Exit: message round-trip works.

## Phase 4 — Frontend

### Task 4.1: Agentic view
- File: `static/app.js` + `static/index.html` (nav item)
- Sections: verify runs, pending approvals (approve/reject), watchdog status,
  scheduler jobs (create/toggle/delete), cost summary, messages, memory browser.
- Exit: renders live data; approve button works.

### Task 4.2: Enhanced kanban cards
- File: `static/app.js` (viewKanban)
- Show claimed_by, verify_status badge, claim button.
- Exit: claim from UI moves card to in_progress, owner shown.

## Phase 5 — Verify & Document

### Task 5.1: Update verify.sh + runtime test
- Add checks for all new endpoints + new functions.
- Runtime: scripts/verify_agentic_e2e.py exercises claim/verify/approval/scheduler.
- Exit: both gates green.

### Task 5.2: Update CLAUDE.md/AGENTS.md
- Document new commands, endpoints, tables.
- Exit: docs accurate.

## Notes
- Commit after each task. Pre-commit gate (verify.sh) must pass before each commit.
- All AI models free/local. Primary coding via GLM-5.2.
