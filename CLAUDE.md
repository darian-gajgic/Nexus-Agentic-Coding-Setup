# CLAUDE.md — Nexus-Agentic-Coding-Setup

This repo is the COMPLETE project: the full Nexus Agent OS (`app/`) plus the
entire Hermes environment (`setup/` — configs, 18 specialists, skills, plugins,
guardian core-mod system, systemd units, qdrant infra, knowledge base).

**To set up a fresh machine end to end, follow `setup/CLAUDE.md`** — it is the
autonomous runbook (prereqs → Hermes pinned @ 048270fa069f → models → qdrant →
customizations → API keys handoff → services → verify). One change vs. that
runbook: its Step 4 (`bash setup/install.sh`) installs Nexus from THIS repo's
`app/` tree automatically.

Quick nexus-only install (Hermes already present): `bash install.sh`.

Not in the repo, by design: re-downloadable tools (Hermes upstream clone,
ollama models, Docker images, JARVIS voice models), machine secrets
(`~/.hermes/.env` — template at `setup/.env.example`), TLS certs, and runtime
data (nexus.db, workspaces, state.db).

**Since the 2026-07-09 unification, `app/` IS the live working tree** — the
running service points at `~/nexus-agent-os`, which is a symlink into this
repo's `app/`. Edit + commit here directly (the pre-commit hook runs
`app/scripts/verify.sh`); no snapshot step. The symlink is LOAD-BEARING: the
systemd unit, absolute workspace paths stored in nexus.db, and the venv
shebangs all resolve through `~/nexus-agent-os` — never remove it. Run the
service from `main`; use git worktrees for experiments (a bare `git checkout`
swaps the RUNNING code). `scripts/refresh-app.sh` is retired to a hermes-side
file copy only.

Keep the Hermes side current: re-vendor `setup/` from ~/hermes-team-setup
(local staging only — its remote is retired) after running its
`scripts/sync-hermes.sh` / `sync-brain.sh`.
