# Nexus Agent OS (app/)

FastAPI + SQLite agent-orchestration dashboard. The running service lives at
`~/nexus-agent-os`, a **LOAD-BEARING symlink** into this repo's `app/` — the systemd
unit, absolute workspace paths stored in nexus.db, and the venv shebangs all resolve
through it; never remove it. Run the service from `main`; use git worktrees for
experiments (a bare `git checkout` swaps the RUNNING code).

Execution engine: real Hermes Agent API sessions (localhost:8642). Voice: Piper TTS +
one shared faster-whisper STT worker. Vector store: qdrant. Local models: ollama.
Server: port 8777, HTTPS when `cert.pem`/`cert.key` exist (mic needs HTTPS off-localhost).

## File map
- `server.py` — FastAPI server: API + static frontend + JARVIS chat streaming
- `hermes_dispatch.py` — real-execution engine: kanban task → Hermes session → deliverable in `workspaces/<task-id>/`; budgets, quota, resume/harvest, framing
- `worker.py` — one lane subprocess per agent; claims ONE task at a time (atomic CAS)
- `voice.py` / `stt_worker.py` — TTS + the machine's ONE faster-whisper (killable subprocess, JSON-lines protocol, gpu-locked loads)
- `dictation*.py` — system-wide voice typing + MeetingMode (hotkey → shared STT → LLM cleanup → typed text)
- `vision.py` / `vision_worker.py` — JARVIS visual memory (SigLIP+OCR → qdrant), local VLM describe, SDXL imagine (worker killed after idle — process exit is the VRAM guarantee)
- `jarvis_brain.py` — folds ~/knowledge (business brain) into JARVIS framing per turn
- `plan_engine.py`, `autopilot.py`, `loop_engine.py`, `lessons.py`, `evals.py`, `routing.py`, `agent_memory.py`, `app_runner.py`, `project_preview.py`, `watchdog.py`, `scheduler.py`, `worktree.py`, `secrets_store.py`, `settings_registry.py` — deterministic cores of the subsystems listed below
- `static/` — vanilla JS/HTML/CSS frontend: `index.html`, `app.js` (view router + all views), `style.css` (design system v3), `nexus3d.js`, `jarvis3d.js`, vendored three.js addons in `static/vendor/`

## Hard rules
- **No build step, no npm/bundler/node_modules.** Vanilla JS/HTML/CSS via `<script>`/`<link>` only.
- **The string "three" must never appear in `index.html`** (verify.sh gate) — Three.js is dynamically `import()`ed inside `static/nexus3d.js`/`jarvis3d.js` only.
- All server data interpolated into HTML goes through `esc()`; API errors surface via `toast()`.
- Live updates patch the DOM **in place** (`tick()`/`softRender()`/`uiLocked()`) — never reintroduce blind innerHTML rebuilds on tick; they eat clicks and input focus.
- **Cache-busting:** bump `?v=N` in `index.html` when editing `app.js`/`style.css`/`jarvis3d.js` etc., or the browser serves stale code.
- **`systemctl --user restart nexus` is THE way to restart** — never nohup `start.sh` (a stray instance blocks port 8777 and bypasses the unit).
- **Manual-start posture BY DESIGN:** user units + docker.service + ollama.service are disabled at boot (docker.socket stays enabled); `nexus-up` starts the stack. Do NOT "fix" this by re-enabling units. `nexus-up` needs the `/etc/sudoers.d/nexus-stack` rule.
- **ONE kanban:** nexus.db is the single source of truth and dispatch queue; Hermes's `~/.hermes/kanban.db` is retired — never bridge or revive it.
- **Hermes-side changes ship ONLY as guardian-tracked core-mods/plugins** — never loose edits. Per-session/per-turn model choice works only through the `session-model-api-server` core-mod (upstream ignores per-session models without it).
- **12 GB VRAM is shared** (ollama + STT + vision + SDXL): idle unloading is guaranteed by killing worker subprocesses; GPU-first with CPU self-heal on real CUDA failure. Keep that discipline.
- **Z.ai 429 error 1305 = probabilistic load-shedding, not quota.** Dispatch and JARVIS chat each retry ONCE on the fallback model, then blocked_quota + backoff.
- Hermes API facts: sessions persist in `~/.hermes/state.db` and survive gateway restarts; session titles must be UNIQUE; `delegate_task` is synchronous on the api_server platform; a client disconnect does not kill a run (it finishes orphaned → harvestable).

## Subsystems — read the source-of-truth doc before touching an area
- Real dispatch / agent lanes / budgets: `SPEC-REAL-AGENTS.md`
- Judge loop (judge/screen/retry/closure): `docs/SPEC-JUDGE-LOOP.md` — holds the cascade, state inventory, settings table, and the INVARIANTS list (§11) changes must not break
- JARVIS voice/vision/avatar/deck: `docs/JARVIS-VOICE.md` (§0 is the map — read before editing JARVIS code)
- Settings v2, encrypted credentials, model registry + purpose routing: `docs/SPEC-SETTINGS-V2.md`
- Multi-user & auth: `docs/SPEC-MULTIUSER.md` · review v2 + memory galaxy: `docs/SPEC-BLOCK2.md` · replanning + eval corpus: `docs/SPEC-BLOCK3.md` · onboarding wizard: `docs/SPEC-ONBOARDING.md`
- Super Result (grounded critic), Quality Autopilot (Q1–Q7 levers), Deep Plan mode: plans archived at repo `docs/archive/` (`SUPER-RESULT-PLAN-2026-07-09.md`, `QUALITY-AUTOPILOT-PLAN-2026-07-10.md`, `DEEP-PLAN-MODE-PLAN-2026-07-10.md`)
- Implementation history, audits, and fix runbooks: repo `docs/archive/` + git log.

## Environment
- App venv `.venv/` (Python 3.14) — server + Playwright. `~/ml-env` (torch+CUDA) hosts the vision-worker deps. Model weights auto-download to the HF cache on first use; ollama needs `qwen3-vl:8b` pulled.
- Start script: `bash start.sh` (sets CUDA LD_LIBRARY_PATH, runs main.py) — but restart via systemd (rule above).
- Piper voice at `models/piper_voice.onnx`; swap via setting `voice.tts_voice` (22050 Hz .onnx; falls back to base on a bad file).

## Verify (canonical commands)
- **Static gate (every edit; pre-commit enforces):** `bash scripts/verify.sh`
- **Per-edit hook:** `.claude/check.sh` (auto-run on Write|Edit)
- **Runtime gates** (run with `.venv/bin/python`; all target `https://127.0.0.1:8777`, self-signed):
  `verify_real_dispatch_e2e.py` (GLM steps fail during Z.ai load-shedding — upstream, not the gate) ·
  `verify_agentic_e2e.py` · `verify_agentic_playwright.py` · `verify_v3_ui.py` ·
  `verify_jarvis_e2e.py` · `verify_jarvis_v2_backend.py` · `verify_stt_e2e.py` ·
  `verify_block2_e2e.py`/`_ui.py` · `verify_block3_e2e.py`/`_ui.py` ·
  `verify_onboarding_e2e.py`/`_ui.py` · `verify_feedback_e2e.py` ·
  `verify_super_result_e2e.py` · `verify_autopilot_e2e.py`/`_ui.py` ·
  `verify_deep_plan_e2e.py`/`_ui.py` · `verify_settings_e2e.py` ·
  `verify_stop_e2e.py` · `verify_phase_c_e2e.py` · `verify_mode_coherence_e2e.py` ·
  `verify_judge_loop_e2e.py`
- **Screenshot sweep:** `scripts/screenshot_all_tabs.py <suffix>` — all tabs, fails on any console error.
