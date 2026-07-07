# Cline + Memory Bank setup (VS Code) — for when the user wants to drive / review in an IDE

Cline (VS Code ext id: `saoudrizwan.claude-dev`) is a Plan/Act-mode agent. It uses any OpenAI-
compatible provider including local Ollama (free). Memory Bank is Cline's persistence layer — a
hierarchy of markdown files the agent reads at session start and updates at session end.

## Install
```bash
code --install-extension saoudrizwan.claude-dev
```

## Provider config (do it in VS Code UI, not a file)
Cline settings → API Configuration:
- **Local/free:** Provider = Ollama, base http://localhost:11434, model qwen3:14b.
- **Cloud:** Anthropic key (Claude) or an OpenAI-compatible custom endpoint (GLM via Z.AI).
Priority for this user = result quality first; token/cost second.

## Memory Bank hierarchy (standard Cline docs)
1. `projectbrief.md` — foundation, defines scope (source of truth)
2. `productContext.md` — why it exists, problems solved, UX goals
3. `activeContext.md` — CURRENT focus, recent changes, next steps, blockers (read FIRST on resume)
4. `systemPatterns.md` / `progress.md` — architecture, decisions, what works, what's left

## Bootstrap template (reusable across projects)
Store a template dir at `~/.config/cline-memory-bank-template/` with skeleton versions of each
file plus a `.clinerules`. Then a one-command bootstrap:
```bash
# ~/.local/bin/cline-init — copy the template into a project
#!/usr/bin/env bash
set -euo pipefail
PROJ="${1:-.}"; PROJ="$(cd "$PROJ" && pwd)"
TPL="$HOME/.config/cline-memory-bank-template"
mkdir -p "$PROJ/memory-bank"
cp "$TPL"/projectbrief.md "$TPL"/productContext.md "$TPL"/activeContext.md "$PROJ/memory-bank/"
cp "$TPL"/.clinerules "$PROJ/.clinerules"
```
Usage: `cline-init <project-dir>` then `code <project-dir>`.

## The .clinerules that enforces the verify-loop inside Cline
Key rules to put in `.clinerules` so Cline matches the CLI agents' discipline:
- After EVERY code change: run the project check (syntax+lint+tests) before claiming done.
  NEVER report done without executing verification (New Relic 2026: AI code grades high in review
  but causes 1.7x runtime incidents — only execution catches what review misses).
- For non-trivial features: PLAN mode, present plan, get approval before ACT.
- Match surrounding code style; DRY/YAGNI/KISS; minimal diffs; reuse before adding new.
- Never read/print secrets; never rm -rf/dd/force-push without explicit approval.
