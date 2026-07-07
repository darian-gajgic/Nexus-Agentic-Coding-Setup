# JARVIS Voice & Avatar — Implementation Documentation

> **Status:** Working. Last verified 2026-07-05.
> This document describes the complete wiring of the JARVIS talking-head avatar:
> voice input (STT), LLM reply, voice output (TTS), neural lip-sync (Wav2Lip),
> and the avatar-as-button UI. Read this before touching any JARVIS code.

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
