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

Keep it current from the source machine: `bash scripts/refresh-app.sh` (nexus)
and re-vendor `setup/` from ~/hermes-team-setup after running its
`scripts/sync-hermes.sh`.
