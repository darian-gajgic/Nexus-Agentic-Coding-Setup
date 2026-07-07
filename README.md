# Nexus-Agentic-Coding-Setup

Repo-native agentic coding for the Nexus + Hermes stack: point any kanban task
(or a whole wizard pipeline) at an **existing client repository** and the
pipeline works *inside* it — isolated git worktree, branch per pipeline, the
repo's own conventions and test gates, and a reviewable **diff as the
deliverable** — instead of scaffolding a fresh project in an empty workspace.

Built 2026-07-07 against the researched plan in
`docs/HERMES-BIGPROJECT-CODING-PLAN.md` (Sourcegraph Big-Code practices,
Claude Code context discipline, live audit of this install).

## What it adds

**Hermes side** (`patches/hermes-dev-specialists.patch`, already applied +
committed in `~/.hermes/agents` @ e14fc20):
- All five dev specialists (tech-lead-orchestrator, code-implementer,
  code-reviewer, acceptance-verifier, debugger) gain the `mcp-serena` (LSP
  symbol navigation) and `mcp-context7` (current library docs) toolsets.
- New mandatory playbook block: navigate by symbol not file-reads,
  blast-radius-first planning, done = the repo's own gates green AND every
  touched symbol's usages re-searched, repo conventions file wins, schema
  migrations always escalate to the human.

**Nexus side** (`patches/nexus-repo-native-tasks.patch`, applied to the live
working tree, deliberately NOT committed in nexus-agent-os per operator
instruction — this repo is the canonical record):
- `tasks.repo_path` column + API field + validation (`is_repo`).
- `worktree.py`: `ensure_task_worktree` (idempotent branch `nexus/<slug>`,
  worktree under `<repo>/.worktrees/`; pipeline tasks share one branch so
  stages build on each other; different pipelines stay isolated; the
  operator's main checkout is never touched), `snapshot_commit` (never lose
  uncommitted agent work), `capture_diff` (three-dot vs the baseline branch).
- `hermes_dispatch.py`: repo-mode framing — work inside the worktree, follow
  AGENTS.md/CLAUDE.md (first 6KB injected directly into the framing → no
  Hermes core-mod needed), run the repo's own gates, commit on the branch;
  after the turn: snapshot-commit + `changes.diff` captured into the task
  workspace for review/UI/judge.
- UI: repo picker in the task-create modal (from the Code Projects registry),
  repo badge in task detail, `changes.diff` previews inline in Deliverables.
- Task template "🧬 Onboard a code repository" — read-only generation of a
  ruthless-concise `AGENTS.md` (purpose, architecture map, verified commands,
  conventions, danger zones; <150 lines).

## Design decisions (state of the art, and why)
- **Diff is the deliverable; human is the merge gate.** Nothing pushes or
  merges automatically — the pipeline proposes a branch, you review the diff.
- **Zero Hermes core-mods.** Repo conventions are injected by Nexus at
  framing time instead of patching the session API for cwd — deterministic,
  guardian-neutral, works today. (A session-cwd core-mod remains a possible
  later refinement for interactive CLI parity.)
- **Branch per PIPELINE, not per task** — implement → review → fix → verify
  must see each other's work; parallel pipelines on one repo get separate
  worktrees (amux isolation).
- **Deterministic retrieval over embeddings** — LSP symbol navigation
  (serena) instead of vector-indexing client repos.
- **Non-breaking:** a task without `repo_path` behaves byte-identically to
  before; verified by the full 109-check gate.

## Install on a new machine — FULL project (Hermes + Nexus)
```bash
git clone git@github.com:dariannixda-eng/Nexus-Agentic-Coding-Setup.git
cd Nexus-Agentic-Coding-Setup
# then follow setup/CLAUDE.md — or open the repo in Claude Code and say
# "set this up": the runbook installs Hermes (pinned @ 048270fa069f), local
# models, qdrant, ALL customizations (18 specialists, skills, plugins,
# guardian core-mods, systemd units) AND Nexus from app/ — pausing once for
# you to paste API keys into ~/.hermes/.env (template: setup/.env.example).
```
Nexus-only quick path (machine already runs Hermes): `bash install.sh`.

Excluded by design (re-downloadable or secret): Hermes upstream clone, ollama
models, Docker images, JARVIS voice models, API keys (.env), TLS certs, and
runtime data (nexus.db, workspaces, Hermes state.db).

## Repo layout
- `app/` — the COMPLETE Nexus Agent OS source tree (2.2 MB, runtime data
  excluded) with the repo-native feature applied. This is what installs.
- `install.sh` — one-command install: copies the tree, builds the venv
  (`app/requirements.txt`; voice stack optional in `requirements-voice.txt`),
  generates a self-signed cert, installs the five dev specialists into
  `~/.hermes/agents` (with backups), and registers the systemd user unit.
- `system/nexus.service` — the unit template (paths rewritten at install).
- `patches/` — the feature as reviewable git patches.
  `nexus-repo-native-tasks.patch` applies on nexus-agent-os @ **01d7138**.
- `files/` — copies of just the feature-changed files (review-friendly view;
  `app/` supersedes them for installation).
- `scripts/refresh-app.sh` — re-snapshot this package from the live source
  machine before pushing updates.
- `docs/` — the research plan this implements.

NOT in the package (by design): `nexus.db` and task workspaces (runtime data),
TLS certs (generated per machine), JARVIS voice models (optional GPU stack —
see `docs/JARVIS-VOICE.md` in `app/docs/`), and Hermes itself (own setup repo).

## Apply / verify / rollback
- Nexus: `git -C ~/nexus-agent-os apply patches/nexus-repo-native-tasks.patch`
  (already live on this machine; base commit 01d7138 — if the base has moved,
  copy from `files/nexus/` instead), then `bash scripts/verify.sh` and restart
  the `nexus` unit.
- Hermes specialists: `git -C ~/.hermes/agents cherry-pick e14fc20` on a fresh
  machine (or copy `files/hermes-agents/*.md` into `~/.hermes/agents/`).
- Rollback: `git -C ~/nexus-agent-os checkout -- .` (nexus) and
  `git -C ~/.hermes/agents revert e14fc20` (specialists).

## E2E verification (2026-07-07, live pipeline run)
Probe task on a scratch repo: agent worked in the isolated worktree, followed
AGENTS.md conventions, committed `Add farewell() to greeter`, repo test suite
green, 39-line junk-free changes.diff captured, main checkout untouched.
The run also surfaced and fixed: a per-model slot deadlock (truthy "0"
default), snapshot pollution by __pycache__, and a git pathspec quirk
(':(exclude)' long form required).

## Usage
1. (Once per client repo) Create a task from the "🧬 Onboard a code
   repository" template, attach the repo, dispatch → you get a reviewed
   `AGENTS.md`.
2. Any coding task or wizard pipeline: pick the repo in "Existing code
   repository". The pipeline runs on branch `nexus/<id>`; open the task's
   `changes.diff` in Deliverables, review, and merge manually
   (`git merge nexus/<id>`) when satisfied.
