# Nexus Agent OS — JARVIS Module

## Project Overview
Nexus Agent OS is a FastAPI + SQLite agent dashboard at /home/sinep/nexus-agent-os.
The JARVIS feature is an AI assistant interface integrated into the dashboard.
It connects to Hermes Agent API (localhost:8642) for LLM, Piper TTS for voice, and faster-whisper for STT.

## Architecture
- `server.py` — FastAPI server (port 8777, **HTTPS** — cert.pem/cert.key exist), serves API + static frontend
- `hermes_dispatch.py` — **real-execution engine (v2)**: runs a kanban task as a REAL Hermes
  API session (create session → SSE stream → deliverable files in `workspaces/<task-id>/` →
  real token usage). Budget/quota guardrails + resume/harvest live here. See SPEC-REAL-AGENTS.md.
- `worker.py` — agent-lane worker process (v2): claims ONE task at a time (atomic CAS) and
  executes it via hermes_dispatch. **The v1 simulation is gone** — no fake task strings, no
  random tokens (verify.sh enforces this). A lane exits when its agent is retired/stopped.
- `scripts/migrate_real_agents.py` — one-time migration (ran 2026-07-06): archived sim data,
  retired the SelfHealTest zombie, deleted seed demo agents/tasks, flipped dispatch.enabled=1.
- `voice.py` — TTS (Piper CPU, incl. streaming synthesize_stream) + the STT worker CLIENT:
  the machine's ONE faster-whisper (large-v3) lives in the killable subprocess
  `stt_worker.py` (JSON-lines protocol, gpu_lock'd loads, ollama eviction via _ensure_vram,
  OOM→CPU self-heal; stderr → logs/stt_worker.log). All STT callers — JARVIS mic, dictation,
  meetings — serialize on its pipe. `transcribe_pcm()` (sync) + `warm_stt()` are the entry
  points for dictation/meeting threads.
- `dictation.py` (+ `dictation_layout.py`, `dictation_overlay.py`, `dictation_meeting.py`)
  — system-wide voice typing ABSORBED FROM WisprFlow (2026-07-10, STT consolidation):
  evdev hotkey (keycode 425, two-device dedup) → segmented recording (max_seconds is a
  CHAIN boundary, never a silent cap) → shared STT → gemma3:4b cleanup on the isolated
  ollama :11435 (`nexus-cleanup-llm.service`, f16 KV) → layout-aware ydotool typing +
  tkinter overlay pill. Control socket: `$XDG_RUNTIME_DIR/nexus-dictation.sock`
  (toggle/cancel/status/meeting/note/lang). MeetingMode writes speaker-labeled transcripts
  to `~/wf-meetings` (Meetings tab reads them; supervised ffmpeg channels, temporal-overlap
  bleed dedup). Settings: `dictation.*`. `~/local-wisprflow` stays on disk as the rollback
  (re-enable wf-* units + set dictation.enabled=0).
- `vision.py` — JARVIS visual memory (SigLIP+OCR frames in qdrant `jarvis_vision`), local
  VLM describe (ollama qwen3-vl:8b), SDXL-Turbo image generation
- `vision_worker.py` — persistent ml-env subprocess hosting SigLIP/RapidOCR/SDXL (JSON-lines
  protocol; killed after 10min idle — process exit is the VRAM guarantee)
- `static/index.html` — Main dashboard HTML (grouped sidebar, inline SVG icons, toast/drawer roots)
- `static/app.js` — Frontend JS (vanilla, no build step), view router + all views
- `static/style.css` — Design system v3: glass panels over aurora backdrop, Inter UI font + JetBrains Mono for data, CSS variables
- `static/nexus3d.js` — ES module; dynamically imports Three.js from CDN and renders the dashboard 3D agent constellation (window.Nexus3D = mount/update/dispose)

## Key Design Rules
- **No build step.** All frontend is vanilla JS/HTML/CSS loaded via <script> and <link> tags.
- **Three.js must NEVER be referenced from index.html** (verify.sh gate rejects the string "three" there). It is dynamically `import()`ed inside `static/nexus3d.js` only.
- **No npm, no bundler, no node_modules.** Pure browser-side code.
- Dark theme tokens: --accent #7c5cff, --accent-2 #5eead4, --cyan #22d3ee, --bg #07070d, panels are translucent rgba glass. Fonts: --font-ui (Inter), --font-mono (JetBrains Mono), loaded from Google Fonts CDN.
- All server data interpolated into HTML goes through `esc()`. API errors surface via `toast()`.
- Live updates: tick() every 3s patches the DOM **in place** for dashboard/agents/monitor and only re-renders kanban/agentic when their data hash changes and no modal/drawer/drag is active (`uiLocked()`); WS events use `softRender()`. Don't reintroduce blind innerHTML rebuilds on tick — they eat clicks and input focus.
- The JARVIS view is rendered by `renderJarvisView()` in app.js which sets `$('#content').innerHTML`

## JARVIS v2 (2026-07-08) — particle avatar, WS TTS, vision, files, control
**Full docs: `docs/JARVIS-VOICE.md` §0 — READ IT before editing JARVIS code.**
- **Avatar (v7 hologram, 2026-07-10)**: cyan point-lattice hologram head (torso PARKED: SHOW_TORSO=false)
  (`static/jarvis3d.js`): the three.js "facecap" model (52 ARKit blendshapes, credit
  Face Cap/bannaflak.com; KTX2 texture stripped offline by
  `scripts/build_facecap_hologram.py` → `static/avatar/facecap_hologram.glb`) rendered
  as dark occluder + additive wireframe + morph-aware shader dots behind an
  UnrealBloomPass composer. Lip sync = TEXT-ALIGNED VISEMES: app.js registers a live
  per-sentence utterance record (`Jarvis3D.speak(rec, ctx)`, cleared via
  `stopSpeech()`); its Oculus-viseme timeline (vendored MIT
  `static/vendor/lipsync/lipsync-en.mjs`) is stretched over the sentence's REAL audio
  window on the AudioContext clock and gated by the live RMS envelope. Eyes =
  saccade/fixation gaze machine on rotatable eye pivots (camera/pointer tracking) +
  Trutoiu blink dynamics on eyeBlink morphs. Vendored three.js r160 addons live in
  `static/vendor/threejsm/` (single shared THREE instance — see
  `static/vendor/_VENDORING.md`). Memory galaxy renders behind, unchanged. States
  idle/listening/thinking/talking; FX button freezes the RAF loop. Wav2Lip is RETIRED
  (/talk + /lipsync return 410 Gone since 2026-07-09; lipsync.py stays on disk but
  nothing reaches it).
- **Voice out**: `/ws/jarvis/tts` streams raw PCM per sentence (`voice.synthesize_stream`);
  the browser schedules chunks gaplessly + drives the avatar mouth from an AnalyserNode on
  the same graph (native-timing lip-sync). Sentences are spoken WHILE the reply streams.
  HTTP `/api/jarvis/tts` = fallback. Voice toggle 🔊 in the topbar.
- **Voice in**: adaptive-noise-floor VAD auto-detects end of speech (1.15s hangover in CONV
  mode, 2.1s manual) and auto-sends; CONV mode adds a barge-in monitor during playback
  (echoCancellation'd mic — sustained speech stops TTS and listens).
- **Vision memory**: `vision.py` + `vision_worker.py` (persistent ml-env subprocess, killed
  after 10min idle): SigLIP so400m + RapidOCR per frame → qdrant `jarvis_vision`.
  **VRAM robustness (2026-07-08)**: the 12GB card is shared with ollama + the user's dictation
  tool; when SigLIP OOMs on CUDA, `vision_worker._siglip_op_with_fallback` drops it to CPU
  (float32) for the worker's life and reruns — "seeing" degrades to slower-but-working instead
  of a 500 (a worker respawn after idle retries CUDA). The embed ops report `device`; frame
  failures are logged to the activity feed. Mirrors the STT self-heal.
  (per-user, deduped). Webcam/screen share buttons index frames every 4-5s; hybrid search
  (`/api/jarvis/vision/search`) opens a scroll/select/copy popup; "look at this" turns ride
  a frame described by ollama `qwen3-vl:8b` into the chat as [JARVIS EYES] context.
  Z.AI has NO vision/image models on this key (1113) — vision is fully local.
- **Imagine**: `/api/jarvis/imagine` → SDXL-Turbo (sequential CPU offload, ollama VLM evicted
  first — 12GB card) → PNG in the file exchange.
- **File exchange**: `workspaces/jarvis/<uid>/files/` — sidebar drag&drop; per-turn framing
  points Hermes there; post-turn folder diff → SSE `files` event → chips in chat.
- **System control**: per-turn `system_message` gives Hermes curl access to the Nexus API via
  the per-boot `auth.INTERNAL_TOKEN` + `x-nexus-user` (user-scoped; readback-confirm rule).
  The framing documents the FULL OS surface (board+wizard, projects, deliverables, ▶ Test-app,
  judge/verify/review, approvals/scheduler/agents/quota) so JARVIS can plan-then-build or hand
  work to the fleet — not just move cards.
- **Business Brain (2026-07-08)**: `jarvis_brain.py` makes JARVIS domain-aware. Per turn it
  detects the craft domain (9 domains, keyword-scored) and folds ~/knowledge into the framing:
  always the BUSINESS-CONTEXT facts + STYLE-VOICE AI-slop kill-list (voice guardrail); on a
  deliverable-looking turn it adds the matched domain's RUBRIC must-pass gates + PLAYBOOK task
  menu + file paths (compact — full playbooks are read on demand via file tools). Files are
  mtime-cached (edits apply live). `_jarvis_framing(uid, user_input)` returns (framing, domain);
  the stream emits an SSE `domain {domain,label}` event → the topbar 📚 domain chip.
- **Command deck (2026-07-08)**: topbar ⚡ Deck toggles a right rail (`jarvisLoadDeck`) with a
  board glance (column counts + running, click→kanban), recent Deliverables each with **▶ Test**
  (reuses `testAppUI` → per-task app preview) + open-file, pending Approvals (✓/✗), and a
  "✨ Hand a task to the fleet" (→`describeTaskUI`). Persisted open state (`jvDeckOpen`); refreshes
  on open, on the `files` SSE event, and after approval decisions.
- **Sessions**: multiple per user (`jarvis_session.json` history) — sidebar switch/forget/title.
- **Overload fallback (2026-07-08)**: Z.AI load-sheds the chat model at peak → server emits
  `event: fallback {from,to}` + retries the turn ONCE on `dispatch.fallback_model`
  (default glm-5-turbo) in the SAME session via per-turn model override; the chat shows a
  ⚡ note. Details in docs/JARVIS-VOICE.md §5 + the Real Dispatch quota bullet below.
- **Extras**: daily spoken briefing, spoken task completion/failure callbacks (12s polling),
  `/find` + `/imagine` intents (typed or spoken), per-message copy buttons.
- **STT consolidation (2026-07-10)**: ONE whisper for the whole machine. `stt_worker.py`
  (spawned by voice.py, app venv) owns faster-whisper **large-v3 int8_float16 (~2GB)**;
  JARVIS mic, system dictation and meetings all go through it. GPU-first: loads wait up to
  45s on the cross-process gpu_lock (the GPU waiting line), evict idle :11434 ollama models
  when VRAM is short (`_ensure_vram`), and only fall back to CPU on a real CUDA failure
  (worker flips to CPU for its life + parent blocks CUDA spawns 600s). Warm-on-mic-press /
  warm-on-hotkey (`POST /api/jarvis/stt/warm`, `voice.warm_stt()`) hides the ~4-8s cold
  load. Settings: `voice.stt_model|stt_device|stt_compute|stt_language|stt_idle_timeout`.
  WisprFlow's adaptive GPU↔CPU demote loop was deliberately NOT ported — its two
  disagreeing probes thrashed placement every ~10s and OOM-killed the old daemon
  (journal-proven 2026-07-08). The user's WisprFlow services (wf-daemon/wf-keylistener/
  wf-cleanup-llm) are disabled; `wf-cleanup-llm` was renamed → `nexus-cleanup-llm.service`
  (same ~/.ollama-wf models dir, keep_alive 5m→2m).
- **Idle model unloading (all guaranteed):** the STT worker is **killed** after
  `voice.stt_idle_timeout` (300s) of STT inactivity — process death reclaims 100% of VRAM
  incl. the ~158MiB CUDA context; Piper drops after 300s of TTS inactivity (timers are
  SEPARATE since 2026-07-10 — CPU TTS use no longer pins the GPU whisper); the vision
  worker is killed after `vision.idle_timeout` (default 600s); all via the server's 15s
  unloader thread. **The ollama VLM (qwen3-vl, ~6-8GB) frees promptly:** describe calls
  use a short keep_alive (setting `vision.vlm_keep_alive`, default 60s); SDXL imagine
  evicts the VLM first (keep_alive:0). (`vision.unload_vlm()` exists but has no chat-turn
  call site — VLM VRAM is freed by keep_alive expiry, not per-turn eviction.) Dictation's
  cleanup gemma3:4b frees after 2m (`dictation.llm_keep_alive` + the unit's
  OLLAMA_KEEP_ALIVE).
- **Graceful shutdown (2026-07-08)**: the dashboard always holds a `/ws` socket + SSE streams,
  so uvicorn's default unbounded graceful shutdown hung until systemd's 90s SIGKILL (every
  restart lost in-flight state + spammed the journal). Fixed: `uvicorn.Config(timeout_graceful_
  shutdown=8)` + a `handle_exit` that sets `watchdog.SHUTTING_DOWN` FIRST (so the watchdog stops
  respawning SIGTERM'd workers mid-stop) + `TimeoutStopSec=25` in the unit. Restart is now ~1s.
- **Cache-busting:** when editing `app.js`, `style.css`, `jarvis3d.js` etc., bump `?v=N` in
  `index.html` or the browser serves stale cached code.
- TTS voice: swappable via setting `voice.tts_voice` (path to a 22050 Hz Piper .onnx; empty =
  base `models/piper_voice.onnx` = ryan-medium, the always-present fallback). Higher-quality
  US-male voices downloaded to `models/voices/` (gitignored — re-downloadable): **en_US-joe-medium**
  (currently active — calm, deeper), en_US-ryan-high (confident, clear), en_US-lessac-high
  (professional/neutral). `voice._get_tts` reloads on change
  and falls back to the base voice if the file is missing/broken/non-22050. Comparison samples:
  `~/.hermes/cache/voice-samples/*.wav`. Backup of old female voice at
  `models/piper_voice_female_backup.onnx`. SOTA upgrade path (Kokoro-82M, more natural) is a
  separate python3.11 worker — blocked on the 3.14 venv; see `jarvis-tts-kokoro-py314-blocker`.

## Python Environment
- Venv at `.venv/` (Python 3.14) — the nexus server + Playwright for tests
- `~/ml-env` (torch+CUDA) additionally needs: transformers sentencepiece protobuf safetensors
  diffusers accelerate rapidocr-onnxruntime onnxruntime (JARVIS vision worker; installed
  2026-07-08). Model weights auto-download to `~/.cache/huggingface` on first use
  (SigLIP so400m ~3.3GB, SDXL-Turbo ~7GB); ollama needs `qwen3-vl:8b` pulled.
- Start server with `bash start.sh` (sets LD_LIBRARY_PATH for CUDA, then runs main.py)
- HTTPS: if `cert.pem` + `cert.key` exist, server auto-enables HTTPS (needed for mic on non-localhost)
- Piper TTS model at `models/piper_voice.onnx`
- faster-whisper (large-v3) runs in the `stt_worker.py` subprocess (app venv); CUDA libs
  preloaded from `/usr/local/lib/ollama/cuda_v12/` + LD_LIBRARY_PATH (start.sh / _worker_env)
- Dictation deps in the app venv: sounddevice + evdev (requirements.txt); the overlay needs
  a tkinter-capable python (apt `python3-tk`; auto-probes fallbacks incl. the old wf venv)

## Test / Verify (canonical commands)
- **Static gate (fast, every edit):** `bash scripts/verify.sh` — JS/Python syntax, no debug leftovers, function integrity, Agentic capabilities integrity, + real-dispatch/judge/health integrity incl. sim-is-dead negatives (the gate prints its own count — 256 checks as of 2026-07-09). Must pass before commit; the git pre-commit hook enforces it.
- **The server runs as a systemd user unit:** `systemctl --user restart nexus` is THE way to
  restart it (unit: ~/.config/systemd/user/nexus.service → start.sh). Don't nohup start.sh
  manually — a stray instance blocks port 8777 and bypasses the unit.
- **Runtime gate — REAL dispatch (v2):** `.venv/bin/python scripts/verify_real_dispatch_e2e.py` — spawns a real lane, drives a task through a REAL Hermes `api_*` session (claim → queue → worker executes → deliverable file + tokens + transcript), budget block, injected-429 quota block + auto-retry, kill-worker→resume, retire→no-respawn. GLM-dependent steps fail while Z.ai load-sheds (error 1305) — that's upstream, not the gate.
- **Runtime gate — API (integration):** `.venv/bin/python scripts/verify_agentic_e2e.py` — exercises all 9 agentic endpoints (claim/verify/approvals/memory/scheduler/cost/messages/worktree) via HTTP. 30 checks.
- **Runtime gate — UI (Playwright):** `.venv/bin/python scripts/verify_agentic_playwright.py` — loads the Agentic view in a real headless browser, asserts all subsystem cards render, exercises the approval + scheduler flows from the UI, captures console errors. 11 checks. This catches frontend↔backend contract drift the static gate cannot.
- **Runtime gate — v3 UI features:** `.venv/bin/python scripts/verify_v3_ui.py` — agent detail drawer (memory/messages/cost tabs + add/delete memory), kanban task create/edit/delete + search filter, memory-hub subtabs, specialists learning pipeline, watchdog config modal, JARVIS still boots. 24 checks.
- **Screenshot sweep:** `.venv/bin/python scripts/screenshot_all_tabs.py <suffix>` — screenshots all 14 tabs to `~/.hermes/cache/screenshots/nexus-<suffix>/`, fails on any console error.
- All runtime scripts target **https://127.0.0.1:8777** (self-signed → `verify=False` / `ignore_https_errors=True`).
- **Runtime gate — JARVIS (v2):** `.venv/bin/python scripts/verify_jarvis_e2e.py` — full Playwright
  run: v2 layout + particle avatar canvas render, live reply streams (SSE), WS TTS engages
  (SPEAKING state), vision popup from a chat intent, returns to idle. Tolerates Z.AI load-shedding.
- **Runtime gate — JARVIS v2 backend:** `.venv/bin/python scripts/verify_jarvis_v2_backend.py` —
  23 checks: frame indexing (SigLIP+OCR, dedup), hybrid search ranking, VLM describe, SDXL
  imagine, file exchange, sessions v2 (fresh/switch/foreign-404/title), briefing, events,
  WS TTS streaming + first-chunk latency. Self-cleaning.
- **Runtime gate — STT consolidation:** `.venv/bin/python scripts/verify_stt_e2e.py` —
  21 checks: TTS→STT round trip through the shared worker, warm endpoint, SIGKILL→respawn,
  idle-kill frees ALL whisper VRAM, cpu-force round trip, dictation/meetings API + filename
  validation. Self-cleaning (settings PATCHed back). Dictation smoke without the hotkey:
  `printf status | nc -U "$XDG_RUNTIME_DIR/nexus-dictation.sock"` (toggle/cancel/lang/note).
- **Runtime gate — Block 3 (replanning/evals/plan-editor):** `.venv/bin/python scripts/verify_block3_e2e.py` —
  revalidate round-trip, replan detect→dismiss→re-arm→apply (archival, rewiring, loop reset,
  approval expiry), eval run lifecycle on a scratch corpus with stubbed generation+judge,
  per-user isolation. 33 checks, self-cleaning.
- **Runtime gate — Block 3 UI (Playwright):** `.venv/bin/python scripts/verify_block3_ui.py` —
  drives the plan editor inside the proposal modal (edit/add/revalidate without creating),
  the replan review modal, and the Specialists→Evals tab. 15 checks.
- **Runtime gate — Block 2 (review v2/memory edit/PR):** `.venv/bin/python scripts/verify_block2_e2e.py` —
  review JSON line numbers + Pygments highlight, comment CRUD + cross-user 404, retry
  consumes comments, memory edit/merge/delete on seeded qdrant probes (re-embed proof,
  tag preservation, ownership), PR flow against a scratch repo + local bare origin with
  stubbed gh (settings pr.cmd, restored), code map in framing. 48 checks, self-cleaning.
  Needs qdrant + ollama up (both local, always on).
- **Runtime gate — Block 2 UI (Playwright):** `.venv/bin/python scripts/verify_block2_ui.py` —
  review modal (gutters, highlight spans, unified⇄split toggle, line-comment composer,
  retry-with-feedback button), memory modal confirm-gating, Create-PR button. 21 checks.
- **Runtime gate — Onboarding (SPEC-ONBOARDING):** `.venv/bin/python scripts/verify_onboarding_e2e.py` —
  37-slot schema + explanations, per-user answers (save/resume/un-answer/isolation), apply
  renders + git-commits (dirty-tree snapshot first), owner→canonical vs member→overlay,
  per-user framing paths. 27 checks; runs on a scratch knowledge root (settings
  onboarding.root, restored), owner's real answers backed up.
- **Runtime gate — Onboarding UI (Playwright):** `.venv/bin/python scripts/verify_onboarding_ui.py` —
  CTA banner, welcome step, section explanations, auto-save on Next, n/a toggle, review
  counts, confirm-gated apply → success, Settings entry. 12 checks.
- **Runtime gate — Super Result:** `.venv/bin/python scripts/verify_super_result_e2e.py` —
  stubbed-critic e2e against the LIVE sweep (takes minutes): critic run → source/anchor
  validated auto-comments → retry drain → closed auto-round → convergence + round-cap
  escalations → SHIP quiet-stop → open-mode checkpoint + approve/reject → workflow cascade
  → revalidate reconciler/multi-review repair. ~27 checks, self-cleaning, restores
  super.critic_cmd.
- **Runtime gate — Quality Autopilot:** `.venv/bin/python scripts/verify_autopilot_e2e.py` —
  36 checks, mostly deterministic + a stubbed distillation: Q7a preset derivation (rules
  1/2/4/6, P2 staged), design_loop derivation + the rule-2 risk floor, Q4 decision-log
  harvest/injection, Q5 [UNSURE] framing/tools, Q1 exemplar selection + guards (L3),
  Q2 stubbed distill → admin lesson card → apply (canonical + L2 overlay), L1 outcome
  capture + L4 fingerprint invalidation + rule-9 collapse monitor, Q7b auto-approve-ship
  guard + /api/decisions, rule-5 Eco collapse + high-stakes re-insertion, rule-7 scheduler
  template. Self-cleaning; restores settings.
- **Runtime gate — Settings v2 (SPEC-SETTINGS-V2):** `.venv/bin/python scripts/verify_settings_e2e.py` —
  settings schema/registry round-trip, encrypted credential store (masked responses, plaintext
  never leaves the API, per-user isolation), machine-default key view/rotation (scratch env
  file — never the live .env), model registry CRUD + purpose-routing validation, task-model
  validation, session-keys bridge, judge model/env plumbing via stubbed judge.cmd.
  62 checks, self-cleaning, multi-user-preserving.
- **Per-edit gate:** `.claude/check.sh` (auto-run by Claude Code PostToolUse on Write|Edit).
- Playwright is installed in `.venv`. Screenshots save to `~/.hermes/cache/screenshots/`.

## Settings v2 (2026-07-08, docs/SPEC-SETTINGS-V2.md is source of truth)
- `settings_registry.py` = declarative registry of every operational setting (defaults =
  historical behavior; env-backed entries resolve setting → env → default via `sreg.conf`).
  `GET /api/settings/schema` renders the whole Settings tab generically; `_SETTINGS_PREFIXES`
  derives from the registry. PATCH with `""` = back-to-default (registry keys pin the default
  explicitly — code-site fallbacks differ; env-backed/unmanaged keys clear the row).
- `secrets_store.py` = first at-rest crypto: per-user + global credentials Fernet-encrypted in
  nexus.db (master key `secret.key`, 0600, gitignored). NO endpoint ever returns a stored
  secret — metadata + 4-char hint only. Missing credential = the machine's env/CLI default key.
- **Machine default keys** (admin): `GET /api/credentials/defaults` (masked set/hint status) +
  `PUT /api/credentials/defaults/{provider}` rotate `~/.hermes/.env` in place (fixed
  provider→env allowlist in `secrets_store.DEFAULT_PROVIDERS` — never arbitrary env names;
  anchored rewrite incl. `# [disabled…]`-commented lines, atomic 0600, live os.environ update).
  zai/brave apply to new Hermes work after a gateway restart; anthropic's default is the
  Claude CLI subscription auth (rotate via `claude` login, not env).
- **Model registry**: `user_models` (global NULL-user rows + per-user rows) + `model_assignments`
  (purposes: complicated / easy / mechanical / frontier_judge; 'global' scope = inherited
  default). Seeded once (empty-table check): the GLM trio + `anthropic/claude-opus-4-8`
  route=cli as frontier judge. Routing is APPLIED end-to-end: task create/patch validate against
  `db.task_models_for(uid)`, dispatch/JARVIS/wizard/eval sessions run
  `resolve_task_model`/`default_task_model`, the wizard's model guidance + dev-stage floor use
  the owner's assignments, and the judge resolves `evals.judge_model_for(owner)`.
- **Per-user API keys at execution**: dispatch publishes `~/.hermes/session-keys.json` (0600,
  same bridge pattern as model-efforts.json); the guardian-tracked zai override plugin turns an
  entry into a per-request `Authorization` header (absent entry = env `GLM_API_KEY`). Judge gets
  `JUDGE_MODEL` + `JUDGE_ANTHROPIC_API_KEY` env (cjudge honors both; unset = subscription auth).
  Caveat: Hermes AUXILIARY calls (title gen, compression) still bill the machine key.
- Hermes-side files touched (keep guardian + vendored copies in sync — ship-flow step 4):
  `~/.hermes/plugins/model-providers/zai/__init__.py`, `~/.local/bin/cjudge`, and the
  `session-model-api-server` core-mod on
  `~/.hermes/hermes-agent/gateway/platforms/api_server.py` (guardian patch + sentinel).

## Real Dispatch (v2 — added 2026-07-06, SPEC-REAL-AGENTS.md is source of truth)

The Agents fleet is now the REAL execution layer of Hermes — the v1 simulation is deleted.
- **Agent = executor lane**: a `worker.py` subprocess per agent row; claims one task at a
  time; opens ONE fresh Hermes session per task (`nexus:<task-id>`, an `api_*` session id);
  streams the work (SSE → live preview, tool events → activity feed, `run.completed` → real
  token counts); writes `workspaces/<task-id>/deliverable.md` (+ `_dispatch.json` audit).
- **Dispatch is queue-only**: `POST /api/tasks/{id}/dispatch` claims + marks `queued`; the
  lane worker is the SOLE executor (no server-thread execution — race designed out).
  Feature flag: settings `dispatch.enabled` (now default ON). Budgets: settings
  `dispatch.default_task_budget` (1M) / `dispatch.daily_cap` (10M) / per-task `budget_tokens`.
- **dispatch_state lifecycle** (orthogonal to kanban columns): none → queued → dispatching →
  streaming → finalizing → completed | failed | blocked_budget | blocked_quota.
- **Self-heal resumes, not restarts (R3)**: dead worker → watchdog respawns it → new worker
  harvests the orphaned-but-finished Hermes run from session history (free), else sends a
  continue-turn into the SAME session; fresh re-dispatch only if the session is gone.
- **`retired` is a terminal agent status** — watchdog never touches it (`POST
  /api/agents/{id}/retire`). This is how the SelfHealTest zombie ended (10,954 respawns).
- **ONE kanban**: Nexus's (nexus.db) is the single source of truth + dispatch queue.
  Hermes's `~/.hermes/kanban.db` is RETIRED (was empty; its toolset is disabled) — do not
  bridge or revive it.
- **Quota reality**: Z.ai 429 error 1305 = probabilistic load-shedding at peak, NOT quota
  exhaustion. First strike on a task's model → **overload fallback** (settings
  `dispatch.fallback_enabled`/`dispatch.fallback_model`, default glm-5-turbo): the dispatch
  retries ONCE on the fallback model in a fresh session (`fallback_model_for` /
  `run_task_dispatch(fallback_model=…)` in hermes_dispatch.py). Only when the fallback is
  overloaded too: blocked_quota + exponential backoff (settings
  `dispatch.quota_backoff_until`, `dispatch.quota_consecutive`); test injection knob
  `dispatch.force_429` (429s BOTH passes, so the gate still sees blocked_quota).
  **JARVIS chat has the same fallback** (same two settings): a load-shed signature before
  any streamed content → `event: fallback {from,to}` to the browser + ONE retry in the
  SAME session as a per-turn model override (server.py `jarvis_chat_stream` /
  `_jarvis_overload_signature`); test knob `jarvis.force_429=1` sheds the primary pass
  without sending it (the fallback pass runs for real).
- **Session models are honored ONLY via our guardian core-mod** (`session-model-api-server`,
  added 2026-07-08): upstream's api_server platform ignores the per-session `model` for
  session-chat turns — every turn silently ran config.yaml's default (journal-verified:
  100% glm-5.2 before the mod, so per-task models/pools were cosmetic until then). The mod
  makes turns run the session's stored model AND accepts an optional per-turn body
  `model` override on `/api/sessions/{id}/chat[/stream]` (what JARVIS fallback uses).
  Gateway restart applies it; guardian re-asserts it after Hermes updates.
- Hermes API facts (verified against source): sessions persist in `~/.hermes/state.db` and
  survive gateway restarts; `delegate_task` is SYNCHRONOUS on the api_server platform;
  client disconnect does NOT kill a run (it finishes orphaned → harvestable); per-request
  `system_message` = ephemeral framing; **session titles must be UNIQUE** (create_session
  retries with a `~hex` suffix on collision). Hermes-side changes ship ONLY as
  guardian-tracked core-mods/plugins — never loose edits.

### v2.1 additions (2026-07-06, user-testing round 3)
- **Workflows (= "Projects" in the UI, nav `data-view="workflows"`)**: `workflows` table +
  `tasks.workflow_id`/`tasks.depends_on` (JSON id list). A task runs only when all
  dependencies are `done` (worker skips claiming; manual dispatch 409s); done predecessors'
  `deliverable.md` paths are injected as INPUT into the dispatch framing. Endpoints:
  GET/POST/PATCH/DELETE `/api/workflows(/{id})`. Example-campaign creator in the UI.
- **Deliverables tab** (nav `data-view="deliverables"`): `GET /api/deliverables` aggregates
  every task's workspace files; inline .md preview; follow-up chaining sets a real dependency.
- **Per-model concurrency slots**: Z.ai allows ~10 concurrent PER MODEL, Hermes 10 total.
  `hermes_dispatch.slot_available()/slots_in_use()` count live dispatches (fresh heartbeats);
  workers WAIT instead of erroring. Settings: `dispatch.max_concurrent_per_model` (8),
  `dispatch.max_concurrent_total` (8). `/api/quota` exposes `in_flight` per model.
- **Per-task model** (`tasks.model`): glm-5.2 default / glm-5.1 / glm-4.5-air — session is
  created with that model; lighter tasks use a separate concurrency pool. (Actually
  effective only since the `session-model-api-server` core-mod, 2026-07-08 — before it,
  upstream ran every session turn on the config default regardless.)
- **Skill wizard**: `/api/hermes-skills` list/get/save + `/api/hermes-skills/wizard` (AI
  drafts SKILL.md → human reviews → save writes `~/.hermes/skills/<name>/SKILL.md`).
  Specialist wizard: `/api/specialists/wizard` (same pattern; eval gate on save stays).
- **App preview (v3.5)**: ▶ Test a task's program output live. app_runner.py detects the
  runnable in the workspace (package.json dev/start → npm install+run; app.py/main.py
  (+requirements→.venv-preview) → python; index.html → python -m http.server), runs it as
  its own process group on a dedicated 127.0.0.1 port (8790-8820, max 3 concurrent, env
  marker NEXUS_PREVIEW=1 for pid identity), logs to <ws>/_preview.log, auto-stops after
  30 min (reaper thread also kills restart-orphans; registry workspaces/.preview-apps.json).
  Endpoints: GET/POST /api/tasks/{id}/app(/start|/stop|/log). UI: ▶ Test app in the
  Deliverables rows + task detail → modal with live log → opens the app in a new tab when
  it answers. Port truth (v3.4): vite dev scripts get `-- --port <p> --strictPort --host
  127.0.0.1` appended (vite ignores the PORT env and a busy config port auto-increments);
  any other server that ignores PORT is adopted from the URL it prints in its log —
  `_adopt_logged_port` rewrites the registry port/url once that port answers.
  Full stack (v3.5): a node frontend with a python/ASGI sibling (pyproject/requirements
  naming fastapi|uvicorn) gets the backend started in the SAME process group — on the port
  the frontend's proxy config targets (vite server.proxy / CRA proxy, default 8000), env
  seeded from the project's own .env(.example), alembic migrations run first, `[backend]`-
  prefixed lines in the same live log; status carries backend_port/backend_ready. Compose
  infra (image-only services: db, mail, …) comes up via the project's own docker-compose.yml
  (`up -d --wait`); a declared host port held by a FOREIGN container (e.g. langfuse holds
  3000+5432 here) is remapped through a patched copy `_preview.compose.yml` and the env
  URLs rewritten to match. Infra containers persist across previews (stop kills only the
  process group) — concurrent old/new states of one project SHARE backend + db by design
  (second state finds the proxy port answering and doesn't start its own).
- **Project app preview (v3.6)**: ▶ Test project — run the WHOLE assembled project (every
  stage's changes together, not one task's output), at the current state OR any earlier one,
  side by side on separate ports to compare new vs old / spot regressions. `project_preview.py`
  resolves the project's runnable history two ways: REPO projects (member tasks carry
  repo_path) → the shared task branch nexus/<wf-slug>; states = commits from `merge-base..branch`
  (the project's own commits, so a big repo's history never buries them) + the fork-point
  "baseline" anchor; materialize = `git archive <sha>` (read-only on the repo, cached since
  commits are immutable). WORKSPACE projects → states = DONE member tasks in completion order;
  state vK = overlay of the first K task workspaces (later stages overwrite same-named files,
  each deliverable.md collected into _deliverables/); fingerprint-cached by contributing tasks'
  updated_at so a repeat start reuses the built copy (keeps npm install / .next) and only
  rebuilds when a stage was retried. Every state materializes into a DISPOSABLE dir
  (workspaces/workflow-<id>/_project_preview/<key>/state) and runs via the SAME app_runner
  (registry key wf:<id>:<state>, so old+new run concurrently under the 3-app cap / 30-min TTL /
  reaper); the live worktree + task workspaces are NEVER run in place or mutated. State keys
  come only from list_states — membership is the injection gate (no arbitrary git revs / paths).
  Endpoints: GET/POST /api/workflows/{id}/app(/start|/stop|/log) ({version} body). UI: ▶ Test
  project on the project card + inside its panel → modal with a state picker, running-states
  list (each with Open/Log/Stop), live log, Stop-all. Non-runnable states (spec-only stages,
  the bare init commit) return a clean 409.
- **Looping (v3.2)**: per-task and per-project improve-and-recheck loops.
  `tasks.loop_config` / `workflows.loop_config` (JSON: enabled, mode open|closed,
  preference quality|speed, auto_judge, triggers[] with per-trigger max_rounds/used).
  `POST /api/loop/design {kind, id?|meta, preference, mode}` — DETERMINISTIC designer
  (loop_engine.design_loop, no LLM): inspects the item's real shape (verifier stage?
  domain rubric? high-stakes?) and emits the config + plain-language reasoning.
  RUNTIME: loop_engine.loop_engine_thread (started like the watchdog) sweeps every 20s;
  closed mode only: verify-FAIL on a looped project → retry fix task with the verifier's
  findings + re-verify; judge REVISE/REWRITE on this deliverable version → auto-retry
  (judge findings auto-attach); quality mode auto-runs the judge on fresh high-stakes
  deliverables. Bounded: per-trigger round caps (regenerating resets them), 3 actions per
  sweep, budgets still apply. Open mode = engine does nothing (checkpoints wait for the
  human — the pre-v3.2 behavior, now an explicit choice). UI: enable + quality/speed
  cards in task-create and wizard project modals; 🔁 View/edit loop in task/project
  detail opens the loop modal (flow diagram, trigger cards with round counters,
  reasoning, open↔closed switch, regenerate, disable).
- **Attachments (v3.1)**: operators attach input files (pdf/office/images/text, ≤25 MB)
  to a task (`workspaces/<task-id>/attachments/`) or a whole project
  (`workspaces/workflow-<id>/attachments/`) via the task-detail / project-detail modals;
  endpoints `GET/POST/DELETE /api/{tasks|workflows}/{id}/attachments(/{name})`. Dispatch
  framing lists them as MUST-READ input; extraction + binary OUTPUT formats (pdf, docx,
  xlsx, pptx, png) run through the nexus `.venv` python, which has python-docx, openpyxl,
  python-pptx, reportlab, pypdf, pillow, markdown preinstalled. Since 2026-07-08 the
  project modal has an "Attach to" target picker (project-wide vs ONE member task) with
  per-task placement groups, every upload spot takes multi-file + drag & drop
  (`attachWire`/`attachUploadFiles` in app.js), and the task modal shows inherited
  project-wide files read-only. Files can also be staged at CREATION time (task-create
  modal incl. single-task wizard output → the new task; wizard project proposal →
  project-wide): `attachStage*` helpers hold File objects in memory and upload right
  after Create returns the new id — a cancelled form never leaks its staged files.
- **Task wizard** (v3): `POST /api/tasks/wizard {instruction, answers?}` — two-phase.
  Phase 1 may return `{type:"questions"}` (ONE round, ≤6 — ask-when-in-doubt; each option carries pros/cons + a ★ recommended best-practice pick; unknowns that change the
  plan's SHAPE — stack/platform, acceptance criteria, real-money blast radius; every
  question carries a default so it is skippable). Phase 2 (body has `answers`) must return
  a plan; a second questions reply is retried once with defaults, then 502.
  Plans carry `assumptions` (also embedded into the description / task 0) and `repairs`.
  CODING GOALS get the house pipeline template: spec&plan (tech-lead-orchestrator) →
  implement+tests (code-implementer) → code review (code-reviewer) → fix findings
  (code-implementer, NO-OP if review clean) → acceptance verification (acceptance-verifier,
  high_stakes ALWAYS). `_repair_workflow()` then deterministically enforces it: whitelists
  specialists against the live roster, forces glm-5.2 on dev stages, inserts missing
  review/fix/verify gates (append-only → acyclic by construction), moves the verifier to
  the end as unique sink, chains orphans, and falls back to a sequential chain on any
  repair error. Non-coding: research→create (2-3 tasks) or single task; the frontier judge
  is the review stage for high-stakes content — no extra review task.
  UI entry points: Kanban "✨ Describe a task", Projects "✨ Describe a goal"; the proposal
  modal shows stages (parallel tasks grouped), assumptions, auto-repairs, and lets the
  operator untick optional tasks (quality gates are locked; skipped tasks are spliced out
  of the DAG so dependents inherit their dependencies).

### Super Result (2026-07-10, SUPER-RESULT-PLAN-2026-07-09.md is source of truth)
- **Grounded quality loop**: flag `super_result` on a task/workflow (wizard ✨ toggle, task
  create/detail, project modal, or API) and every fresh deliverable is re-verified by a
  GROUNDED CRITIC — the frontier-judge model running `cverify` (~/.local/bin, vendored
  setup/bin/) with FULL tool access inside a DISPOSABLE sandbox copy of the evidence
  (`workspaces/_critic/<task>-r<N>-<hex>`: workspace copytree + `git clone --local` with
  origin removed for repo tasks; secrets-scrubbed env; deny rules for push/remote/gh/sudo).
  The critic re-reads sources, re-runs quoted commands, and emits sentinel-fenced JSON
  (verdict/findings/contradictions/missing/revision_brief/learning_note).
- **Auto-comments → rework**: findings land as line-anchored `review_comments`
  (`source='critic'`, supersede-then-insert per round, anchors validated ±2 against the
  real file); `_retry_task` drains them (tags [CRITIC]/[JUDGE]/[REVIEWER], fb cap 16k) with
  the revision brief. The loop engine (`_sweep_super_result`, 20s) runs critic → closed
  auto-retry / open checkpoint → SHIP quiet-stop | convergence (`keys ⊆ prev`) | round cap
  | error → `super_result` approvals (reject=rework+round bump, approve=accept). The
  `super_result` trigger REPLACES judge_revise/auto_judge in the loop design (§4.5).
- **Fan-out (planning-time)**: wizard body `super_result:true` (+`fanout`, defaults
  `super.fanout_default`) shapes the plan per goal family — analysis: N lens-investigators
  + reconciler; coding: 2 parallel lens reviewers (never parallel impls); content/research:
  2 drafts + synthesis. `_repair_workflow` enforces the reconciler + multi-review wiring.
- **State**: `tasks.critic_*` columns (separate from `judge_*` BY DESIGN — §4.1),
  `tasks/workflows.super_result`, `deliverable_type` (analysis|code_change|content|research
  — drives the type rubric `~/knowledge/rubrics/INVESTIGATION.md` for the judge too, N1).
  Settings section `super.*` (critic_cmd is the gate stub hook, max_rounds, timeout_s,
  max_findings, fanout_*, keep_sandbox). Critic runs bill the Claude CLI subscription, NOT
  the GLM budget counters (B7 note) — Usage under-reports SR cost by design.
- **Cost**: ~5–10× a single pass. Default OFF; per-task/workflow opt-in.

### Quality Autopilot (2026-07-10, QUALITY-AUTOPILOT-PLAN-2026-07-10.md is source of truth)
Phase 3 of the quality program — compounding quality levers + full automation.
- **Q1 golden exemplars** (`hermes_dispatch.golden_exemplars`): the operator's own SHIP'd,
  high-scoring past deliverables injected as MUST-READ few-shot paths (content/research/
  analysis only; never code; L3 age-out). **Q4 decision log**: workflow members read a
  running `workspaces/workflow-<id>/DECISIONS.md` and end with a `## Decisions` section that
  `_finalize_result` harvests (deterministic). **Q5 uncertainty tagging**: executors mark
  unverified claims `[UNSURE: reason]`; the critic/judge check those first (unmarked-false =
  critical). **Q3 acceptance-tests-first**: the spec stage owns an executable `acceptance/`
  suite + hashes; `_repair_workflow._apply_tests_first` binds it (`pipeline.tests_first`).
- **Q2 edit distillation / N8** (`lessons.py` + vendored `cdistill`): `edit_evidence` table
  captures rejections + user comments + rejected→accepted diffs; a cron/manual judgment-tier
  call proposes ≤5 PLAYBOOK/RUBRIC/STYLE-VOICE deltas → ONE admin-scoped `lesson_deltas`
  approval → apply writes `~/knowledge` + git-commits (autonomy ceiling). L2 routes
  canonical vs user_overlay.
- **Q7a autopilot** (`autopilot.py::derive`): two axes — `autopilot` (full_auto/assisted/
  manual) × `spend_profile` (eco/optimal/smart) — columns on tasks+workflows, set every
  downstream knob (preference, mode, SR, fan-out, round caps, judge scope, budget ×0.5/1/2,
  pipeline depth). Guardrail rules 1–10 enforced (risk is an independent hard floor; forward
  deps P2-staged). **Q7b Decision Inbox**: `GET /api/decisions` — one card list (headline/
  recommendation/reasons/cost), unified `decBadge`, `autopilot.auto_approve_ship_hours` (Full
  Auto SHIP only, never high-stakes/SR). **Q7c**: house metaphor (worker/inspector/foreman/
  planner/you=client) + `?` explainers + manual sections.
- **Learning loop**: L1 `routing_outcomes` + `routing.sweep_stats` (no-LLM threshold proposals
  + rule-9 collapse monitor); L4 `learned_params` fingerprint-invalidated on tier rotation.
- **N5** `judge.auto_scope=all_quality`, **N6** `replan.auto_draft`, **N7** `judge.on_blind_reject`,
  **B4** `scheduled_jobs.task_template` (SR/type/preset passthrough).
- Settings section `quality` + `judge.auto_scope`/`on_blind_reject`. Gate:
  `scripts/verify_autopilot_e2e.py`. Deep Plan + Appendix C + Phase-8 benchmarks are LATER phases.

### Block 3 (2026-07-08, docs/SPEC-BLOCK3.md is source of truth)
- **Plan editor in the proposal modal (R1)**: every wizard-proposed task is editable in place
  (title/brief/specialist/domain/model/stakes/budget/deps — deps only from EARLIER tasks, so
  the DAG stays acyclic in the UI), tasks can be added/removed, quality gates stay locked.
  An EDITED plan goes through `POST /api/tasks/wizard/revalidate` (same `_repair_workflow`,
  `max_raw=7`) before creation; repairs re-render for one more confirm. Shared editor
  functions `planEd*` in app.js are reused by the replan review modal.
  `GET /api/specialists/names` = light roster for pickers (no qdrant scroll).
- **Mid-run replanning (R2)** — three separate gates BY DESIGN: (1) the loop engine only
  DETECTS (`_sweep_replan_detection`: terminal `dispatch_state='failed'`, or verifier FAIL
  with no automatic fix round left) and flags `workflows.replan` (JSON status
  needed/drafting/proposed/applied/dismissed); (2) DRAFTING is operator-triggered
  (`POST /api/workflows/{id}/replan/draft`, judge-style background thread; boot resets
  orphaned `drafting`→`needed`); (3) APPLY (`.../replan/apply`) is operator-approved after
  editing in the plan editor — refuses while a stage executes (409), archives superseded
  non-done tasks (`status='archived'`: kept for audit, excluded from rollups/board/engine),
  creates recovery tasks in Backlog (roots inherit every DONE task as INPUT deps), expires
  stale approvals, resets loop rounds. Dismissed failures don't re-flag; a NEW failed task
  re-arms. The engine NEVER rewrites a pipeline itself.
- **Eval corpus (R3, remediation #6)**: fixed briefs in `~/knowledge/domains/<domain>/evals/*.md`
  (27 cases, format in `~/knowledge/domains/EVALS-README.md`) run through the REAL dispatch
  framing (`hermes_dispatch.build_framing`) and scored by the frontier judge against the
  domain RUBRIC — `evals.py` runner (sequential daemon thread, one run at a time), tables
  `eval_runs`/`eval_results` (user-scoped), config fingerprint per run (playbook/rubric/
  style/context/specialist hashes) so score deltas map to config changes. UI: Specialists →
  📏 Evals (domain cards + trends, run history, per-case judge output). The task judge and
  the eval runner share `evals.run_judge_cmd` (settings `judge.cmd` stays the stub hook);
  gate-only hooks `evals.corpus_root`/`evals.stub` default off.

## Agentic OS Capabilities (v1 — added 2026-07-04)

First-class features implementing the agentic-coding harness concepts + competitive
research (amux, arXiv "Code as Agent Harness", SuperAGI, Microsoft Agent Framework).
All map to the 5-layer orchestration stack (Runtime/Isolation/Communication/Coordination/Observability).
**v2 note:** the fake workload behind these mechanics is gone (see Real Dispatch above); the
mechanics themselves (claiming, watchdog, approvals, cost, worktrees, scheduler) stand.

### Coordination layer
- **Atomic task claiming** — `POST /api/tasks/{id}/claim` uses SQLite CAS (UPDATE...WHERE
  status IN ('backlog','todo') + ownership verify). Two agents can never grab the same task;
  second claimer gets 409 with the owner named. Release via `/release`.

### Quality layer (Plan-Execute-Verify)
- **Verify loop** — `POST /api/verify` runs a command, captures exit code + stdout/stderr tail,
  persists to `verify_runs` table. Runtime runs update the task's `verify_status`
  (passing/failing). `GET /api/verify/runs` lists history. This is the OS-level version of the
  static+runtime verify-gate from the coding harness.

### Safety layer
- **Approval gates** — `POST /api/approvals` creates a pending request (agent asking permission
  for sensitive actions: deploy, sudo, destructive ops). `PATCH /api/approvals/{id}` decides.
  Pending count shows as a nav badge. Mirrors SuperAGI's Action Console.

### Resilience layer
- **Self-healing watchdog** — background thread (watchdog.py) every 10s: restarts dead agents
  (PID gone), detects stuck agents (stale heartbeat past watchdog.stale_threshold_s, default 150s) and restarts them, enforces cost caps.
  Configurable via settings table. `GET /api/watchdog/status` for config + recent actions.
  Dead agents are marked 'crashed' (not silently 'idle') so the watchdog heals them. Verified:
  a killed agent is auto-restarted with a new PID in ~3s, same agent ID preserved.

### Isolation layer
- **Git worktree isolation** — `POST /api/agents/{id}/worktree` creates an isolated git worktree
  + branch (session/<short>) so parallel agents never stomp each other's files (the amux pattern).
  worktree.py handles create/has-changes/remove (never force-removes a dirty worktree).

### Memory layer
- **Agent memory** — `memory` table with STM/LTS/experience/longterm scopes.
  `POST/GET/DELETE /api/agents/{id}/memory`. `GET /api/agents/{id}/memory/context` returns a
  condensed context blob (LTS summary + recent experience) — the SuperAGI two-part model.

### Automation layer
- **Cron scheduler** — `scheduled_jobs` table + scheduler.py background thread.
  Minimal cron parser (*, */N, single value, comma lists) across the 5 standard fields.
  `GET/POST/PATCH/DELETE /api/scheduler`. Verified: a */1 job fires within ~70s.

### Cost layer
- **Cost guardrails** — `GET /api/agents/{id}/cost` returns tokens + pct of max_tokens cap +
  projected_usd (configurable via NEXUS_COST_PER_1M_TOKENS). Watchdog force-sets status to
  'cost_capped' when an agent exceeds its max_tokens. Per-agent caps live in the config JSON.

### Communication layer
- **Inter-agent messaging** — `messages` table. `POST /api/agents/{id}/message` sends agent→agent.
  `GET /api/agents/{id}/messages?direction=` lists sent/received. Agents discover peers via the
  agents table (no external service discovery).

### Frontend
- **Agentic view** — new nav item "⚙ Agentic" renders a dashboard of all subsystems: approval
  gates (with Approve/Reject buttons + nav badge), watchdog status + recent actions, verify runs,
  cron scheduler (create/toggle/delete jobs), cost guardrails summary.
- **Enhanced kanban** — task cards now show claimed_by (⚑ owner), verify_status badge, and the
  claim flow is wired through the WS broadcast.
