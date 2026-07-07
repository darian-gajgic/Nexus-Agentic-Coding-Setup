# Hermes Team Setup

A portable snapshot of our customized **Hermes Agent** setup — the persistent
specialist-agent system, the self-healing guardian, the Nexus dashboard, the mem0
memory scoping, and all the tools we built on top of Hermes. Clone this on a second
machine, install the base tools, add your own API keys, and run the installer to get
the **same configuration and features**.

> **What this repo is (and isn't).** It contains *our customizations* — configs,
> the specialist agents (18 active + 28 archived), custom skills, plugins, the guardian + core-mod patches,
> Nexus, and the memory/infra config. It does **not** contain the upstream Hermes
> install itself, the local LLM models, Docker images, any secrets, or any personal
> conversation history/memory — you install those separately (steps below). Nothing
> here holds a live API key; fill in your own via `.env`.

---

## What you get

- **18 active specialist agents + 28 archived** (`hermes/agents/`, consolidated 2026-07-06 — every kept one carries a mandatory Knowledge protocol; archived ones are restorable) — dev, SaaS, research, marketing,
  brand, content, e-commerce, plus DJ/music — that Hermes reuses with per-agent
  playbooks and private memory. See `docs/SPECIALIST_SYSTEM.md`.
- **Keyword-triggered specialist router** (`hermes/plugins/routing/specialist_router/`)
  — say "use a specialist" and it force-routes to the best-matching agent.
- **Auto-reflection + lesson pruning** (`hermes/scripts/`) — specialists learn from
  their work (human-approved) and stale lessons are auto-archived.
- **Self-healing guardian** (`guardian/`) — verify-only watchdog that re-applies our
  edits to Hermes's own source (as git patches) after a `hermes update` reverts them
  (or on an explicit `guardian.py --restore`); between updates it only reports drift.
- **Nexus control plane** (`nexus/`) — the web UI is now the REAL execution layer
  (v2, 2026-07-06): kanban cards are executed by real Hermes `api_*` sessions via
  worker "lanes" (atomic claiming, resume-based self-heal, per-task model choice
  glm-5.2/5.1/4.5-air), deliverables land as files per task, high-stakes work pauses
  for approval with a frontier-judge (`cjudge`) verdict, budgets/quota-storm backoff,
  health panel, task templates, JARVIS voice. Spec: `nexus/SPEC-REAL-AGENTS.md`.
  Since the `unified` merge, `nexus/` is a real **git subtree** (squashed) of
  `~/nexus-agent-os`; refresh with `bash scripts/sync-nexus.sh` (subtree pull of
  the committed tree — secret-free by construction).
- **Two-scope mem0 memory** (`hermes/mem0.json` + patches) — per-specialist private
  memory + a curated team-shared scope, on self-hosted qdrant.
- **Custom skills** (`hermes/skills/`), including the `development-workflow` pipeline
  (research → plan → implement → test → review-loop → verify → document).

---

## Prerequisites (install these first)

Tested on **Ubuntu 26.04**. You need:

1. **Hermes Agent** — install from https://github.com/NousResearch/hermes-agent
   into `~/.hermes/hermes-agent` (follow their README; create its venv).
   ⚠️ Use the **same version our patches target** (see `guardian/core-mods.json` and
   `docs/PERSISTENCE.md`) so the core-mod patches apply cleanly.
2. **Docker + Docker Compose** — for qdrant (and optionally Langfuse).
3. **Ollama** — https://ollama.com — then pull the local models used by mem0:
   ```bash
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```
4. **Python 3.11+** and **Node.js** (Hermes uses some npm-based MCP servers).

---

## Install

### Easiest: let Claude Code do it
Clone the repo, open **Claude Code** in its folder, and say **"set this up"**. It reads
`CLAUDE.md` and runs the whole installation automatically — base tools, customizations, and
services — pausing only once, for you to paste your own API keys into `~/.hermes/.env`.

### Or do it manually

```bash
git clone <this-repo-url> hermes-team-setup
cd hermes-team-setup

# 1. Start qdrant (vector store for mem0)
docker compose -f infra/qdrant-docker-compose.yml up -d

# 2. (Optional) Langfuse for observability — self-host separately:
#    https://langfuse.com/self-hosting  (then set HERMES_LANGFUSE_* in .env)

# 3. Apply our customizations to your Hermes install
bash install.sh

# 4. Add your OWN API keys
cp .env.example ~/.hermes/.env
$EDITOR ~/.hermes/.env      # fill in GLM_API_KEY (required) + the rest

# 5. Start everything
systemctl --user daemon-reload
systemctl --user enable --now hermes-gateway.service hermes-guardian.timer \
    hermes-reflect.timer hermes-prune.timer nexus.service

# 6. Nexus dashboard
cd ~/nexus-agent-os && python -m venv .venv && . .venv/bin/activate \
    && pip install -r requirements.txt   # first time only
# then it runs under the nexus.service unit; open the dashboard URL it prints.
```

`install.sh` copies configs/agents/skills/scripts/plugins into `~/.hermes/`, installs
the guardian into `~/hermes-guardian/`, Nexus into `~/nexus-agent-os/`, drops the
systemd units into `~/.config/systemd/user/` (rewriting paths for your user), and
runs the guardian once with `--restore` to apply the 5 Hermes core-mod patches.

---

## Repo layout

| Path | What |
|---|---|
| `hermes/config.yaml`, `SOUL.md`, `mem0.json` | Hermes config, system prompt, memory config |
| `hermes/agents/` | specialist definitions (18 active + archive/ with 28 restorable) |
| `hermes/skills/` | our custom/modified skills only (upstream-identical ones are excluded by the sync) |
| `hermes/scripts/` | reflect.py (auto-reflection), prune_lessons.py, mem0_curate.py |
| `hermes/plugins/` | specialist_router + our other user plugins |
| `guardian/` | guardian.py, manifest.json, core-mods.json, `patches/*.patch`, `golden/` |
| `nexus/` | the Nexus dashboard (code only — build its venv from requirements.txt) |
| `infra/` | qdrant docker-compose |
| `systemd/` | user service/timer units |
| `docs/` | full architecture write-ups — start with `SPECIALIST_SYSTEM.md` |
| `knowledge/` | the Business Brain: 9 domain playbooks + rubrics + exemplars, WORKFLOW routing, MANUAL (operator guide incl. German), evals, WIN/LESSON ledgers. Specialists hard-reference `~/knowledge/...` — install to `~/knowledge` |
| `bin/` | frontier bridge scripts `cspec` / `creview` / `cjudge` (spec-writing, diff review, deliverable judging via the Anthropic side) — install to `~/.local/bin`, need the `claude` CLI logged in |
| `claude-glm/` | GLM-side Claude Code config (CLAUDE.md, pipeline agents, /spec + /ultra commands, hooks) — install to `~/.claude-glm`; its API key lives in `~/.glm-agent/key.env` (bring your own) |

---

## Updating this snapshot (from the main machine)

After meaningful changes land in the live setup, refresh the snapshots and push:

```bash
bash scripts/sync-nexus.sh    # subtree-pulls ~/nexus-agent-os HEAD into nexus/ (commits itself)
bash scripts/sync-hermes.sh   # exports ~/.hermes customizations + guardian + systemd
bash scripts/sync-brain.sh    # exports ~/knowledge + bridge scripts + ~/.claude-glm
git diff --stat               # review what changed
git add -A && git commit -m "sync: <what changed>" && git push
```

All scripts are secret-safe: sync-nexus pulls only git-committed files (db/certs/
env/models are gitignored at the source), sync-hermes uses an allowlist (never
`.env`, state DBs, reports, personal memories) and ABORTS if anything resembling
a real credential appears in the export. Provenance: nexus/ carries its source
commit in the subtree merge message; `hermes/.snapshot-provenance` stamps the rest.

---

## Notes & gotchas

- **Secrets** live only in `~/.hermes/.env` (never committed). See `.env.example`.
- **Core-mods**: we edit 5 files inside Hermes's own source; the guardian re-applies
  them after updates. If `hermes update` bumps the version and a patch fails, the
  guardian flags a conflict in Nexus for you to resolve. See `docs/PERSISTENCE.md`.
- **mem0** runs in OSS mode against local ollama + qdrant — no cloud mem0 account.
- This is a **fresh start**: no accumulated memories are included. Your specialists
  learn from scratch; approve their lessons in the Nexus Specialists tab.
- Nexus generates its own TLS cert on first run (the old `cert.key`/`cert.pem` are
  intentionally excluded).
