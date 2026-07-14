# Hermes for Big-Client-Project Agentic Coding — Research & Plan (2026-07-07)

Goal: maximum productivity + maximum automation for agentic coding on large,
long-lived client repos — via Hermes-side improvements, without disturbing the
working stack (guardian-managed, minimal core-mods).

Grounding: Sourcegraph "Agentic Coding in 2026" (Big-Code practices), Claude
Code best-practices corpus (context management, CLAUDE.md, subagents), plus a
live audit of this Hermes install.

## The audit findings (this machine, today)

| # | Finding | Impact on big repos |
|---|---------|---------------------|
| A | Dev specialists (code-implementer, tech-lead-orchestrator, debugger, code-reviewer, acceptance-verifier) run with `tools: [file, terminal]` ONLY | They navigate 500-file repos by grep/cat — the most token-hungry, least precise method. Serena (LSP: find-symbol, references, rename) and context7 (current library docs) are INSTALLED and running but unreachable for exactly the agents that need them |
| B | Hermes's per-project instruction files (`.hermes.md` > `AGENTS.md` > `CLAUDE.md`, prompt_builder) never fire | Gateway/API sessions default cwd=$HOME, so no session ever loads a repo's conventions. The single most consensus-backed practice in the field (CLAUDE.md/AGENTS.md) is wired but dormant |
| C | `session_reset.mode: none` — interactive sessions grow forever (measured p50 83k, max 236k resident) | The documented "agent dumb zone": performance degrades past ~60-70% context. Long project sessions rot. (Nexus-dispatched tasks are immune — fresh session per task) |
| D | No repo onboarding artifact per client project | Every task re-discovers architecture from scratch; no repo map, no conventions doc, no verify commands |
| E | Verification lacks the Big-Code rule: "search for other usages of every symbol you touched" | The classic 80%-done failure: local change passes its tests, breaks a caller three layers away |
| F | Specialist router inert in CLI (fires only on messaging dispatch) — remediation P3 | Interactive coding sessions don't auto-route to specialists |

## The plan (priority order; each step independent)

### 1. Give the dev specialists their tools back (30 min, highest ROI)
Add `serena` + `context7` MCP toolsets to the five dev specialists' `tools:`
frontmatter, and add a "navigation discipline" block to their playbooks:
- Locate code by SYMBOL (serena find-symbol/references), not by reading files
  end-to-end; read only the definitions you need.
- Ground library usage in context7 docs, never training-data memory, for any
  dependency question.
Why (research): "Favor exact symbol references over embedding/approximate
retrieval — on Big Code approximate retrieval returns plausible results that
miss cross-cutting impact" (Sourcegraph). LSP = deterministic retrieval.
Note: specialists' tool allowlists are enforced at delegation; verify MCP
toolset names resolve for children (inherit_mcp_toolsets).

### 2. Activate per-repo AGENTS.md loading (1-2 h)
- For every client repo: create `AGENTS.md` (conventions, architecture map,
  commands: test/build/lint, "danger zones"). Auto-generate via an
  "Onboard repo" task template (tech-lead-orchestrator, read-only) and keep it
  updated by the pipeline (fix/review tasks append decisions).
- Pin session cwd to the repo so prompt_builder loads it: CLI = launch hermes
  from the repo dir; API sessions = pass cwd at create (verify api_server
  create-session accepts cwd; if not, ONE small guardian-tracked core-mod).
Why: CLAUDE.md/AGENTS.md-style project memory is the consensus practice across
Claude Code/Codex/Cursor ecosystems; Hermes already implements the loader.
KEEP IT SHORT: "if the instructions file is too long the model ignores half of
it" — prune ruthlessly, link to deeper docs (progressive disclosure).

### 3. Big-Code verification rules (1 h, playbook edits only)
Append to code-implementer + acceptance-verifier playbooks and the
development-workflow skill:
- BLAST RADIUS FIRST: before changing a symbol, list its references
  (serena) and name affected layers in the plan.
- DONE MEANS: full test suite green + "search the codebase for any other
  usage of the symbols you touched; anything you never opened = not done".
- Gate on the repo's OWN commands (from AGENTS.md), never generic checks.
- Schema/stateful migrations always escalate to the human (agents don't
  understand data gravity).

### 4. Session hygiene for long projects (30 min, config)
- `session_reset.mode: idle` (per remediation C2) so stale interactive
  sessions reset instead of rotting in the dumb zone.
- Compaction guidance in SOUL.md: on compression, always preserve the list of
  modified files + the repo's test commands (mirrors the compaction-survival
  practice).
- Habit: one Hermes session per work item; /reset between items.

### 5. Parallel work isolation (already planned Nexus Phase 1; Hermes side is ready)
Git worktree per task + branch `task/<id>`; subagents/parallel lanes never
share a checkout ("delegate independent slices to parallel agents;
sub-agent results return as summaries — context isolation is the point").
Hermes needs nothing new here: delegation already summarizes children;
worktree.py exists Nexus-side.

### 6. Specialist router on pre_llm_call (remediation P3, ~2 h, plugin edit)
Auto-route interactive coding requests to the right specialist in the CLI,
not only via messaging dispatch. Guardian-track the plugin change.

### 7. Per-client isolation (remediation M3 — prerequisite for real client work)
Per-client mem0 scoping (run_id/agent_id), per-repo env, session titles carry
the client tag. Do BEFORE the first paying client's code enters the system.

## Explicit non-goals (researched and rejected)
- Embedding/vector indexing of client repos: approximate retrieval underperforms
  deterministic LSP/search on Big Code and adds an index to maintain.
- Merging Nexus↔Hermes either direction (see 2026-07-07 discussion): the
  control-plane/runtime split is the SOTA shape and is what makes restarts,
  updates and self-heal safe.
- A "always check public APIs" router — evaluated separately, rejected;
  curated skill shipped instead.

## Sources
- https://sourcegraph.com/blog/agentic-coding (Big-Code practices: deterministic
  retrieval, blast radius, symbol-usage verification, CI gating, sub-agent
  orchestration, migrations at scale)
- https://code.claude.com/docs/en/best-practices + community corpus (CLAUDE.md
  discipline, context dumb-zone, subagents for context isolation, plan mode)
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
  (skills/progressive disclosure — already applied to this stack)
- Live audit of ~/.hermes (specialist toolsets, prompt_builder project files,
  session_reset, delegation config) 2026-07-07.
