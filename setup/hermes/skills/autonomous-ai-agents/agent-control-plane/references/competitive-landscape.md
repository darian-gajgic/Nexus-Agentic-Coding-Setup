# Agent Control Plane — Competitive Landscape (2026)

Condensed research for scoping an agent control plane / fleet-OS. Use this to answer
"what should our OS have?" with evidence, and to avoid rebuilding what others solved.
Sources: amux (mixpeek/amux), arXiv "Code as Agent Harness" survey (2605.18747),
LangChain frameworks comparison, SuperAGI (DataCamp), Northflank/Modal sandboxing guides.

## The standout reference implementation: amux

Single-file Python (stdlib `http.server` + SQLite + tmux). MIT + Commons Clause.
The closest analogue to a self-contained, zero-dep agent control plane. Owns all 5 layers.

Key patterns worth copying directly:
- **Atomic task claiming via SQLite CAS** — `UPDATE ... WHERE status IN ('todo','backlog')`
  + ownership verify. No Redis, no etcd, no distributed consensus. (Nexus v1 adopted this verbatim.)
- **Self-healing watchdog** — monitors context %, auto-compacts, restarts on corruption,
  replays last message, detects stuck agents (no-output timeout), handles rate-limit prompts
  fleet-wide (parses reset time, parks all sessions, resumes when the window opens).
- **Git worktree isolation** — `session/<id>` branches; shared object store, isolated trees.
- **Channels** — 1:1 inter-session messaging with @mentions for real-time agent coordination.
- **Notes** — markdown docs agents read/write/reference across sessions (shared global memory).
- **Scheduler** — named cron-style recurring jobs with management UI.

amux's "why amux?" table is a precise feature-gap checklist: crashes-at-3am → watchdog;
can't-monitor-10-sessions → dashboard; duplicate-work → atomic board; no-phone-access →
mobile PWA; no-coordination → REST API; no-shared-context → Notes/Channels; no-automation
→ scheduler.

## SuperAGI — memory + approval model

- **Two-part memory**: STM = rolling window by token limit; LTS = condensed summary of
  context outside the STM window. Together = "Agent Summary" fed to each reasoning step.
  Vector DB (Weaviate/Pinecone/Qdrant) holds knowledge embeddings separately. (Nexus v1's
  `/memory/context` endpoint implements the STM+LTS condensation.)
- **Action Console** — human-in-the-loop. In restricted-permission mode, agents PAUSE before
  critical actions (send email, write file) and wait for approval. This is the approval-gate pattern.

## Microsoft Agent Framework RC (Feb 2026 GA)

- **WorkflowBuilder** — strongly-typed DAG: sequential, fan-out (parallel), conditional,
  handoff. Compile-time type-safe. Replaces AutoGen's unpredictable group-chat loops.
- **CostGuardMiddleware** — `workflow.with_max_supersteps(12).add_middleware(
  CostGuardMiddleware(max_usd=2.0, alert_at=1.5))`. Hard-cap reasoning cycles AND dollars.
  This is the formal version of cost guardrails.
- **ChatClient abstraction** — swap Azure/Anthropic/Ollama/Bedrock in one config line.
- **Guardrails when deployed via AI Foundry** — task-adherence, PII protection,
  prompt-injection defenses.
- **Declarative YAML agent config** for version-controlled deployments.

## arXiv "Code as Agent Harness" (2605.18747) — the taxonomy

Five harness mechanism categories. When scoping a control plane, map your features to these:

1. **Planning** — externalize goals into decompositions, structural constraints, search
   trajectories, workflow orchestration. (CodePlan dependency-graph, MapCoder map-code-test.)
2. **Memory & context engineering**:
   - *Working memory* — SWE-agent (repair trajectory), CodeMem (budgeted slots).
   - *Semantic memory* — AutoCodeRover, RepoCoder (repo structure retrieval).
   - *Experiential* — MemGovern, ExpeL (reflection replay), Reflexion (verbal feedback memory).
   - *Long-term* — MemCoder (intent→code mappings), TALM (vector retrieval of past episodes).
   - *Multi-agent* — MIRIX (cross-agent routing), ChatDev (phase-level context passing).
   - *Compaction* — LongCodeZip, SWE-Pruner (task-aware pruning).
3. **Tool usage** — governed executable interfaces: APIs, repos, terminals, sandboxes,
   verification tools, orchestrators.
4. **Plan-Execute-Verify (PEV) control loop** — plans as contracts, sandboxed execution,
   verification via deterministic sensors + human-review gates. Decide accept/revise/escalate/
   rollback. (OpenHands full PEV, Self-Debugging, AgentCoder coder-tester-executor,
   VeriGuard, LiteLLM permission gateway.)
5. **Harness engineering** — deep telemetry, evolution agents, replay-based eval, governed
   harness mutation.

The PEV loop (category 4) is the formal grounding for the verify-gate pattern from
`agentic-coding-harness` and the `/api/verify` endpoint in a control plane.

## Sandboxing / isolation (Northflank, Modal, Daytona, E2B)

- **microVM (Kata/gVisor)** — hardware-level isolation for untrusted code. Overkill for v1.
- **Hardened containers** (seccomp + AppArmor + capability drop) — only for trusted, reviewed code.
- **Resource limits** — CPU/memory/disk/network caps prevent resource exhaustion (intentional or not).
- **No-network code execution** — for generated code, strip network to prevent exfil.
- Daytona (cloud dev sandbox), E2B (code-browser sandbox), Modal (50k+ concurrent sessions,
  fast cold starts, memory snapshots).

For a v1 control plane on a single host: subprocess isolation + git worktrees is the floor.
Full microVM sandboxing is a documented future direction, not a v1 requirement.

## The 5 orchestration patterns (scope which your OS supports)

| Pattern | Agents | Best for | Quality control |
|---------|--------|----------|-----------------|
| Solo | 1 | simple tasks | none (self-review) |
| Parallel Workers | 2–50+ | embarrassingly parallel | post-hoc review |
| Pipeline | 3–6 | quality-critical (plan→implement→test→review) | stage gates |
| Hub & Spoke | 4–11 | cross-cutting, architectural | coordinator review |
| Swarm | 5–50+ | large loosely-coupled | peer review / gates |

Note: a control plane doesn't need a pattern-picker UI in v1. The primitives (claim,
worktree, message, verify) SUPPORT all five; a pattern-picker is a future layer on top.

## Feature-gap checklist (run this against your OS)

Against the consensus, a v1 control plane should have:
- [ ] Atomic task claiming (SQLite CAS)
- [ ] Self-healing watchdog (dead + stuck detection, cost caps)
- [ ] Git worktree isolation per agent
- [ ] Approval gates for sensitive actions
- [ ] Agent memory (STM + LTS at minimum)
- [ ] Cost guardrails (enforced, not just reported)
- [ ] Cron scheduler
- [ ] Inter-agent messaging
- [ ] Observability dashboard (live status, cost, health, activity feed)
- [ ] PEV verify loop (the OS-level verify-gate)

Anything unchecked is a gap a competing product already fills.

## The overview/toolchain-hub layer (the #1 user-visible gap, 2026-07)

The 9 capabilities above are the fleet layer. The layer users COMPLAIN about when missing
is the integration/overview layer: a live health-checked registry of every tool the fleet
depends on (the host agent, coding models, local LLMs, memory provider, voice stack, infra)
+ scanners for skills, projects, and cross-provider usage/cost. Without it, an OS that has
all 9 fleet capabilities still reads as "3/10, missing the overview" to the operator.

Observed 2026-07-04 (github.com/topics/agent-os scan): the closest peers ALL surface this:
- **modimihir07/agentic-os** — 21 dashboard pages: Skills Hub, Cost Analytics, Goals,
  Journal, Agent Health, Smart Router, Session Replay, Error Dashboard, Circuit Breaker.
  Closest analogue to a FastAPI+vanilla-JS control plane with an overview hub.
- **OpenHands "Agent Control Plane"** — every token tracked per session/repo/user with
  custom labels for cost-ROI slicing. The token-economics gold standard.
- **KAOS (kronos-agent-os)** — 6-tier memory, MCP gateway, pluggable analytics (Zabbix,
  Grafana, Sentry, Linear), daily-pulse + weekly-business-report automations.
- **Cognithor OS** — 19 LLM providers, 18 channels, 145 MCP tools, Agent Packs marketplace.

Build order when upgrading an existing control plane: tools registry → skills scanner →
projects scanner → usage/cost aggregator (see `usage-cost-aggregation.md` for the recipe
and the two overcount bugs). Each is one `GET /api/<x>` endpoint + one SPA view.
