# SPEC — Agentic OS Capabilities (v1)

> Spec-driven build, 2026-07-04. Treat as a client deliverable. Source of truth.
> Implements the agentic-coding harness concepts as first-class Agent OS features,
> informed by competitive research (amux, arXiv "Code as Agent Harness" survey,
> SuperAGI, Microsoft Agent Framework, Northflank/Modal sandboxing).
> The implementation must satisfy every numbered requirement.

## Context & Goal

Nexus Agent OS is a FastAPI + SQLite agent dashboard with agent fleet management,
kanban tasks, programs, monitoring, and a JARVIS interface. Yesterday we built a
professional agentic-coding harness in Hermes (spec-driven dev, verify-loop,
parallel worktrees, subagent delegation, self-correction, cost discipline, memory,
docs grounding). The goal now is to promote those concepts from "harness tricks"
into first-class, observable features OF the Agent OS itself, and to close the gaps
that competing agent-control-planes (amux, SuperAGI, Microsoft Agent Framework)
already solve: atomic task claiming, self-healing, isolation, memory, approval
gates, cost guardrails, scheduling, and inter-agent communication.

Design constraints (non-negotiable):
- Pure Python stdlib backend + vanilla JS frontend. NO new external runtime deps.
- FastAPI + SQLite (WAL). No Redis, no Postgres, no Docker, no message broker.
- SQLite CAS (compare-and-swap via WHERE-clause UPDATE) is the concurrency primitive.
- All new tables are additive migrations; existing data and endpoints are preserved.
- No build step. Frontend is vanilla JS loaded via <script>.

## Requirements (numbered, testable)

### 1. Atomic Task Claiming (Coordination layer)
1.1. An endpoint `POST /api/tasks/{id}/claim` atomically claims a task for an agent
     using SQLite CAS: the UPDATE only succeeds if status IN ('backlog','todo').
1.2. If another agent already claimed it, the endpoint returns 409 Conflict with a
     clear message naming the owning agent.
1.3. On successful claim, task status -> 'in_progress', claimed_by set, claimed_at
     set, and a WS broadcast fires so the kanban updates in real time.
1.4. `GET /api/tasks` response includes claimed_by and claimed_at for every task.
1.5. `POST /api/tasks/{id}/release` releases a claim back to 'todo' (status reset,
     claimed_by cleared) so another agent may pick it up.

### 2. Plan-Execute-Verify loop (Quality layer)
2.1. A `verify_runs` table records each verification attempt: id, task_id (nullable),
     agent_id, kind ('static'|'runtime'), command, exit_code, stdout_tail, passed,
     ts, duration_ms.
2.2. An endpoint `POST /api/verify` runs a command in a subprocess, captures exit
     code + tail of stdout/stderr, persists a verify_run row, and returns the result.
2.3. An endpoint `GET /api/verify/runs` lists recent verify runs (filterable by
     task_id and agent_id).
2.4. Tasks gain a `verify_status` column ('unknown'|'passing'|'failing'|'blocked').
2.5. A failing runtime verify_run against a task sets that task's verify_status to
     'failing'; a passing runtime run sets it to 'passing'.

### 3. Approval Gates (Safety layer)
3.1. An `approvals` table: id, agent_id, action_type, description, payload (JSON),
     status ('pending'|'approved'|'rejected'|'expired'), requested_at,
     decided_at, decided_by, risk_level.
3.2. An endpoint `POST /api/approvals` creates a pending approval request (an agent
     asking permission for a sensitive action: deploy, sudo, destructive delete,
     external send).
3.3. An endpoint `PATCH /api/approvals/{id}` decides (approve/reject) a pending
     request, recording decided_by.
3.4. `GET /api/approvals?status=pending` lists approvals by status.
3.5. Pending approvals appear in the UI with Approve/Reject buttons; the count of
     pending approvals shows as a badge in the nav.

### 4. Self-Healing Watchdog (Resilience layer)
4.1. A background watchdog thread runs every N seconds (configurable, default 10s).
4.2. It detects dead agents: a running/busy agent whose PID no longer exists is
     auto-restarted (spawn a fresh worker), and the restart is logged to activity
     as level 'warn'.
4.3. It detects stuck agents: no heartbeat for a configurable stale_threshold
     (default 60s) while status is running/busy -> status set to 'stuck', a 'warn'
     activity logged, and the agent auto-restarted if restart_on_stuck is enabled.
4.4. It enforces a per-agent max_tasks before forced recycle (configurable, 0=off).
4.5. Watchdog decisions are visible via `GET /api/watchdog/status` (config + recent
     actions) and in the activity feed.

### 5. Git Worktree Isolation (Isolation layer)
5.1. Spawning an agent with `worktree=true` creates an isolated git worktree + branch
     for the agent's program repo, so parallel agents never stomp each other's files.
5.2. The worktree path and branch name are stored on the agent row (worktree_path,
     worktree_branch).
5.3. Stopping/removing the agent cleans up the worktree (git worktree remove) if it
     has no uncommitted changes; if it has changes, it is left for review and flagged.
5.4. `GET /api/agents/{id}` includes worktree info, and a file-conflict warning is
     shown when two agents share a repo+branch.

### 6. Agent Memory (Memory layer)
6.1. A `memory` table: id, agent_id, scope ('stm'|'lts'|'experience'|'longterm'),
     kind, content, embedding_b64 (nullable), created_at, expires_at (nullable),
     source.
6.2. `POST /api/agents/{id}/memory` adds a memory entry (the agent recording a fact,
     lesson, or reflection).
6.3. `GET /api/agents/{id}/memory?scope=` lists entries, most-recent-first, with a
     soft cap (default 100).
6.4. `DELETE /api/agents/{id}/memory/{mid}` forgets a specific memory.
6.5. A `GET /api/agents/{id}/memory/context` endpoint returns a condensed context
     blob (LTS summary + recent experience) suitable for prepending to an agent's
     prompt — the STM/LTS two-part model from SuperAGI.

### 7. Cron Scheduler (Automation layer)
7.1. A `scheduled_jobs` table: id, name, cron_expr, agent_id, action, last_run,
     next_run, enabled, run_count, last_status.
7.2. A scheduler thread evaluates jobs whose next_run has passed and triggers them
     (sets agent current_task / posts a message / runs a command), recording results.
7.3. `GET /api/scheduler` lists jobs; `POST /api/scheduler` creates; `PATCH` toggles
     enable/disable; `DELETE` removes.
7.4. Creating a job computes next_run from a minimal cron parser (minute/hour/dom/
     month/dow; '*' supported, '*/N' supported, single value supported).

### 8. Cost Guardrails (Cost layer)
8.1. Agents gain config fields max_tokens (hard cap) and max_supersteps (reasoning
     loop cap), stored in the agent config JSON.
8.2. `GET /api/agents/{id}/cost` returns tokens_in + tokens_out + total + pct of cap
     + projected_usd (using a configurable per-1M-token price).
8.3. When an agent's total tokens exceed max_tokens, its status is force-set to
     'cost_capped' by the watchdog and a 'warn' activity is logged.
8.4. Global system stats include total projected cost (sum across agents).

### 9. Inter-Agent Communication (Communication layer)
9.1. A `messages` table: id, from_agent, to_agent, content, ts, read.
9.2. `POST /api/agents/{id}/message` sends a message from one agent to another
     (peer discovery via the agents table).
9.3. `GET /api/agents/{id}/messages?direction=` lists sent/received, newest-first.
9.4. Unread inbound messages surface in the agent detail view.

### 10. UI: Agentic View + Enhanced Kanban
10.1. A new "Agentic" nav item renders a dashboard of the agentic capabilities:
      active verify runs, pending approvals, watchdog status, scheduler jobs,
      cost summary, inter-agent messages, agent memory browser.
10.2. Kanban cards show claimed_by, verify_status, and a claim button for agents.
10.3. All new endpoints are exercised by the frontend.

## Out of Scope (explicitly)
- A real vector database (embedding_b64 column is a placeholder for future vector
  search; we store content + keyword match only for v1).
- MicroVM / gVisor sandboxing (we use subprocess isolation + git worktrees only;
  full container sandboxing is documented as a future direction).
- The 5 orchestration patterns as first-class UI (the primitives — claim,
  worktree, message, verify — support all five; a pattern-picker UI is future).
- MCP server hosting (we consume Hermes as the LLM; we do not host MCP ourselves).
- Changing the JARVIS voice/lip-sync flow.

## Verification (the exact checks that prove it works)
1. `bash scripts/verify.sh` passes including all new endpoints + functions.
2. `curl POST /api/tasks/{id}/claim` succeeds for agent A; a second call by agent B
   returns 409 with the owner named.
3. `curl POST /api/verify -d '{"command":"python -c \"print(1)\""}'` returns a row
   with passed=true, exit_code=0; the run appears in GET /api/verify/runs.
4. `curl POST /api/approvals` creates a pending request; PATCH approves it; the nav
   badge decrements.
5. Kill a spawned agent's PID; within ~10s the watchdog restarts it and logs a warn.
6. Spawn an agent with worktree=true against a git repo; the worktree dir + branch
   exist on disk and are recorded on the agent row.
7. POST a memory entry; GET returns it; DELETE removes it.
8. Create a scheduler job with cron '*/1 * * * *'; within ~70s it fires (run_count
   increments).
9. Set an agent max_tokens low; the watchdog caps it once exceeded.
10. POST a message agent->agent; GET lists it.
11. The Agentic view renders and shows live data from all subsystems.

## Risks / Open Questions
- SQLite CAS under high concurrency: mitigated by WAL + short transactions; the
  claim() does UPDATE...WHERE status IN (...) then verifies ownership — the proven
  amux pattern.
- Watchdog restarting agents that are legitimately long-running but quiet: mitigated
  by heartbeat-based stuck detection (the worker already heartbeats every 2s) and a
  generous stale_threshold default.
- Cron parser correctness: v1 supports the common subset (*, */N, single value);
  complex expressions (ranges, lists) are documented as unsupported in v1.
- Worktree cleanup safety: never force-remove a worktree with uncommitted changes.
