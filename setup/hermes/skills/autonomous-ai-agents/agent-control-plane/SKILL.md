---
name: agent-control-plane
description: "Build a self-contained agent control plane / fleet-OS — the platform layer that manages, coordinates, isolates, heals, and observes a fleet of autonomous agents. FastAPI + SQLite + vanilla JS, zero external infra. Covers the 5-layer orchestration stack (Runtime, Isolation, Communication, Coordination, Observability), atomic task claiming, self-healing watchdog, approval gates, cost guardrails, scheduling, and the pitfalls (signal-stealing between background loops, restart-preserving-ID) that bite when you build one."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agent-os, control-plane, fleet-management, orchestration, self-healing, task-claiming, fastapi, sqlite, watchdog, multi-agent]
    related_skills: [web-dashboard-apps, agentic-coding-harness, runtime-verification]
---

# Agent Control Plane

Build the platform layer that turns a set of agent processes into a managed fleet —
the thing amux, SuperAGI, and Microsoft Agent Framework are. This is NOT the harness
that gates a single coding agent's output (that's `agentic-coding-harness`), and NOT
the dashboard stack (that's `web-dashboard-apps`). This is the OS that *runs the agents*:
spawning, claiming work, healing crashes, isolating parallel work, approving sensitive
actions, and observing cost/health.

## When To Use

- User asks to build an "agent OS", "control plane", "fleet manager", or "orchestrator" for agents
- A dashboard/OS project needs multi-agent coordination, self-healing, isolation, or approval gates
- User wants parallel agents to share a task queue without stomping each other
- You are extending an existing agent OS (Nexus, Paperclip) with orchestration features
- The deliverable is platform infrastructure for autonomous agents, not a single agent or a static dashboard

## When NOT To Use

- Gating one coding agent's output (spec→verify loop) → `agentic-coding-harness`
- Building the FastAPI+vanilla-JS dashboard UI/stack itself → `web-dashboard-apps`
- Running one agent via a CLI delegation tool → `claude-code` / `codex` / `opencode`
- A static monitoring dashboard with no agent lifecycle → `web-dashboard-apps`

## The 5-layer orchestration stack (the consensus model)

Every mature agent control plane implements these layers. Use this as your feature
checklist — a gap in any layer is a real functional gap, not a nice-to-have.

```
Layer 5: OBSERVABILITY   monitoring, cost tracking, health checks, dashboards, activity feed
Layer 4: COORDINATION    task boards, ATOMIC claiming, conflict resolution, handoffs
Layer 3: COMMUNICATION   inter-agent REST/messaging, MCP, shared filesystem, @mentions
Layer 2: ISOLATION       git worktrees, branches, containers, sandboxes (agents must not stomp)
Layer 1: RUNTIME         real OS subprocesses (not simulations), tmux/terminal sessions, containers
```

(Source: amux's architecture, corroborated by the 2026 orchestration survey. See
`references/competitive-landscape.md` for the full tool map and which products own which layers.)

## The canonical capability set (what to build)

Map each layer to a concrete feature. These are the features the research consensus
converges on, and the ones the Nexus Agent OS v1 implements:

| Layer | Feature | How (minimal, no external deps) |
|-------|---------|---------------------------------|
| Coordination | **Atomic task claiming** | SQLite CAS: `UPDATE ... SET claimed_by=? WHERE id=? AND status IN ('backlog','todo')` then verify ownership. Second claimer gets 409. No Redis/etcd needed. |
| Quality | **Plan-Execute-Verify loop** | `/api/verify` runs a command, captures exit code + stdout tail, persists to a `verify_runs` table. Runtime runs flip a task's `verify_status`. |
| Safety | **Approval gates** | `approvals` table (pending/approved/rejected). Agent requests permission for sensitive actions; operator decides. Nav badge shows pending count. |
| Resilience | **Self-healing watchdog** | Background thread: restart dead agents (PID gone), detect stuck (stale heartbeat), enforce cost caps. |
| Isolation | **Git worktree per agent** | `git worktree add -b session/<id> .worktrees/<id>` — shared object store, isolated working tree. Parallel agents never conflict. |
| Memory | **STM + LTS memory** | `memory` table with scopes; a `/memory/context` endpoint condenses LTS summary + recent experience for prompt injection. |
| Automation | **Cron scheduler** | `scheduled_jobs` table + minimal cron parser (`*`, `*/N`, single value, comma lists). Fires jobs whose `next_run` passed. |
| Cost | **Cost guardrails** | Per-agent `max_tokens` cap; watchdog force-sets `cost_capped` status when exceeded. `/cost` returns projected_usd. |
| Communication | **Inter-agent messaging** | `messages` table; agents discover peers via the agents table. POST/GET per-agent. |
| Integration | **Toolchain overview hub** | Live health-checked registry of every tool the fleet depends on + scanners for skills, projects, and cross-provider usage/cost. THE layer users expect and the most-visible gap when missing. See "Toolchain overview hub" below. |

## Toolchain overview hub — the integration/observability layer users demand

A control plane that manages agents but never shows you the TOOLS those agents use
(the host agent, the coding models, the local LLMs, the memory provider, the voice stack,
the infra) reads as incomplete. This is the #1 "I expected an overview" gap. Build it as
live scanners in a stdlib-only module (`tools_hub.py`) behind `GET /api/{tools,skills,
projects,usage}` endpoints, rendered as 4 SPA views.

**Tool registry (`GET /api/tools`)** — each tool is a dict {id, name, category, status,
detail, config_path}. Health-check LIVE (subprocess/HTTP/file probe), never cached. Status
vocabulary: `online` | `configured` (installed but not running) | `partial` | `offline`.
Group by category (Agent / Coding / LLM / Memory / Voice / Infra) in the UI.

**Skills scanner (`GET /api/skills`)** — recurse `~/.hermes/skills/` for every `SKILL.md`,
parse frontmatter for description, merge in usage stats from `.usage.json` (use_count,
view_count, state). Group by category. Searchable frontend.

**Projects scanner (`GET /api/projects`)** — scan the user's home for project dirs (has
.git, package.json, pyproject.toml, requirements.txt, or top-level code). Per project:
size, languages (file-extension histogram), git_branch, git_dirty, has_venv, README
description. Exclude noise dirs (.cache, node_modules, .venv, Desktop, Downloads, etc.).

**Usage/cost aggregator (`GET /api/usage`)** — aggregate token usage + estimated cost across
ALL providers (GLM via .claude-glm transcripts, Claude via .claude transcripts, Hermes via
state.db). Returns per-provider totals, 14-day timeseries, per-model breakdown, top projects.
Cache 60s (transcript parsing is ~100ms). See `references/usage-cost-aggregation.md` for the
recipe AND the two bugs that silently inflate cost 30-50x.

## Atomic task claiming — the core coordination primitive

The hard problem isn't listing tasks; it's *claiming* them without two agents grabbing
the same one. The amux pattern (proven, no external deps):

```python
@app.post("/api/tasks/{task_id}/claim")
async def claim(task_id, body):
    now = time.time()
    cur = db.execute(
        "UPDATE tasks SET status='in_progress', claimed_by=?, claimed_at=?, updated_at=? "
        "WHERE id=? AND status IN ('backlog','todo')",
        (body["agent_id"], now, now, task_id),
    )
    if cur.rowcount == 0:
        # Didn't get it — find out who did
        task = db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
        return JSONResponse(409, {"error": "taken by another agent",
                                  "owner": task.get("claimed_by")})
    return db.query_one("SELECT * FROM tasks WHERE id=?", (task_id,))
```

The `WHERE status IN ('backlog','todo')` IS the compare-and-swap condition. SQLite's
single-writer lock means only one claim succeeds. Verify ownership after to distinguish
"task gone" from "lost the race". No Redis, no distributed consensus.

## Self-healing watchdog — and the signal-stealing bug (#1 pitfall)

The watchdog must keep the fleet alive unattended: restart crashed agents, detect stuck
ones, enforce caps. But the #1 bug when you build one is **signal-stealing**:

### THE BUG (hit in Nexus v1, 2026-07-04)

A metrics-collection background thread (every 3s) checks if agent PIDs are alive. A dead
agent was silently marked `status='idle'`. The self-healing watchdog (every 10s) then
looked for `status IN ('running','busy')` — and never saw the dead agent, because the
faster metrics loop had already flipped it to `idle`. The watchdog could not heal what it
could not detect. **Two background loops on shared state, the faster one masks the
slower one's signal.**

### THE FIX

Dead agents must be marked with a *distinct, watchable* status — NOT a benign terminal
state like `idle`/`stopped`. Mark them `crashed` and have the watchdog sweep
`status IN ('running','busy','crashed')`:

```python
# agent_manager._update_agent_status() — called by the metrics loop
if not alive:
    # NOT 'idle' — that steals the watchdog's signal. Use 'crashed'.
    db.execute("UPDATE agents SET status='crashed' WHERE id=? AND pid IS NOT NULL", (a["id"],))

# watchdog.py — sweep includes the crashed state
agents = db.query_all("SELECT * FROM agents WHERE status IN ('running','busy','crashed')")
for a in agents:
    if not _is_alive(a["pid"]):
        am.restart_agent(a["id"])  # heals it
```

Generalize beyond watchdogs: **when two background loops touch the same rows, they must
agree on a signal vocabulary.** The faster loop must not resolve an ambiguous state into a
terminal one the slower loop needs to act on. Pick a distinct intermediate state
(`crashed`, `stuck`, `cost_capped`) that survives until the responsible loop processes it.

## restart_agent MUST preserve the ID (#2 pitfall)

Naive restart = `stop_agent()` then `spawn_agent()`. But `spawn_agent` mints a NEW
agent ID, leaving the original row with `pid=NULL, status='stopped'`. After a watchdog
restart, references to the old ID dangle (tasks claimed_by the old ID, memory keyed to
the old ID, the UI tracking the old ID). Restart in place:

```python
def restart_agent(agent_id):
    agent = db.query_one("SELECT * FROM agents WHERE id=?", (agent_id,))
    if agent.get("pid"):
        try: os.kill(agent["pid"], signal.SIGTERM)
        except (ProcessLookupError, PermissionError): pass
    time.sleep(0.2)
    proc = subprocess.Popen([sys.executable, WORKER_SCRIPT, agent_id, agent["name"]],
                            env={**os.environ, "NEXUS_AGENT_ID": agent_id})
    db.execute(
        "UPDATE agents SET pid=?, status='running', started_at=?, last_heartbeat=?, "
        "current_task='Restarted...' WHERE id=?",
        (proc.pid, time.time(), time.time(), agent_id),
    )
```

The worker is launched with the SAME agent_id. References stay valid. Verified live in
Nexus: a SIGKILLed agent was restarted with a new PID in 3s, same ID, `restart_count` incremented.

## Git worktree isolation (Layer 2)

Parallel agents in one working dir stomp each other (uncommitted changes, merge chaos).
A full clone per agent is wasteful. `git worktree` shares the object store, isolates the
tree — sub-second, negligible disk:

```python
def create_worktree(repo_path, agent_id):
    short = agent_id.replace("agent-","")[:8]
    branch = f"session/{short}"
    subprocess.run(["git","worktree","add","-b",branch,
                    f"{repo}/.worktrees/{short}"], check=True)
    return {"worktree_path": str(wt_path), "worktree_branch": branch}
```

Cleanup safety: **never force-remove a worktree with uncommitted changes.** Check
`git status --porcelain` first; if dirty, leave it for human review and flag it.

## Minimal cron parser (don't reach for a library)

For a scheduler, you usually only need `*`, `*/N`, single values, and comma lists. That's
~40 lines, no dependency:

```python
def _parse_field(expr, lo, hi):
    out = set()
    for part in expr.split(","):
        part = part.strip()
        if part == "*":              out.update(range(lo, hi+1))
        elif part.startswith("*/"):  out.update(range(lo, hi+1, int(part[2:])))
        elif part.isdigit():         out.add(int(part))
    return out

def next_run(cron_expr, after=None):
    base = datetime.fromtimestamp(after or time.time()).replace(second=0, microsecond=0) \
           + timedelta(minutes=1)
    for _ in range(60*24*366):  # cap 1 year
        if _matches(cron_expr, base): return base.timestamp()
        base += timedelta(minutes=1)
```

Document explicitly what you DON'T support (ranges, range-steps) so users don't get silent no-ops.

## Verification — three gates, the runtime one is non-negotiable

An agent control plane has a runtime component (subprocesses, threads, a live DB).
Static gates alone cannot catch contract drift (event-name mismatches, status-state
race conditions, restart-ID bugs). Use the `runtime-verification` discipline:

1. **Static gate** (`scripts/verify.sh`) — syntax + endpoint/function/table integrity. Fast, every edit.
2. **Runtime API gate** — HTTP test that exercises every endpoint (claim/verify/approvals/...).
3. **Runtime UI gate** (Playwright) — loads the real dashboard, asserts cards render, exercises flows from the browser, captures console errors. This is what catches frontend↔backend contract drift.

The signal-stealing bug and the restart-ID bug were both caught by the runtime API gate
(killed a PID, watched for the heal), NOT by the static gate. If you skip Layer 2, you ship
these bugs.

See `references/competitive-landscape.md` for the full survey of what amux, SuperAGI,
Microsoft Agent Framework, and the arXiv "Code as Agent Harness" taxonomy offer — use it
to scope features and to justify "we need X because every control plane has it."

See `references/usage-cost-aggregation.md` for the cross-provider token/cost aggregation
recipe (GLM + Claude + Hermes), the dedupe fix, and cache pricing.

## Pitfalls

- **SIGNAL-STEALING between background loops** — the #1 self-healing bug. See above. The faster loop must not resolve an ambiguous state into a terminal one the slower loop acts on. Use distinct intermediate states (`crashed`, `stuck`).
- **restart_agent must preserve the ID** — delete+spawn dangles references. Update in place, relaunch the worker with the same ID.
- **Atomic claim needs the WHERE condition AND ownership verify** — `cur.rowcount == 0` means either "gone" or "lost the race"; re-query to tell them apart and return a useful 409.
- **Never force-remove a dirty worktree** — `git status --porcelain` first; leave dirty ones for review.
- **Cron parser: document the unsupported subset** — silent no-ops on `1-5` or `1,3,5-7` are worse than a clear "unsupported expression" error.
- **Cost cap must be enforced, not just reported** — a `/cost` endpoint that nobody acts on is theater. The watchdog must set `cost_capped` and stop the agent.
- **USAGE AGGREGATION: dedupe transcript snapshots or overcount 30-50x.** Claude Code's transcript `.jsonl` records the SAME `message.usage` block on every `assistant` line in a turn (snapshot behavior). Summing naively reports $90,000 where the real spend is $2,550. Dedupe by `(input_tokens, output_tokens, cache_read, cache_creation, model)` per file. Separate from that: `cache_read_input_tokens` is billed at ~10% of the input rate (prompt-cache discount) and `cache_creation` at ~1.25x — pricing them at full input rate is the second overcount. (Hit in Nexus v2, 2026-07-04; both fixed, $90k→$2.5k.) Full recipe in `references/usage-cost-aggregation.md`.
- **Operational hygiene endpoints are part of the plane** — `POST /api/tasks/cleanup` (archive orphaned in_progress/review tasks with no owner) and `POST /api/agents/cleanup-test-agents` (bulk-delete stopped test spawns) keep the board honest. Agents named Alpha/Beta/Gamma are useless to the operator; provide `PATCH /api/agents/{id}/rename` and default to role-based names (Researcher, Implementer, Tester, Reviewer, DevOps, Docs).
- **Background threads must seed their own config defaults** — if the watchdog reads settings that don't exist yet, it crashes silently. Insert defaults on first loop.
- **All the web-dashboard-apps pitfalls apply** (WAL mode, thread-local DB connections, incremental DOM for charts, kill subprocesses on stop).
