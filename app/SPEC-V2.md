# SPEC — Nexus Agent OS v2 (Tools Hub + Skills + Projects + Usage)

> Upgrades Nexus from 3/10 → 9/10. Adds the overview/configuration hub the user expects.
> Builds ON TOP of v1 (the 9 agentic capabilities are preserved, not replaced).

## Problem (user-stated, 2026-07-04)
The OS has backend agentic features (claim/verify/approvals/watchdog/worktrees/memory/scheduler/cost/messaging)
but is MISSING the actual "overview of all my tools" that makes it a control hub:
- No Tools overview / config hub (Paperclip, Supermemory, Ollama, GLM, Claude, Hermes itself)
- No Skills overview (the 17 Hermes skill categories)
- No Projects overview (the 20+ dirs in /home/sinep)
- No Usage overview (GLM-5.2 + Claude token/cost data that exists in transcripts)
- Kanban has stale orphaned tasks; agents named with Greek letters (Alpha/Beta/Eta/Zeta)

## Goal
Nexus becomes the single dashboard for the user's entire AI toolchain:
1. SEE every tool, skill, project, and usage metric in one place.
2. CONFIGURE tools from the dashboard (status, health, key config knobs).
3. Clean operational state (no stale tasks, role-named agents).

## Design constraints (unchanged from v1)
- Pure Python stdlib backend + vanilla JS frontend. No new runtime deps.
- FastAPI + SQLite (WAL). No external services.
- All new endpoints are additive; existing v1 endpoints preserved.

## Requirements (numbered, testable)

### 11. Tools Hub (overview + status + config) — Coordination/Integration layer
11.1. A `tools` registry enumerates every integrated tool the user has:
      - Hermes Agent (the host agent) — version, model, gateway platforms, skills count
      - GLM-5.2 via Z.AI (primary coding model) — CLI path, transcripts count
      - Claude Code (secondary) — config dir, transcripts count
      - Ollama (local models) — running status, model list
      - Paperclip (agent control plane) — install path, running status
      - Supermemory (Hermes memory provider) — store count
      - Wav2Lip (neural avatar) — model path, CUDA status
11.2. `GET /api/tools` returns the registry: each tool has id, name, category, status
      (online/offline/beta), health detail, key metrics, config path.
11.3. Each tool is health-checked live (subprocess/HTTP/file probe), NOT cached.
11.4. The UI groups tools by category (LLM / Coding / Memory / Voice / Infra) and shows
      a status grid (green=online, yellow=partial, red=offline, blue=configured-not-running).
11.5. Clicking a tool opens a detail panel with its config file path + key settings (read-only
      for v2; config editing is v3).

### 12. Skills Overview (what the agent can do)
12.1. `GET /api/skills` scans `~/.hermes/skills/` recursively, reading every `SKILL.md`.
12.2. Returns categories with child skills: name, description (from frontmatter), file path,
      use_count + view_count (merged from `~/.hermes/skills/.usage.json`), state (active/archived).
12.3. The UI renders a searchable/filterable grid grouped by category, with usage bars.
12.4. Search filters by name/description across all skills (client-side for v2).

### 13. Projects Overview (what's on disk)
13.1. `GET /api/projects` scans top-level directories under `/home/sinep/` that look like projects
      (contain .git, package.json, pyproject.toml, requirements.txt, or *.py/*.js files).
13.2. For each project returns: name, path, size_bytes, language(s), git_branch, git_dirty
      (uncommitted changes), last_modified, has_venv, description (from README.md first line
      if present, else .git/config remote url).
13.3. Excludes noise: .cache, node_modules, .venv, snap, Desktop, Downloads, Public, Templates,
      Music, Videos, Pictures, Documents.
13.4. The UI renders a sortable table/grid; clicking opens the project dir in a detail panel
      with git status + quick stats.

### 14. Usage & Cost Overview (token economics)
14.1. `GET /api/usage` aggregates token usage across THREE sources:
      - GLM-5.2: parse `~/.claude-glm/projects/*/*.jsonl` (message.usage.input_tokens/output_tokens,
        message.model, timestamp).
      - Claude: parse `~/.claude/projects/*/*.jsonl` (same structure).
      - Hermes: query `~/.hermes/state.db` messages.token_count grouped by sessions.model.
14.2. Returns: per-provider totals (input_tokens, output_tokens, sessions, est_cost_usd),
      a 14-day timeseries (tokens per day per provider), per-model breakdown, top-5 projects by tokens.
14.3. Cost is computed via a configurable price table (GLM ~$0.50/1M, Claude ~$3/1M in / $15/1M out
      for Sonnet; Ollama=$0). All prices configurable via settings.
14.4. The UI renders: provider summary cards, a stacked-area Chart.js timeseries, a model breakdown
      donut, a per-project bar chart.
14.5. Parsing is cached for 60s (transcript parsing is ~100ms; avoid re-parse every poll).

### 15. Kanban Cleanup + Agent Naming (data hygiene)
15.1. Stale tasks (in_progress/review with no claimed_by for >48h) are bulk-archivable via
      `POST /api/tasks/cleanup` which sets them to 'backlog' and logs an activity.
15.2. The kanban "review" column tasks with no owner move to 'todo'; "in_progress" tasks with no
      owner move to 'backlog' (they were never actually started).
15.3. A `POST /api/agents/rename` endpoint renames agents by id; the UI agents view gets a rename
      control. The 7 leftover "SelfHealTest" agents (stopped, test artifacts) are bulk-deletable.
15.4. Agent names should reflect ROLE not alphabet position. The UI suggests role names:
      Researcher, Implementer, Reviewer, Tester, DevOps, Docs — based on the agent's program/config.

### 16. Nav + Dashboard Enrichment
16.1. New nav items: Tools (between Dashboard and Kanban), Skills, Projects, Usage.
16.2. The Dashboard gets a "Toolchain Health" strip showing online/offline count of all tools,
      and a "Today's Tokens" mini-card linking to the Usage view.
16.3. The version in the sidebar footer bumps to v2.0.0.

## Verification (the exact checks that prove it works)
12. `curl /api/tools` returns >=6 tools with live status (Hermes online, Ollama online, etc.).
13. `curl /api/skills` returns >=15 skills grouped by category, each with use_count.
14. `curl /api/projects` returns >=10 projects with git info.
15. `curl /api/usage` returns GLM + Claude + Hermes totals that match a manual spot-check.
16. `curl /api/tasks/cleanup` archives stale tasks; kanban shows no orphaned in_progress tasks.
17. The 4 new views render in a real browser (Playwright) with no console errors.
18. `bash scripts/verify.sh` passes with the new endpoints + functions.

## Out of Scope (explicitly, for v2)
- Writing/editing tool config files (read-only tool detail for v2).
- Real-time token streaming (parsed on-demand, cached 60s).
- Cost data from providers' billing APIs (we derive from local transcripts).
- Webhook receivers / PWA / mobile (v3).
