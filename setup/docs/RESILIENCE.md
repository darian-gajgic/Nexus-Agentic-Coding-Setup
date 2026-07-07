# Resilience System — change protection, self-healing, reboot survival

**Guards every change from the 2026-07 hardening session against Hermes updates, accidental deletion, and reboots. Built 2026-07-05.**

Everything lives in **`~/hermes-guardian/`** — a dedicated directory *outside* `~/.hermes`, so neither a Hermes update nor the changes-under-protection can touch it, and `$HOME` survives reboots.

## 1. The change manifest — `~/hermes-guardian/manifest.json`

The authoritative, machine-readable record of every change we made, in five classes:

- **9 files** we authored (zai override plugin, `pixel_qa.py`, `mem0_dump.py`, `reinstall-extras.sh`, the `client-delivery-gate` skill, `mem0.json`, the edited `hermes-agent-skill-authoring` skill, the Langfuse + qdrant compose files) — each with a SHA-256 and a **pristine "golden" copy** in `~/hermes-guardian/golden/`.
- **12 config values** in `config.yaml` (effort=xhigh, vision model/URL, memory.provider=mem0, langfuse plugin enabled, playwright pin, pre_update_backup, the 3 re-enabled skills, fallback removed).
- **9 env-var presences** in `.env` (names only — secret values are never stored).
- **4 venv packages** (`langfuse`, `ollama`, `mem0ai`, `qdrant-client`) with pinned versions.
- **4 services + 2 containers** that must be enabled/running.

To update the manifest after an intentional future edit: `python3 ~/hermes-guardian/guardian.py --capture` (refreshes the golden copies to match the current on-disk files).

## 2. The guardian — `~/hermes-guardian/guardian.py`

A self-healing reconciler. On each run it:

- **Detects a Hermes update** by comparing the current git commit to the last-seen one (`state.json`).
- **Restores files surgically, not bluntly:**
  - files we *fully authored* (override plugin, scripts, skills, compose, `mem0.json`) → whole-file from `golden/` only if **missing** or **update-reverted** (the whole file is our content, so whole-file is the correct unit);
  - the one file where we edited only *part* of a Hermes-shipped file (the skill-authoring skill) → re-applies only our **find/replace patch** to the current file, so any upstream content is preserved and only our change is re-asserted.
- **Enforces crucial config values *surgically*** — e.g. `agent.reasoning_effort=xhigh`, `memory.provider=mem0`, the vision keys: it rewrites **only that one line** (line-level editor, not a YAML round-trip), backing up + validating + rolling back on any parse error. Every other byte of `config.yaml` — comments, indentation, personality strings — is untouched. *Proven:* drifting 5 values at once produced a 5-line diff and nothing else. Non-crucial config drift is reported, not changed.
- **Reinstalls vanished packages** into the Hermes venv (the real risk: a venv rebuild prunes `langfuse`/`ollama`, which aren't in Hermes' lockfile).
- **Enables disabled services** and **restarts down containers** (`docker compose up -d`).
- **Verifies** env-var presence and reports any missing secrets (it never stores or restores secret *values*).
- Restarts the gateway **only** if it restored something the gateway loads (a package, the provider override, `mem0.json`, or config).
- Writes a JSON report to `reports/` (only when something is noteworthy) and always updates `latest-report.json`.

**Proven:** deleting a protected file and running the guardian restored it from golden with correct permissions (`overall: RESTORED`).

**Trigger:** `hermes-guardian.timer` (systemd user timer) runs it **90 s after boot and every 15 minutes**. Each run is **verify-only by default**: drift is detected and reported (visible in Nexus) but nothing is changed. It restores automatically only when a run detects a Hermes update (the repo's git HEAD moved) reverted our mods — so an update is still caught and repaired within 15 minutes. For anything else (e.g. an accidental deletion flagged as DRIFT/MISSING), repair explicitly with `guardian.py --restore`.

## 3. Visible in the Agentic OS (nexus)

- **Guardian tab** — status, checks OK / auto-restored / problems, last-run time, whether it was a post-update run, and a run-history table. Backed by `GET /api/guardian`.
- **Memory tab** — every locally-stored mem0 memory (text + timestamp). Backed by `GET /api/memory`, which runs `~/.hermes/scripts/mem0_dump.py`.

> **Why qdrant moved to server mode:** the embedded (file) qdrant is single-process — the gateway locked it, so nexus couldn't read memories. mem0 now uses a **qdrant server** (`~/qdrant`, Docker, `localhost:6333`, `restart:always`), so the gateway *and* nexus read it concurrently. The 20 existing memories were migrated into it; the old embedded store is kept at `~/.hermes/mem0_qdrant` as a backup.

## 4. Reboot survival — everything auto-starts

| Component | How it comes back on boot |
|---|---|
| Hermes gateway | `hermes-gateway.service` (user, **enabled**, linger on) |
| **nexus** | **new** `nexus.service` (user, enabled) — previously it only started manually |
| Guardian | `hermes-guardian.timer` (enabled; also runs 90 s after boot) |
| Langfuse (6 containers) | `restart: always` + `docker.service` enabled |
| qdrant (memory store) | `restart: always` + `docker.service` enabled |
| ollama | system service (enabled) |

All user services survive logout/reboot because **linger is on**. Nothing needs a manual start after a reboot.

## Cheat-sheet

| Task | Command |
|---|---|
| Run a check now | `python3 ~/hermes-guardian/guardian.py` |
| See the last result | `cat ~/hermes-guardian/latest-report.json` (or the **Guardian** tab) |
| After you intentionally edit a protected file | `python3 ~/hermes-guardian/guardian.py --capture` |
| See what the guardian protects | `cat ~/hermes-guardian/manifest.json` |
| Timer status | `systemctl --user list-timers hermes-guardian.timer` |
| View local memories | the **Memory** tab, or `~/.hermes/hermes-agent/venv/bin/python ~/.hermes/scripts/mem0_dump.py` |

## Note

`~/hermes-guardian/` itself is not self-restoring (it can't rebuild its own scripts). It lives in `$HOME`, outside every update path, so it only disappears if you delete it manually. If you ever want it backed up too, copy the directory somewhere off-machine.
