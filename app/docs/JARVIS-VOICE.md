# JARVIS Voice & Avatar — Implementation Documentation

> **Status:** v2 — particle avatar + WS-streamed TTS. Last verified 2026-07-08.
> Read this before touching any JARVIS code.

---

## 0.-1 STT CONSOLIDATION (2026-07-10) — supersedes every STT detail below

STT no longer runs in-process. The machine's ONE faster-whisper (**large-v3,
int8_float16, ~2GB VRAM**) lives in the killable subprocess `stt_worker.py`;
`voice.py` is its CLIENT (`transcribe()` async for the browser path,
`transcribe_pcm()`/`warm_stt()` sync for dictation + meetings — every caller
serializes on the worker pipe). GPU discipline: loads wait ≤45s on the
cross-process gpu_lock, evict idle :11434 ollama models when VRAM is short,
CPU only on a real CUDA failure (worker-lifetime flip + 600s parent cooldown).
Idle: the worker is **killed** after `voice.stt_idle_timeout` (300s) — full
VRAM reclaim incl. the CUDA context; TTS has its own separate 300s timer.
`POST /api/jarvis/stt/warm` (fired on mic-press) hides the ~4-8s cold load.
System-wide dictation + MeetingMode were absorbed from WisprFlow into
`dictation*.py` (see app/CLAUDE.md + the Meetings tab). STT references below
(medium.en, shared idle timer, "60s"/"300s" unload numbers) are historical.

## 0.0 v2.1 CAPABILITY + ROBUSTNESS PASS (2026-07-08)

Additive; the pipeline below is unchanged. New:

- **STT self-heals** (voice.py): a CUDA failure under VRAM contention used to be a silent 500.
  Now it logs a traceback → reloads → retries once → CPU int8 fallback + a 600s GPU cooldown.
  Model/device/language are settings (`voice.stt_model` [medium.en; try large-v3-turbo],
  `voice.stt_device` auto|cuda|cpu, `voice.stt_language`).
- **Graceful shutdown bounded** (server.py + watchdog.py + the unit): `timeout_graceful_shutdown=8`
  + a `handle_exit` that trips `watchdog.SHUTTING_DOWN` before shutting down (no worker respawn
  mid-stop) + `TimeoutStopSec=25`. Ends the 90s-SIGKILL-on-every-restart problem (was ~1s now).
- **Business Brain** (jarvis_brain.py): per-turn domain detection (9 domains) folds ~/knowledge
  (BUSINESS-CONTEXT facts + STYLE-VOICE kill-list always; the matched domain's RUBRIC gates +
  PLAYBOOK menu + paths on deliverable turns) into the framing. `_jarvis_framing` returns
  (framing, domain); the stream emits an SSE `domain` event → topbar 📚 chip.
- **Fuller control surface**: the framing now documents the whole OS API (wizard, projects,
  deliverables, ▶ Test-app, judge/verify/review, approvals/scheduler/quota), told to plan-then-build
  or hand work to the fleet.
- **Command deck** (app.js): topbar ⚡ Deck → right rail with board glance, deliverables (each
  with ▶ Test app), pending approvals, and "Hand a task to the fleet". `jarvisLoadDeck`.
- Gates: `verify.sh` (static) + `verify_jarvis_e2e.py` (page_errors:[] with the new topbar) both
  green; deck+domain-chip proven live via Playwright.

---

## 0. ARCHITECTURE v2 (2026-07-08) — READ THIS FIRST

The Wav2Lip talking-head is **RETIRED from the pipeline** (endpoints `/talk`
and `/lipsync` return **410 Gone** since 2026-07-09 — they were still live and
loaded Wav2Lip onto the shared 12 GB GPU when hit; lipsync.py stays on disk
but nothing reaches it). The v2 stack:

- **Avatar (v7 HOLOGRAM, 2026-07-10 — HOLOGRAM-AVATAR-PLAN-2026-07-09.md)**
  = cyan point-lattice hologram head: the three.js "facecap" model with
  ALL 52 ARKit blendshapes (model by Face Cap — bannaflak.com/face-cap, no
  explicit upstream model license; credit kept in jarvis3d.js + the build
  script; clean-license drop-in = a Ready Player Me GLB). The upstream GLB
  requires a KTX2 texture loader at parse time — `scripts/
  build_facecap_hologram.py` strips images/textures/animations offline →
  `static/avatar/facecap_hologram.glb` (meshopt stays; decoded at runtime).
  **Rendering** — ONE shared baked-Float32 geometry, three renderables:
  near-black occluder Mesh (+teeth — hides the far side, reads solid),
  faint additive wireframe lattice, and morph-aware ShaderMaterial Points
  (fresnel rim, per-dot twinkle via aSeed, scanline shimmer, rare glitch
  flicker, density-compensated brightness aB — dense lip/eye loops would
  blow out white otherwise, neck fade via uFade, manual size attenuation
  uScale). Points layer is midpoint-subdivided (2.7k → ~10.4k dots,
  POINT_SUBDIV). All three renderables share ONE morphTargetInfluences
  array (r160 texture-based morphs bind per object automatically — works
  for Points + ShaderMaterial via the morphtarget_* shader chunks). Post:
  EffectComposer (MSAA HalfFloat RT) → UnrealBloomPass half-res, strength
  .45/radius .30/threshold .85 (HIGH on purpose: additive dots sum past
  1.0 — a low threshold blooms the head to a white ball) → OutputPass.
  Fit anchors on the EYE PIVOTS (grp_eyeLeft/Right), NOT the bbox — the
  cranium is deep/tall and bbox-anchoring drops the face out of frame
  (HEAD_H 53, eye mid → (0, −2, +3), face +z, auto-flip if authored -z).
  The head sits ON the Lee Perry-Smith SCAN BUST torso (the pre-v7
  anatomy, CC-BY 3.0): scripts/build_torso_from_scan.py slices the scan
  below mid-neck, normalized to head-width units → torso_scan.glb; runtime
  scales it 0.75× the head half-width, anchors it at the neck-stub ring and
  fades the head’s stub out under the chin (per-material uFade) while the
  torso fades at the frame bottom — the seam-hiding overlap. Eyes are separate meshes under rotatable pivot Groups; glints ride the pivots.
  Avatar→memory links: 3-strand beams, BOTH ends tinted per memory node
  hue, ×1.5 spread. Fallback = procedural ellipsoid lattice, head-only
  (no morphs) + console.warn if a GLB fails.
  **Lip sync = TEXT-ALIGNED VISEMES (no backend change):** app.js keeps a
  LIVE per-sentence utterance record {text,start,end,done} on the
  AudioContext clock (first PCM chunk fixes start, every chunk extends
  end, WS {done}/{error} closes FIFO) and registers it via
  `Jarvis3D.speak(rec, ctx)`; barge-in/stop/reset clear via
  `stopSpeech()`. jarvis3d stretches the Oculus-viseme timeline
  (vendored MIT `static/vendor/lipsync/lipsync-en.mjs`,
  wordsToVisemes → relative times/durations) over the REAL audio window —
  self-corrects as chunks land — evaluates 50ms-attack/120ms-release
  envelopes, maps visemes → ARKit weights (VISEME_ARKIT table), gates by
  the live RMS envelope (real pauses close the mouth) and keeps the
  sibilance narrowing (Jarvis3D.setLevel(v, hf) unchanged). No timed
  utterance (mic mouthing) → amplitude fallback on jawOpen. The
  analyser-less HTTP WAV fallback passes a fixed-window record on the
  performance clock (gate = 1).
  **Eyes/idle are research-grounded:** blink keeps the measured human
  dynamics (Trutoiu et al., ACM TAP 2011 — ~80ms accelerating close,
  brief closure, ~220ms asymptotic reopen, 2–6s randomized, 12% doubles)
  on eyeBlink_L/R; gaze = saccade/fixation state machine (75%
  camera-locked fixations that TRACK the pointer-driven camera with
  head-sway compensation, 60–90ms saccades + overshoot, microsaccades,
  blink coupling at saccade onset), driving the eye pivots + eyeLook*
  morphs as lid follow; thinking = up-aside gaze + browInnerUp,
  listening = locked-on + eyeWide + roll tilt, talking = env-correlated
  micro-nods + brow pulses. Idle = breathing + subtle sway, ALWAYS faces
  the user (no turntable — operator decision 2026-07-09). MODE_TINT are
  multipliers on the cyan base uBase (0.30, 0.85, 1.0) (>1 amplifies into bloom).
  **Vendored runtime deps (no build step):** `static/vendor/threejsm/`
  (13 r160 jsm addons, bare 'three' rewritten to the exact core CDN URL —
  ONE shared THREE instance; never /+esm) + `static/vendor/lipsync/` —
  see `static/vendor/_VENDORING.md`. Old head_points.json/male_head.glb/
  2D-frame assets + their build scripts are DELETED (git history has them).
- **Memory galaxy in the JARVIS scene (v10, 2026-07-08)** — the old node
  streams/pulse sprites are GONE. jarvis3d.js now embeds the Memory tab's
  real 3D map (`/api/memory3d`: PCA positions, similarity links, identity
  hues, region callouts, ambient electric pulses) at **50× node spacing**
  (v12: 5× the previous 10×; the ±6000 cloud fills the sky) in a slowly
  spinning group (the tab's auto-orbit rate) at z≈-7800, y≈1540 — between
  the bust and the static memory-matrix backdrop (the same scatter, pushed
  to z≈-16500). **100 links** run from the back of the skull to the 100
  most-linked ("most used") nodes, endpoint-tracked every frame; each link
  is a 3-STRAND converging beam (WebGL caps lines at 1px, so 3× thickness
  = center strand + two dimmer satellites).
  Signals: idle = a thin inbound trickle; **thinking** = rapid amber pulses
  between the avatar-connected nodes; **leaving thinking** (the answer is
  forming) = a 2.4s flood of signals from the galaxy into the head
  (`setMode` triggers it). The topbar **🧠 Memory** button calls
  `Jarvis3D.toggleGalaxy()`: the camera flies THROUGH the bust into the
  galaxy (chat overlay fades via `.jv2-stage.galaxy-on`), then drag-orbit /
  scroll-zoom / hover panel / click-to-edit (`onMemorySelect` →
  `openMemoryNodeModal`, the same editor as the Memory tab). Only events
  targeting the canvas navigate — toolbar clicks never open stars.
  Historical (superseded) approach below:
- ~~Avatar~~ = `static/jarvis3d.js`: a Three.js POINT-CLOUD HEAD sampled from
  `static/avatar/reference.jpg` (contrast-stretched luminance + edge boost →
  particle density/brightness; ellipsoid relief), with node streams flowing
  from the back of the skull into the user's REAL memory galaxy
  (`/api/memory3d` data, memory3d.js palette). The avatar renders BEHIND the
  chat (`.jarvis3d-canvas` z-0). States idle/listening/thinking/talking =
  tint + motion. `window.Jarvis3D = {mount, dispose, setMode, setLevel,
  setAnimations}` — setAnimations(false) is the FX on/off button (freezes RAF).
- **Voice out** = `/ws/jarvis/tts` WebSocket: client sends `{"text": sentence}`,
  server streams raw PCM chunks (16-bit mono 22050) from `voice.synthesize_stream`
  (Piper incremental) + `{"done":true}`; `{"stop":true}` aborts (barge-in).
  Browser schedules chunks gaplessly on an AudioContext; an AnalyserNode on the
  SAME graph feeds `Jarvis3D.setLevel()` → **native-timing lip-sync** (the mouth
  region of the point cloud opens with real amplitude — nothing to align).
  First audio ≈100-300ms warm. Sentences are spoken PROGRESSIVELY while the
  LLM reply is still streaming (`jarvisSpeakProgress`). HTTP `/api/jarvis/tts`
  WAV remains as fallback (`jarvisFetchClip`).
- **Voice in** = adaptive VAD in `jarvisMicLevelLoop`: time-domain RMS with a
  self-calibrating noise floor (floor EMA while no speech), speech threshold
  `max(0.028, floor*3)`, end-of-speech hangover 1.15s (conversation mode) /
  2.1s (manual) → auto-transcribe+send. Conversation mode also runs a
  **barge-in monitor** during TTS (echoCancellation'd mic, ~450ms sustained
  voice → stop TTS + listen). getUserMedia uses echoCancellation +
  noiseSuppression + autoGainControl.
- **Eyes** = webcam (`getUserMedia`) / screen (`getDisplayMedia`) share
  buttons. **Black-frame rescue (2026-07-08):** every grab measures mean
  luminance; near-black frames (<8/255) are never indexed or sent. On
  webcam start `jarvisCamAutoFix` probes after ~1.4s — if black (IR/depth
  sensors enumerate next to the real webcam on face-unlock laptops, and
  THIS machine has one at /dev/video2), it walks the other cameras and
  keeps the first that shows light (choice persisted in localStorage
  `jvCamId`, used as `deviceId: {ideal}` next time). Frames every 4-5s →
  `POST /api/jarvis/vision/frame` → vision.py:
  SigLIP so400m embeddings + RapidOCR in a persistent ml-env worker
  (`vision_worker.py`, killed after 10min idle), stored in qdrant
  `jarvis_vision` (per-user, deduped, capped 4000). Search =
  `POST /api/jarvis/vision/search` (SigLIP text→image + OCR keyword boost),
  surfaced in a scroll/select/copy popup (`jarvisVisionSearchModal`). Chat
  turns mentioning look/see/screen ride the current frame along
  (`frame_b64`) → described locally by ollama `qwen3-vl:8b` → injected as
  `[JARVIS EYES …]` context AND indexed with the user's words as note.
  **Image-FILE analysis (2026-07-08):** GLM chat models have no vision, so
  the chat endpoint auto-describes exchange images with the same local VLM:
  naming an image file in the message analyzes it (up to 2); an unnamed
  "analyze the image/screenshot/photo…" takes the newest exchange image
  (only when no live frame rides along). Injected as
  `[JARVIS EYES — image file '<name>' …]`; the framing tells him he CAN
  see images and must never claim otherwise.
- **Image generation** = `POST /api/jarvis/imagine` → SDXL-Turbo in the same
  worker (sequential CPU offload — 12GB card; ollama VLM is evicted first)
  → PNG into the file exchange. Z.AI vision/CogView are NOT available on the
  coding-plan key (error 1113, verified) — vision is fully local.
- **File exchange** = `workspaces/jarvis/<uid>/files/`, drag&drop in the
  sidebar; the per-turn `system_message` framing tells Hermes to read/write
  THERE; after each turn the server diffs the folder and emits an SSE
  `files` event → chips in the chat.
- **System control** = the framing gives Hermes curl access to the Nexus API
  via the per-boot `auth.INTERNAL_TOKEN` + `x-nexus-user` (scoped to the
  chatting user; restart invalidates). Readback-confirmation rule is in the
  prompt. Board snapshot rides in each turn.
- **Sessions** = per-user MULTIPLE conversations (`jarvis_session.json`
  history), sidebar with switch/forget/title; messages endpoint allows any
  session in the caller's own history.
- **Extras**: daily spoken briefing (`/api/jarvis/briefing`, deterministic),
  task completion/failure callbacks spoken while the tab is open
  (`/api/jarvis/events` polling), voice/text intents for `/find` (vision
  search) and `/imagine`, per-message copy buttons.
- **Gates**: `scripts/verify_jarvis_e2e.py` (live turn incl. WS TTS),
  `scripts/verify_jarvis_v2_backend.py` (23 checks: vision memory, VLM,
  imagine, files, sessions, briefing, WS TTS).

Sections below describe the v1 Wav2Lip pipeline for historical context —
its lessons (cache-busting, autoplay policy, persistent audio element,
GPU discipline) still apply.

---

## 1. Architecture Overview

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│  BROWSER    │     │  NEXUS SERVER (FastAPI, port 8777)        │
│             │     │                                          │
│  Mic click  │────▶│  /stt   → faster-whisper (GPU)           │
│  (face btn) │     │           → transcribed text             │
│             │     │                │                         │
│  Recording  │     │                ▼                         │
│  (webm/opus)│     │  /chat/stream → Hermes Agent API         │
│             │     │  (SSE proxy to localhost:8642)           │
│             │     │           → streamed reply text          │
│             │     │                │                         │
│             │     │                ▼                         │
│  ┌───────┐  │     │  /talk   → Piper TTS  (CPU, ~100ms)      │
│  │ video │◄─┼─────│           → Wav2Lip   (GPU, ~4s)         │
│  │(muted)│  │     │           → ffmpeg mux audio+video       │
│  └───────┘  │     │           → single muxed MP4 returned    │
│  ┌───────┐  │     │                                          │
│  │ audio │◄─┼─────│  (same MP4 blob plays in BOTH elements)  │
│  │(voice)│  │     │                                          │
│  └───────┘  │     │  Idle unloader: after 60s no voice use,  │
│             │     │  unloads TTS+STT from memory              │
└─────────────┘     └──────────────────────────────────────────┘
```

**Key design principle:** The browser fetches `/talk` ONCE per sentence, receiving
a single muxed MP4 that contains both the audio track (TTS voice) and the video
track (lip-synced face). The same blob is played in two elements — a muted
`<video>` for the face and an `<audio>` element for the voice. Since both
elements read the same blob, they are synced by construction and cannot drift.

---

## 2. File Map

| File | Role |
|------|------|
| `static/app.js` | Frontend: view rendering, mic recording, SSE streaming, TTS queue, playback |
| `static/index.html` | Page shell; loads app.js + style.css with `?v=N` cache-busting |
| `static/style.css` | Avatar-as-button layout, reactor ring, state animations |
| `static/avatar/reference.jpg` | The face image (512×512 JPEG). Used for BOTH idle display AND Wav2Lip source |
| `server.py` | FastAPI server; endpoints `/stt`, `/tts`, `/talk`, `/chat/stream`, idle unloader thread |
| `voice.py` | Piper TTS (male voice) + faster-whisper STT. Lazy singletons, idle unload |
| `lipsync.py` | Wav2Lip subprocess wrapper. Serializes GPU inference via asyncio.Lock |
| `models/piper_voice.onnx` | Piper TTS model (male "ryan" voice) |
| `models/piper_voice.onnx.json` | Piper config (sample_rate, dataset, etc.) |

---

## 3. The Voice Turn (end-to-end flow)

### Step 1: User clicks the face (mic toggle)
- The avatar IS the button. The `<div id="jReactorWrap">` contains both the
  canvas animation ring AND the `<div id="jAvatarWrap">` (the face).
- Click handler in `jarvisBindControls()` (~line 1993):
  ```js
  $('#jReactorWrap').addEventListener('click', () => {
    if (jarvisState.recording) jarvisStopRecording();
    else jarvisStartRecording();
  });
  ```
- This click is the **user gesture** that unlocks audio autoplay for the
  session. The persistent `<audio>` element (created lazily in `jarvisAudioEl()`)
  is unlocked here and reused for every clip.

### Step 2: Recording (`jarvisStartRecording`, ~line 2457)
- Uses `navigator.mediaDevices.getUserMedia()` → requires HTTPS or localhost.
- `MediaRecorder` captures audio as `audio/webm; codecs=opus`.
- `ondataavailable` pushes chunks to `jarvisState.audioChunks`.
- `onstop` calls `jarvisHandleRecording()`.
- Mic level visualized via WebAudio `AnalyserNode` → `jarvisMicLevelLoop()`.

### Step 3: Transcription (`jarvisHandleRecording`, ~line 2498)
- Builds a `Blob` from chunks, POSTs to `/api/jarvis/stt` as multipart form.
- Server: `voice.transcribe()` → faster-whisper medium.en (CUDA float16).
- Returns `{ "text": "..." }`.

### Step 4: LLM reply (`jarvisStreamChat`, ~line 2100)
- POSTs `{ "input": text }` to `/api/jarvis/chat/stream` (SSE).
- Server proxies to Hermes Agent API at `localhost:8642`.
- Browser reads the SSE stream, accumulates `fullText`.
- On stream end, calls `jarvisSpeak(fullText)`.

### Step 5: Speak (`jarvisSpeak` → `jarvisProcessTTSQueue`, ~line 2297)
- Splits the reply into sentences: `text.match(/[^.!?]+[.!?]*/g)`.
- Pushes each sentence to `jarvisState.ttsQueue`.
- Calls `jarvisProcessTTSQueue()` which runs the **prefetch pipeline**.

---

## 4. The Playback Pipeline (CRITICAL — read before editing)

### 4a. Prefetch pipeline (`jarvisProcessTTSQueue`, line 2297)

```js
// Render sentence N+1 WHILE sentence N plays.
// This hides the ~4s Wav2Lip render behind playback.
let pending = jarvisFetchClip(firstText);
while (pending) {
    const clip = await pending;
    let nextPending = null;
    if (queue.length > 0) nextPending = jarvisFetchClip(queue.shift());
    if (clip) await jarvisPlayClip(clip);   // plays while next renders
    pending = nextPending;
}
```

- At most **2 concurrent `/talk` calls** (current + next). This is intentional
  — more would overwhelm the GPU lock and cause 500s (see §7, lesson learned).

### 4b. Fetch (`jarvisFetchClip`, line 2338)

- Calls `/api/jarvis/talk` ONCE. Returns a single muxed MP4 blob.
- The MP4 contains both tracks: h264 video (the face) + aac audio (the voice).
- **Fallback:** if `/talk` fails, calls `/api/jarvis/tts` (audio-only WAV).

**Why single-call, not parallel /tts + /talk:**
The old code fetched `/tts` AND `/talk` in parallel for each sentence. But
`/talk` internally synthesizes TTS again, so every sentence triggered double
TTS plus a Wav2Lip subprocess — all competing for the same GPU lock. Under
concurrent pressure, `/talk` intermittently returned 500, the frontend fell
back to audio-only, and the face didn't move until a later `/talk` succeeded.
This caused the "face delayed 2-3 sentences" bug. Single-call eliminates it.

### 4c. Play (`jarvisPlayClip`, line 2363)

```js
function jarvisPlayClip(blob) {
  const isVideo = blob.type === 'video/mp4' || blob.size > 20000;
  // ...
  const url = URL.createObjectURL(blob);
  const audio = jarvisAudioEl();   // persistent, gesture-unlocked
  const video = jarvisState.avatarVideo;

  // Wait until BOTH are ready, then start simultaneously
  const startIfReady = () => {
    if (started || !audioReady || !videoReady) return;
    started = true;
    if (isVideo && video) video.play().catch(() => {});
    audio.play().catch(() => cleanup());
  };

  audio.oncanplay = () => { audioReady = true; startIfReady(); };
  audio.src = url;    // SAME blob
  audio.load();

  if (isVideo && video) {
    video.muted = true;   // ← MUTED: autoplay never blocked by Chrome
    video.oncanplay = () => { videoReady = true; startIfReady(); };
    video.src = url;      // SAME blob as audio
    video.load();
  }
}
```

**Why muted video + separate audio:**
Chrome's autoplay policy blocks unmuted `video.play()` outside a user-gesture
context. The first clip plays (mic click = gesture), but follow-up clips were
silently rejected → video froze, audio kept going. Muted video autoplay is
NEVER blocked. The voice comes from the separate `<audio>` element, which was
unlocked by the user gesture and persists across clips.

### 4d. Idle reset (`jarvisSetIdleAvatar`, line 1879)

- Called when the queue finishes (line 2329).
- Removes the video `src`, calls `video.load()` → snaps back to the poster
  image (`reference.jpg`), so the face doesn't freeze on the last frame.

### 4e. Audio element (`jarvisAudioEl`, line 2415)

- Lazily creates ONE `Audio()` element, stored in `jarvisState.ttsAudioEl`.
- Reused for every clip. This persistence is what keeps `play()` from being
  rejected by autoplay policy on follow-up clips.

---

## 5. Server Endpoints (server.py)

### `/api/jarvis/stt` (POST, multipart)
- Receives webm/wav/mp3 audio bytes.
- Calls `voice.transcribe()` → faster-whisper.
- Returns `{ "text": "..." }`.

### `/api/jarvis/tts` (POST, JSON `{text}`)
- Calls `voice.synthesize(text)` → Piper TTS.
- Returns WAV bytes (22.05kHz mono 16-bit).

### `/api/jarvis/talk` (POST, JSON `{text}`) ← THE PRIMARY ENDPOINT
- Calls `voice.synthesize(text)` → WAV bytes.
- Calls `lipsync.render_bytes(wav_bytes)` → Wav2Lip renders MP4.
- Returns a single muxed MP4 (video/mp4) with BOTH h264 video + aac audio.
- This is what the frontend calls for playback.

### `/api/jarvis/chat/stream` (POST, JSON `{input}`)
- SSE proxy to Hermes Agent API (`localhost:8642`).
- Streams `event: token` / `event: done` SSE events.
- **Overload fallback (2026-07-08):** if the turn dies with a Z.AI 429
  load-shed signature before any content streamed, the server emits
  `event: fallback` `{from, to}` and retries the turn ONCE in the SAME
  session with a per-turn model override (settings
  `dispatch.fallback_enabled` / `dispatch.fallback_model`, default
  glm-5-turbo; needs the `session-model-api-server` guardian core-mod).
  The frontend renders the fallback event as a tool-style note. Test knob:
  setting `jarvis.force_429=1` sheds the primary pass without sending it.

### `/api/jarvis/voice/status` (GET)
- Returns model load state, engine names, `last_voice_use`, `idle_timeout`.

### `/api/jarvis/lipsync/status` (GET)
- Returns Wav2Lip readiness (checkpoint, reference face, ml_env paths).

---

## 6. Voice & Lipsync Modules

### voice.py — Piper TTS + faster-whisper STT

- **TTS:** Piper ONNX model at `models/piper_voice.onnx`. Current voice is
  "ryan" (male, pitch ~163Hz). Runs on CPU (ONNX CPUExecutionProvider).
  Config at `models/piper_voice.onnx.json` (sample_rate 22050).
- **STT:** faster-whisper "medium.en" on CUDA float16. Uses CUDA libs from
  `/usr/local/lib/ollama/cuda_v12/` (preloaded via ctypes).
- **Locks:** `_stt_lock` and `_tts_lock` (asyncio.Lock) serialize each model.
- **Idle unloading:** `_last_voice_use` timestamp updated on every use.
  `check_and_unload_idle()` unloads both models after `IDLE_TIMEOUT` (60s)
  of inactivity. Called by the server's background thread every 15s.
- **Lazy loading:** models load on first use (`_get_stt()` / `_get_tts()`),
  unload after idle, reload on next use.

### lipsync.py — Wav2Lip neural lip-sync

- Runs Wav2Lip as a **subprocess** (not in-process). Each `/talk` call:
  1. Writes WAV to a temp file.
  2. Spawns `/home/sinep/ml-env/bin/python /home/sinep/Wav2Lip/inference.py`
     with `--face static/avatar/reference.jpg --audio <wav> --outfile <mp4>`.
  3. The subprocess loads the Wav2Lip model, renders, muxes audio via ffmpeg,
     writes the MP4, and exits.
- Because it's a subprocess, GPU memory is freed after each render — no idle
  unloading needed for Wav2Lip (unlike the persistent Piper/Whisper models).
- `_lock` (asyncio.Lock) serializes GPU inference — one render at a time.
- **Reference face MUST be 512×512** (or smaller). Larger images cause the
  S3FD face detector to OOM: "Image too big to run face detection on GPU."
- Reference face: `static/avatar/reference.jpg`.

---

## 7. Avatar-as-Button UI

### HTML structure (in `renderJarvisView()`, app.js ~line 1778)
```html
<div class="avatar-reactor-row">
  <div class="reactor-wrap" id="jReactorWrap" title="Click to talk">
    <canvas id="jReactor"></canvas>
    <div class="avatar-wrap" id="jAvatarWrap"></div>   <!-- face, centered -->
    <div class="reactor-state">
      <div class="st" id="jState">IDLE</div>
      <div class="hint" id="jHint">CLICK TO TALK</div>
    </div>
  </div>
</div>
```

- The face (`#jAvatarWrap`) is positioned at 68% size, centered inside the
  reactor ring (`#jReactorWrap`). The canvas (arc reactor animation) is the
  ring behind the face.
- Clicking anywhere on `#jReactorWrap` toggles recording.
- The separate mic button was REMOVED — the face IS the button now.

### CSS (style.css ~line 466)
- `.reactor-wrap`: `cursor:pointer`, `:active { transform:scale(.97) }`.
- `.reactor-wrap .avatar-wrap`: `position:absolute; width:68%; height:68%`.
- `.reactor-wrap.recording .avatar-wrap`: red pulse animation (`facePulse`).
- Recording state toggled in `jarvisStartRecording`/`jarvisStopRecording`
  via `$('#jReactorWrap').classList.add/remove('recording')`.
- Hint text: `#jHint` changes "CLICK TO TALK" ↔ "CLICK TO STOP".

### States (`jarvisSetMode`, line ~2085)
- `idle` (accent purple), `listening` (teal), `thinking` (yellow), `talking` (teal).
- Updates: `#jState` label, `#jVoiceLabel`, `#jStateKv`, video class,
  `#jAvatarWrap` glow class, `#jBar` width.

---

## 8. Cache-Busting (CRITICAL)

`index.html` loads scripts with version query strings:
```html
<link rel="stylesheet" href="/static/style.css?v=3">
<script src="/static/app.js?v=5"></script>
```

**When you edit app.js or style.css, you MUST bump the `?v=N` number.**
Otherwise the browser serves a stale cached copy and your changes are invisible.
This was the root cause of a major debugging fiasco — "fixes" appeared to not
work because the browser was running old cached code.

---

## 9. GPU Memory Management

- **Baseline VRAM usage:** ~3.3GB (owned by other processes, not Nexus).
- **Piper TTS:** runs on CPU, does NOT consume GPU VRAM.
- **faster-whisper STT:** loads to GPU on first use (~1-2GB).
- **Wav2Lip subprocess:** spikes GPU ~2GB during render, freed after exit.
- **Idle unloading:** after 60s with no voice activity, Piper + Whisper are
  unloaded from memory. They reload lazily on next use.

---

## 10. Testing & Verification

There is no canonical test suite for the JARVIS voice flow. Verification is
done via ad-hoc Playwright scripts under `/tmp/hermes-verify-*.py`. Key tests:

1. **/talk reliability:** 5 concurrent calls → 0 failures (500s eliminated).
2. **Face movement:** video element fires `playing` event during SPEAKING.
3. **Voice-to-face sync:** gap ≈ 0s (both from same blob).
4. **Idle unload:** model unloads after 60s, reloads on next use.
5. **Autoplay-safe:** works WITHOUT `--autoplay-policy` flag (real browser).

**Testing pitfall (saved to memory):** Playwright's `--autoplay-policy=no-user-gesture-required`
DISABLES Chrome's real autoplay restrictions. Tests using it will pass while
the real browser silently rejects unmuted video.play(). Always test WITHOUT
that flag to reproduce real browser behavior.

---

## 11. Lessons Learned (do not repeat these mistakes)

1. **Never fetch /tts and /talk in parallel.** It doubles GPU load and causes
   /talk to 500 under pressure. Use single /talk call.

2. **Always cache-bust when editing static files.** Bump `?v=N` in index.html.

3. **Never test video autoplay with --autoplay-policy flag.** It masks the real
   browser behavior. Test without it.

4. **Reference face must be ≤512×512.** Larger images crash Wav2Lip's face
   detector with GPU OOM.

5. **Video must be MUTED for follow-up clips.** Chrome blocks unmuted
   video.play() after the user-gesture context expires.

6. **Reset the avatar after speaking.** Call `jarvisSetIdleAvatar()` when the
   queue finishes, or the face freezes on the last frame.

7. **Use a persistent audio element.** Creating a new `Audio()` per clip causes
   autoplay rejections. Reuse one unlocked by the user gesture.
