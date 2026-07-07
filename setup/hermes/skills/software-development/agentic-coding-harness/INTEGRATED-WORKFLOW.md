# Agentic Coding & Research Toolchain — Integration Guide

> Setup completed 2026-07-03. This is the single reference for the full toolchain.
> Location: /home/sinep/.hermes/skills/software-development/agentic-coding-harness/INTEGRATED-WORKFLOW.md

## Design principles (your decisions, enforced everywhere)
1. **Result quality is priority #1.** Token/cost optimization is secondary (model tiering deferred until token-constrained).
2. **No OpenAI models. No Cursor.** VS Code + Cline is the IDE path.
3. **Free/local where viable.** GLM-5.2 (Z.AI coding max) + Claude (Anthropic) are the cloud models; Ollama (qwen3:14b, llava for vision) is the free fallback.
4. **Verify-loop is non-negotiable, and includes RUNTIME tests** — static gates alone cannot catch contract drift.

---

## MCP servers (the big 2026-07-03 upgrade)
| Server | Purpose | When it fires |
|--------|---------|---------------|
| **Context7** | Injects current, version-specific library docs into prompts. Prevents hallucinated/deprecated APIs. | SOUL.md rule: auto-use before writing code touching any external library (resolve-library-id → query-docs) |
| **Playwright** | 23 browser tools — navigate, snapshot (accessibility tree, not pixels), click, screenshot. Works on Wayland. | Runtime verification of web UIs (replaces computer_use for browser work) |

Manage: `hermes mcp list` / `hermes mcp test <name>` / `hermes mcp add` / `hermes mcp remove`.

## Memory layer
- **Hermes (me):** Supermemory — native plugin, container `hermes`, auto-capture + auto-recall on. Separate from Claude.
  Provider set via `memory.provider: supermemory`; key in ~/.hermes/.env (SUPERMEMORY_API_KEY, chmod 600).
- **Claude Code:** its own memory (MEMORY.md + knowledge-graph MCP), independent.
- Built-in flat memory (6000 char) still active as a fallback/scratch.

## Research stack (user-fixed)
- web_search → paid Brave LLM-Context (real content, ~1.5KB/result, safesearch off, truncation-aware).
- web_extract → local full-page (trafilatura→Jina). Tool descriptions set by a plugin in ~/.hermes/plugins at load time (immune to updates) — never override.

---

## The tools — what, when, how to launch

### Coding agents (CLI)
| Tool | Use it for | Launch |
|------|-----------|--------|
| **Claude Code (`claude`)** | Secondary path, Opus for hardest reasoning (tokens limited) | `claude` |
| **GLM agent (`glm`)** | Daily-driver coding, GLM-5.2 max reasoning | `glm` |
| **Aider (`aider-glm` / `aider-local`)** | Multi-file refactors, architect+editor split, atomic commits | `aider-glm` / `aider-local` (Ollama, free) |
| **Hermes delegation** | I orchestrate parallel subagents for big projects | ask me "run as a delegated build" |

### IDE
| Tool | Use it for | Launch |
|------|-----------|--------|
| **VS Code (`code`)** | Manual editing, reviewing agent output | `code .` |
| **Cline (ext)** | In-editor agent, Plan/Act modes | VS Code → Cline sidebar |
| **Memory Bank** | Persistent project state across sessions | `cline-init [project]` |

### Spec / planning / orchestration
| Tool | Use it for | Launch |
|------|-----------|--------|
| **spec-kit (`spec`)** | Formal SDD: spec→plan→tasks→code | `spec init [project]` |
| **BMAD (`bmad`)** | Full agile multi-agent pipeline. LARGE projects only | `bmad install` (in project) |
| **Paperclip (`paperclip`)** | Agent-company orchestration (consulting/research/YouTube) | `paperclip up` → :3100 |
| **Hermes skills** | `plan`, `parallel-delegated-build`, `runtime-verification`, `agentic-coding-harness` | loaded automatically when relevant |

### Context tooling
| Tool | Use it for | Launch |
|------|-----------|--------|
| **Repomix (`repomix`)** | Pack whole repo into one file for "explain this project" | `repomix` (in repo) |

---

## The verify hierarchy (3 gates, all required for "done")
1. **Per-edit (fast):** syntax + lint + function-presence → `<proj>/.claude/check.sh` (auto-run by Claude Code PostToolUse on Write|Edit).
2. **Pre-commit (medium):** the above + focused tests → `scripts/verify.sh` (git pre-commit hook enforces).
3. **Runtime/integration (before declaring a feature done):** Playwright/e2e that drives the REAL flow and asserts on observable behavior (reply rendered, video loaded, state transitioned). NOT optional for UI features. See the `runtime-verification` skill.

If you can't run the runtime test (no browser automation installed), INSTALL IT first — building blind is how features ship broken.

## Rules that load every session (SOUL.md)
- Context7 auto-use before writing library/framework code (never guess APIs).
- Prompt-cache discipline: front-load stable context, don't edit rules mid-conversation, batch tool calls.

---

## Known issues / gotchas
- **Terminal crashes** = gnome-terminal/VTE 0.84.0 segfault bug (NOT Hermes/memory). Use kgx/alacritty/kitty if it persists.
- **computer_use** broken on Wayland (X11 GetImage error 8). Workaround: Playwright MCP for browser work (works on Wayland). Full-desktop capture still needs a cua-driver upgrade.
- **Orca** = permanently disabled (gsetting + autostart override + binary non-exec). If narration recurs it's NOT Orca.

---

## Quick-start cheat sheet
```
# Code a feature (daily driver)
glm                      # /spec <feature>, implement, reviewer checks

# Refactor (best quality)
aider-glm --architect    # GLM plans + edits, atomic commits

# Open in IDE to review / hand-code
code . && cline-init     # sets up Memory Bank too

# Big client project
cd <project> && bmad install    # full BMAD pipeline

# "Explain this codebase"
repomix                  # → repomix-output.xml, feed to any model

# I orchestrate parallel work
"run this as a delegated build"   # → parallel-delegated-build skill

# Research/consulting/YouTube agent org
paperclip up             # → http://localhost:3100

# Verify a web feature is REALLY done (not just "compiles")
# → runtime-verification skill (Playwright drives the real UI)
```

---

## The tools — what, when, how to launch

### Coding agents (CLI)
| Tool | Use it for | Launch | Cost |
|------|-----------|--------|------|
| **Claude Code (`claude`)** | Complex coding, Opus 4.8 ultracode multi-agent | `claude` | Anthropic (paid) |
| **GLM agent (`glm`)** | Daily-driver coding, GLM-5.2 max reasoning | `glm` | Z.AI (paid) |
| **Aider (`aider-glm`)** | Multi-file refactors, architect+editor split, atomic git commits | `aider-glm` | Z.AI (paid) |
| **Aider local (`aider-local`)** | Same, but free/local (Ollama qwen3:14b) | `aider-local` | Free |
| **Hermes delegation** | I orchestrate parallel subagents for big projects | ask me "run this as a delegated build" | uses model budget |

### IDE
| Tool | Use it for | Launch |
|------|-----------|--------|
| **VS Code (`code`)** | Manual editing, reviewing agent output, coding yourself | `code .` |
| **Cline (VS Code ext)** | In-editor autonomous agent, Plan/Act modes | open VS Code → Cline sidebar |
| **Cline Memory Bank** | Persistent project state across sessions | `cline-init [project]` |

### Spec / planning / orchestration
| Tool | Use it for | Launch |
|------|-----------|--------|
| **spec-kit (`spec`)** | Formal SDD: spec.md → plan.md → tasks.md → code | `spec init [project]` |
| **BMAD (`bmad`)** | Full agile multi-agent pipeline (analyst→PM→arch→dev→QA). LARGE projects only | `bmad install` (inside project) |
| **Paperclip (`paperclip`)** | Agent-company orchestration for consulting/research/YouTube content pipelines | `paperclip up` → http://localhost:3100 |
| **Hermes skills** | `plan`, `parallel-delegated-build`, `agentic-coding-harness` | loaded automatically when relevant |

### Context tooling
| Tool | Use it for | Launch |
|------|-----------|--------|
| **Repomix (`repomix`)** | Pack whole repo into one file to feed a model for "explain this project" | `repomix` (in repo) |

---

## Decision guide — which tool for which job

**Quick fix / small task** → `glm` or `claude` directly. Verify gate auto-runs.

**Feature (multi-file, non-trivial)** → one of:
- `glm` then `/spec` → implement → reviewer subagent (your existing lean loop)
- `aider-glm` in architect mode (best for refactors)
- VS Code + Cline with Memory Bank (best when you want to watch/steer in-editor)

**Large project (multi-week, many features)** → `bmad install` in the project for the full analyst→architect→dev→QA pipeline. Most ceremony, most rigor.

**"Explain this whole codebase to me"** → `repomix` then feed the packed file to a model.

**Parallel independent workstreams** → ask me to run a `parallel-delegated-build`. I spawn up to 3 isolated subagents, verify, and review adversarially.

**Consulting/research/YouTube content pipeline** → Paperclip. Orchestrates agents as an org (roles, budgets, governance). Start it with `paperclip up`.

**You want to code it yourself / review carefully** → `code .` + Cline in Plan mode for the planning, Act mode approves each step.

---

## The verify-loop (applies to ALL paths)

Two layers, both already wired:
1. **Per-edit gate** (instant): after every Write|Edit, `.claude/check.sh` runs in the project. Blocks + feeds the error back to the agent.
   - `~/.claude` → test-check.js (opt-in via `<proj>/.claude/check.sh`)
   - `~/.claude-glm` → verify-check.sh (same opt-in)
2. **Commit gate** (editor-agnostic): git pre-commit hook runs `scripts/verify.sh`. Blocks the commit if it fails.

To opt a new project in: create `<project>/.claude/check.sh` (see `agentic-coding-harness` skill for the template).

---

## Model routing (your stack)
- **Primary cloud (paid):** GLM-5.2 via Z.AI — backs `glm`, `aider-glm`, and me (Hermes). reasoning_effort=max.
- **Secondary cloud (paid):** Claude (Anthropic) — `claude` CLI, Opus 4.8 for hardest tasks.
- **Local/free:** Ollama qwen3:14b / qwen2.5:14b — `aider-local`, Cline (set provider to Ollama).
- **Never:** OpenAI models (your call), Gemini (not installed — you declined the fallback).

---

## Known issues / gotchas
- **Terminal crashes** = gnome-terminal/VTE 0.84.0 segfault bug. NOT Hermes delegation, NOT memory (verified). No fix in repos; use `kgx`/`alacritty`/`kitty` if it persists.
- **Orca screen reader** = permanently disabled (gsetting off + autostart override + binary non-exec). If narration recurs it's NOT Orca.
- **Paperclip data dir** = `/home/sinep/agent-orchestration/paperclip/data/docker-paperclip` (owned uid 1000). The `paperclip` launcher handles start/stop.
- **Delegation limits** = explicitly set safe: max_concurrent_children=3, max_spawn_depth=1. Don't raise without thinking about Z.AI quota (~10 concurrent).

---

## Quick-start cheat sheet
```
# Code a feature (daily driver)
glm                      # then /spec <feature>, implement, reviewer checks

# Code a refactor (best quality)
aider-glm --architect    # GLM plans + edits, atomic commits

# Open in IDE to review / hand-code
code . && cline-init     # sets up Memory Bank too

# Big client project
cd <project> && bmad install    # full BMAD pipeline

# "Explain this codebase"
repomix                  # produces repomix-output.xml, feed to any model

# I orchestrate parallel work
"run this as a delegated build"   # → parallel-delegated-build skill

# Research/consulting/YouTube agent org
paperclip up             # → http://localhost:3100
```
