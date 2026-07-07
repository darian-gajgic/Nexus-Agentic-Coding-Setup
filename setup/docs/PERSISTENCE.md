# Update-Persistence Analysis & Plan

**How every change from this session survives (or doesn't) a `hermes update` and the external-stack upgrades. Web-verified against the installed code + current tool docs, July 2026.**

## Headline

**A normal `hermes update` loses nothing.** Its only dependency step is `uv pip install -e ".[all]"` (additive — main.py:7648), never `uv sync` (which prunes). Git operations run only inside the repo (`~/.hermes/hermes-agent`); everything user-owned lives in `~/.hermes/` *above* the repo, or in separate projects. 16 of our changes survive outright; the handful of "conditional" cases are about a **venv rebuild** or each external tool's **own** upgrade — not about `hermes update`.

## Survives a `hermes update` — no action needed

| Change | Why it persists |
|---|---|
| `config.yaml` edits (effort, vision, mem0, langfuse plugin, playwright pin, disabled skills, pre_update_backup, removed fallback) | In HERMES_HOME (outside git). `load_config` deep-merges user **over** defaults; `migrate_config` is additive-only and never materializes defaults (explicit "don't blow up my config" guard). |
| `.env` (Langfuse keys, rotated API_SERVER_KEY/JARVIS/Brave) | Outside git. Update only appends missing *required* vars and clears a fixed deprecated-key allowlist — none of ours. |
| **zai override plugin** (`~/.hermes/plugins/model-providers/zai/`) | Outside the repo; loaded after the bundled profile, wins by last-writer-registration. Update never writes to `~/.hermes/plugins`. |
| `client-delivery-gate` skill | User skill, not in the bundled manifest — skill-sync never touches it. |
| **Bundled-skill edit** (`hermes-agent-skill-authoring`, `/home/bb`→`~/.hermes`) | Hermes hashes it, sees it diverges from the recorded origin, marks it **user-modified and skips it forever**. *Trade-off: that one skill is now frozen — it won't receive upstream content updates while diverged.* |
| `pixel_qa.py`, `mem0.json`, `memories/USER.md` | All in HERMES_HOME, outside git, never written by the updater. |
| `mem0ai` + `qdrant-client` | In `pyproject.toml`/`uv.lock`; `mem0ai` is also a *lazy feature* that update actively refreshes and that self-heals on first mem0 use. |
| Langfuse Docker stack, nexus, Claude Code settings | Entirely outside Hermes' update scope (confirmed: no reference to those paths anywhere in the update code). |

## Protective actions taken this session

1. **Committed the nexus edits** (`git commit e141022`) — they were uncommitted working-tree changes (the most fragile state: a stray `git checkout`/`reset` would have reverted the Observability view + localhost bind). Now durable in git history.
2. **Created `~/.hermes/scripts/reinstall-extras.sh`** — one command to re-assert the un-lockfiled packages (`langfuse`, `ollama`, `mem0ai`, `qdrant-client`) after a venv rebuild.
3. **Pinned ClickHouse** in `~/langfuse/docker-compose.yml` to `:26.6` (was untagged `:latest`) so a future `docker compose --pull` can't silently jump to a ClickHouse major that Langfuse v3 rejects.

## Rules to follow (the only real risks)

- **Upgrade Hermes only with `hermes update`.** Never re-run `setup-hermes.sh` or the `install.sh` curl one-liner unless you *intend* to rebuild the venv — those run `uv sync --locked`, which **prunes** `langfuse` + `ollama` (they aren't in the lock). Recovery if you ever do: `bash ~/.hermes/scripts/reinstall-extras.sh` then `hermes gateway restart`.
  - Note: if `langfuse` ever vanishes, observability goes dark **silently** (the plugin fails open with `Langfuse=None`, no error). So this is worth guarding.
- **Langfuse upgrades:** use `docker compose up -d --pull always` (never `down -v` — that deletes the data volumes). **Keep `~/langfuse/.env` verbatim** — do NOT rotate `ENCRYPTION_KEY`/`SALT`/`NEXTAUTH_SECRET`, or existing encrypted rows become undecryptable. Back that file up alongside the volumes.
- **Claude Code** preserves `~/.claude/settings.json` across its own auto-updates (kept separate from the app install, with timestamped backups). The S4 deny rules persist.

## Watch-items (low priority, no action now)

- **Langfuse SDK v4 vs server v3 drift:** the venv SDK is 4.13.0 while the server runs v3. Trace *ingestion* works (the plugin only uses the OTEL write path, not the v4 read/metrics API), so it's fine today. When you eventually upgrade the Langfuse *server* to v4, align them. Don't leave a v4 SDK querying a v3 server long-term.
- **nexus `/api/observability`** calls the Langfuse **v3** REST endpoint (`/api/public/metrics/daily`). It fails soft. Revisit only if/when you upgrade the Langfuse server to v4.
- **Frozen bundled skill:** to un-freeze `hermes-agent-skill-authoring` (let it resume upstream updates) while keeping the path fix, copy your edit into a separate user skill, then `hermes skills reset hermes-agent-skill-authoring --restore`. Only do this if you save the edit first. Low value — that skill rarely changes.
- Optional tidy: remove the two leftover `.bak` files (`~/nexus-agent-os/server.py.bak-sec-*`, and the one inside the edited skill dir) — harmless.

## Recovery cheat-sheet

| After… | Do |
|---|---|
| `hermes update` | Nothing — everything persists. (Optionally verify: `hermes plugins list \| grep langfuse`, `hermes memory status`.) |
| Re-running the installer / venv rebuild | `bash ~/.hermes/scripts/reinstall-extras.sh` → `hermes gateway restart` (+ re-check `hermes memory status`). |
| Langfuse container upgrade | `cd ~/langfuse && docker compose up -d --pull always` (keep `.env` unchanged). |
