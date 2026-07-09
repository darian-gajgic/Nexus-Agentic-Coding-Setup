# CLAUDE.md — auto-setup runbook for this repo

**You are Claude Code, running inside a clone of `hermes-team-setup` on a fresh machine.
Your job: set up this entire Hermes agent environment automatically, end to end.**

When the user says something like *"set this up"*, *"install everything"*, or *"get Hermes
running"*, execute the runbook below **autonomously**. Do the whole thing yourself — the
**only** step where you stop and hand off to the user is **the API keys** (Step 5): you
cannot know their secrets, so you pause, let them paste keys into `~/.hermes/.env`, and
then continue.

Be safe on their machine: this installs system packages, Docker containers, and a
background agent. Before the first system-level action, briefly tell them what you're
about to install and get a go-ahead. Prefer reversible steps. If a command needs `sudo`,
show it and let them run it or approve it. Never touch their existing dotfiles beyond what
the runbook specifies.

---

## Target environment
- **OS:** Ubuntu 24.04 / 26.04 (Linux). Adapt package commands for other distros.
- **Runtimes:** Python 3.11, Node.js 20+ (the Hermes installer provides these).
- **This repo** is already cloned; run everything from its root. Paths below assume the
  user's `$HOME`.

---

## Runbook

### Step 0 — Preflight
Check for and install missing prerequisites: `git`, `curl`, `docker` + `docker compose`,
and `ollama`. 
```bash
command -v git curl docker ollama || true
# Docker (if missing): https://docs.docker.com/engine/install/ubuntu/  (then: sudo usermod -aG docker $USER  &&  newgrp docker)
# Ollama (if missing): curl -fsSL https://ollama.com/install.sh | sh
```
Confirm the user is on Linux with a working `docker` daemon before continuing.

### Step 1 — Install Hermes Agent, pinned to the version these patches target
The core-mod patches in `guardian/patches/` were built against **Hermes v0.18.0,
commit `048270fa069f`**. Install Hermes, then pin to that commit so the patches apply
cleanly.
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash    # official installer
# Pin to the matching version (the install dir is a git repo):
git -C "$HOME/.hermes/hermes-agent" fetch --all --tags
git -C "$HOME/.hermes/hermes-agent" checkout 048270fa069f
# Re-sync deps for that commit if the installer used a newer tree:
"$HOME/.hermes/hermes-agent/venv/bin/pip" install -e "$HOME/.hermes/hermes-agent" 2>/dev/null || true
```
If pinning fails or the user wants the latest Hermes, proceed anyway — the guardian
(Step 4/8) will flag any patch that doesn't apply as a **conflict** for later resolution
rather than silently breaking. Tell the user if that happens.

### Step 2 — Local models (for mem0 memory)
```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

### Step 3 — Vector store (qdrant, via Docker)
```bash
docker compose -f infra/qdrant-docker-compose.yml up -d
```
(Optional observability — Langfuse — is self-hosted separately; skip unless the user
wants it, then set `HERMES_LANGFUSE_*` in Step 5.)

### Step 4 — Apply our customizations
```bash
bash install.sh
```
This copies configs, the agents (18 active + archive), custom skills, scripts, and plugins into `~/.hermes/`;
installs the guardian (`~/hermes-guardian/`) and Nexus (`~/nexus-agent-os/`); rewrites
hard-coded paths to this user's `$HOME`; installs the systemd units; and runs the guardian
once to apply the core-mod patches (the set listed in guardian/core-mods.json — 6 today,
incl. `session-model-api-server`: the keystone of model routing — upstream's api_server
ignores per-session models, so without this mod every session turn silently runs
config.yaml's default and per-task/JARVIS model choices are cosmetic).

### Step 5 — API keys ⏸️ **STOP HERE AND HAND OFF TO THE USER**
```bash
cp .env.example "$HOME/.hermes/.env"
```
Now **pause**. Tell the user:
> "Open `~/.hermes/.env` and fill in your own API keys. `GLM_API_KEY` (Z.AI — https://z.ai)
> is **required**; `BRAVE_SEARCH_API_KEY` is recommended for web search; the Langfuse keys
> are optional. Set `API_SERVER_KEY` and `JARVIS_HUD_TOKEN` to any random strings
> (`openssl rand -hex 32`). Tell me when you've saved it and I'll finish the setup."

Do **not** invent, guess, or ask them to paste keys into the chat. Wait for their "done".

### Step 6 — Nexus dashboard environment
```bash
cd "$HOME/nexus-agent-os"
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
deactivate; cd -
```

### Step 7 — Start the services
```bash
systemctl --user daemon-reload
systemctl --user enable --now hermes-gateway.service hermes-guardian.timer \
    hermes-reflect.timer hermes-prune.timer nexus.service
```

### Step 8 — Verify and report
```bash
"$HOME/.hermes/hermes-agent/venv/bin/python" "$HOME/hermes-guardian/guardian.py"   # expect overall=OK, core-mods = the count in guardian/core-mods.json (6 today)
systemctl --user is-active hermes-gateway.service nexus.service
```
Confirm to the user: guardian `overall=OK` with **all core-mods applied** (the set in guardian/core-mods.json — 6 today), gateway + nexus
**active**. Point them at the Nexus dashboard URL the service logs print, and tell them to
try Hermes with *"use a specialist to research X"* to confirm routing works.

---

## If something goes wrong
- **A core-mod patch conflicts** (Hermes version drift): the guardian reports it instead of
  breaking. Read `docs/PERSISTENCE.md`, then either check out commit `048270fa069f` (Step 1)
  or resolve the conflict in the Nexus guardian panel.
- **mem0 errors about ollama/qdrant**: make sure `ollama serve` is running and the qdrant
  container is up (`docker ps`).
- **Nexus won't start**: check its venv (Step 6) and that `API_SERVER_KEY` is set in `.env`.

## What you must NOT do
- Don't ask for, echo, or commit API keys — they belong only in `~/.hermes/.env`.
- Don't upgrade/downgrade the NVIDIA driver, kernel, or bootloader as part of this.
- The full architecture reference is in `docs/` (start with `SPECIALIST_SYSTEM.md`).
