# Agentic Coding Landscape — Condensed Knowledge Bank (2026-07)

Reference for tool selection, cost model, and setup status. Distilled from a broad sweep of
primary sources (Anthropic/GitHub/Microsoft engineering blogs, New Relic + METR studies, SSOJet /
Firecrawl / Morphllm leaderboards, r/LocalLLaMA practitioner threads). Keep concise; go upstream
for exhaustive docs.

## The empirical case (why a harness beats a bigger model)

- **METR study (2025):** 16 experienced devs on their OWN repos took **19% LONGER** with AI tools.
  Root cause: cognitive load from reviewing/verifying AI output. "Substantial and persistent gap
  between perceived and actual performance." → This is the user's exact complaint ("checking your
  results takes too long"). Fix is process, not model.
- **New Relic 2026 State of AI Coding:** AI code grades HIGHER in review than human code, but causes
  **~1.7x more critical runtime incidents** in production; 82% of orgs had an AI-code prod failure
  in 6 months. → Review is insufficient; only **automated execution** catches what eyeballs miss.
  This is why the verify-loop is non-negotiable.
- **r/LocalLLaMA top practitioner insight:** "The biggest quality jump comes from diff-only output
  + strict context slicing, not switching models. Bigger helps, but control helps more."

## The common loop (every framework converges here)

```
SPEC → PLAN (file) → IMPLEMENT (isolated) → VERIFY (auto, blocking) → REVIEW (adversarial, fresh ctx) → COMMIT
```
Tools differ in packaging, not in the loop. BMAD wraps personas; spec-kit wraps files
(spec/plan/tasks); Claude Code wraps hooks+subagents; Cline wraps Memory Bank + Plan/Act.

## Tool map by archetype

### 1. Benchmark leaders (paid, model-locked)
- **Claude Code** (Opus 4.8) — deepest harness: Dynamic Workflows + 30 hook events + agent teams.
- **Codex CLI** (GPT-5.x) — sandbox/approval modes, one account across CLI/cloud/mobile.

### 2. In-editor middle (subscriptions, editor-centric)
- Cursor, Antigravity (Google, free for individuals), Copilot, Windsurf. Shared agent+editor loop.

### 3. Open-source / model-agnostic (free, run any model)
- **OpenCode** — most-starred (75+ providers, Go binary, Plan/Act modes). Top GLM pairing per Reddit.
- **Aider** — any LLM via LiteLLM; repo-map (fns/classes without loading every file); architect mode
  (planner + cheaper editor — measurably improves correctness on multi-file refactors, not just
  tokens); atomic git commit per turn; voice coding via Whisper.
- **Cline / Roo Code** — VS Code extensions; Plan/Act modes; Memory Bank (projectbrief→productContext
  →activeContext...); .clinerules. Roo adds "sandboxed autonomy" per mode.
- **Goose** (Block) — MCP-first autonomous; install/exec/edit/test; 70+ MCP extensions.
- **Gemini CLI** — FREE tier: ~1000 req/day, 1M token context, no credit card. Cheapest fallback.

## Orchestration / multi-agent frameworks

- **BMAD-METHOD** — most comprehensive spec-driven METHOD (not a product). Markdown/YAML agent
  personas (analyst→PM→architect→UX→dev→QA→orchestrator) + workflows + templates, installed into any
  coding agent via `bmad install` (npx, per-project). V6 has scale-adaptive planning. Large projects only.
- **Claude Code Dynamic Workflows / agent teams** — native; Claude authors orchestration scripts at
  runtime, fans out subtasks in parallel, validates, synthesizes. Invoked via effort=ultracode.
- **Paperclip** — "AI company" orchestrator: org charts/budgets/governance/audit. Bring-your-own-bot
  (Claude Code/Codex/OpenCode/OpenRouter). Use case: consulting/research/content pipelines, not coding.
  Self-host via Docker quickstart. See `references/paperclip-selfhost-setup.md` for the gotchas.
- **GitHub spec-kit** — reference SDD: spec.md→plan.md→tasks.md→code; marks parallel tasks [P];
  exact file paths; TDD-ordered. `spec init` (uvx wrapper). The canonical formal spec loop.
- **Hermes native delegation** — delegate_task spawns async isolated subagents; execute_code for
  mechanical sweeps; cron. First-class multi-agent without shelling out to other CLIs. See the
  `parallel-delegated-build` skill for the orchestrated loop.

## Context engineering tooling

- **Repomix** — packs whole repo into one AI-friendly file (XML/MD/JSON). `repomix` (in repo). For
  one-shot "explain this project" or feeding a codebase to a model. Complements agent file access.
- **Aider repo-map** — token-efficient context (signatures only); /add only changed files.
- **Rule files** — AGENTS.md (shared, committed) / CLAUDE.md (Claude-native) / .clinerules /
  GEMINI.md. Pattern: hard constraints + build/test/lint commands + scope boundaries, kept short.

## User's toolchain — INSTALLED & configured (verified 2026-07-03)

All below are installed and on PATH. New ones added this session are **bold**.

Launchers (all executable):
- `claude` — Claude Code (Anthropic, paid). Opus 4.8 ultracode for hardest tasks.
- `glm` — shell fn, GLM-5.2 max reasoning via Z.AI (paid). Daily driver. Bypass mode.
- **`aider-glm`** — Aider architect mode with GLM-5.2 (paid). Multi-file refactors.
- **`aider-local`** — Aider with Ollama qwen3:14b (free). Free local fallback.
- **`code`** — VS Code (snap, v1.124.0). Extensions: Claude Code, **Cline** (saoudrizwan.claude-dev).
- **`cline-init`** — bootstraps Cline Memory Bank + .clinerules into a project.
- **`spec`** — spec-kit wrapper (`spec init <project>`, integration=claude).
- **`bmad`** — BMAD wrapper (`bmad install`, inside a project; large projects only).
- **`repomix`** — packs repo into one file (`repomix` in repo dir).
- **`paperclip`** — self-host control (`paperclip up/down/logs/status`, :3100).

Config / setup facts:
- Backends paid: Z.AI GLM-5.2 (primary), Anthropic Claude (secondary). No OpenAI, no Cursor, no Gemini.
- Free: Hermes Agent, Ollama (qwen3:14b, qwen2.5:14b), all open-source tools above.
- Verify-loop wired BOTH instances: ~/.claude (test-check.js) + ~/.claude-glm (verify-check.sh, see
  templates/verify-check.sh). Editor-agnostic git pre-commit gate in each project.
- Hermes delegation bounded safe: max_concurrent_children=3, max_spawn_depth=1, compression @50%.
- Cline Memory Bank template at ~/.config/cline-memory-bank-template/ (projectbrief/productContext/
  activeContext/systemPatterns-progress + .clinerules).
- Paperclip at /home/sinep/agent-orchestration/paperclip, data at paperclip/data/docker-paperclip (uid 1000).

Decision guide (which tool for which job):
- Quick fix / small task → `glm` or `claude` directly (verify gate auto-runs).
- Feature (multi-file) → `glm`/spec, or `aider-glm` (refactors), or VS Code+Cline (watch/steer).
- Large project (multi-week) → `bmad install` (full analyst→architect→dev→QA pipeline).
- "Explain this codebase" → `repomix` then feed the packed file to a model.
- Parallel independent workstreams → ask Hermes for a delegated build (parallel-delegated-build skill).
- Consulting/research/YouTube agent org → `paperclip up`.
- Hand-coding / careful review → `code .` + Cline Plan/Act modes.
