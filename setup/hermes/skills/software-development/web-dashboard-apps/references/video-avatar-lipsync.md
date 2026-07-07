# Video-Element Avatar with Neural Lip-Sync

The preferred avatar pattern when the avatar should show the user's real face
with neural lip-sync (Wav2Lip). Uses a `<video>` element (MUTED — face only)
plus a separate persistent `<audio>` element (voice), started together when
both are ready. This split is REQUIRED, not optional — see the **Autoplay
Pitfall** below for why a single unmuted video element breaks in real browsers.

Adopted 2026-07-03 in the Nexus JARVIS v2, replacing the Three.js 3D head.
Corrected THREE times as real-browser bugs surfaced:
  - 2026-07-05 (1st): original dual-track design (muted video + separate audio,
    fetched & played independently) caused voice/face desync. "Fixed" by merging
    into one unmuted muxed MP4. This traded desync for a WORSE bug (below).
  - 2026-07-05 (2nd): the single-unmuted-MP4 design passed all headless tests
    but FROZE on follow-up sentences in the real browser — Chrome's autoplay
    policy silently rejected unmuted `video.play()` after the user-gesture
    context expired. The headless tests used `--autoplay-policy=no-user-gesture-required`
    which masked the bug for 3+ iterations. Fixed by going back to separate
    elements but playing them correctly: video MUTED (never blocked), audio via
    a persistent gesture-unlocked element, both started at the same instant.
  - 2026-07-05 (3rd): cache-busting `?v=N` on `app.js` so the browser stops
    serving stale code after edits.

The current correct pattern is documented below. Do NOT regress to the
single-unmuted-MP4 design — it fails in real browsers.

## The Core Rule: MUTED video (face) + separate audio (voice), started together

```
WRONG #1 (desyncs):     /tts  → <audio>.play()        ┐ one starts now
                        /lipsync → <video>.play()     ┘ other starts seconds later
                        (lip-sync render is slow; audio plays immediately → per-sentence drift)

WRONG #2 (freezes):     /talk → single MP4 → <video muted=false>.play()
                        (works on clip 1; clip 2+ silently rejected by autoplay policy → face frozen)

RIGHT (current):        /tts  → <audio> (persistent, gesture-unlocked) ┐ both started at the
                        /talk → <video muted=true> (face only)          ┘ same instant when ready
                        (muted video NEVER blocked; audio unlocked by gesture; no drift)
```

Two independently-timed media streams desync (WRONG #1). But a single unmuted
video gets autoplay-blocked on follow-up clips (WRONG #2). The correct design
splits the concerns: the **video plays MUTED** (muted video autoplay is never
blocked by any browser, on any clip), and the **voice comes from a separate
persistent HTMLAudioElement** that was unlocked by the user's mic-click gesture
and is reused for every clip. Both are fetched in parallel and started at the
same instant when both are ready — so they stay in sync (the lip-sync video is
generated FROM the audio by Wav2Lip, so durations match by construction).

If the lip-sync endpoint is unavailable, the video is simply skipped and audio
plays alone — still no desync (single source), just no face movement.

## HTML Structure

No `<script>` tag for Three.js. No avatar.js file. The video element is created
dynamically in JavaScript inside a circular container:

```html
<!-- index.html: NO three.js CDN, NO avatar.js -->
<script src="/static/app.js"></script>
```

```javascript
// In renderJarvisView() — the container is just an empty div
<div class="avatar-wrap" id="jAvatarWrap"></div>
```

## Video Element Creation

```javascript
function jarvisInitAvatar() {
  const wrap = $('#jAvatarWrap');
  if (!wrap) return;
  wrap.innerHTML = '';
  const video = document.createElement('video');
  video.id = 'jAvatarVideo';
  video.className = 'avatar-video idle';
  video.muted = true;          // muted only in IDLE state (poster image)
  video.loop = true;
  video.playsInline = true;
  video.autoplay = true;
  video.poster = '/static/avatar/reference.jpg';
  video.style.width = '100%';
  video.style.height = '100%';
  video.style.objectFit = 'cover';
  wrap.appendChild(video);
  state.avatarVideo = video;
  setIdleAvatar();
}

function setIdleAvatar() {
  const video = state.avatarVideo;
  if (!video) return;
  video.className = 'avatar-video idle';
  video.loop = true;
  video.removeAttribute('src');
  video.load();
  video.play().catch(() => {});
}
```

## Server: the combined /talk endpoint

The server should expose one endpoint that does TTS synthesis + Wav2Lip render
in a single call and returns the muxed MP4:

```python
@app.post("/api/jarvis/talk")
async def jarvis_talk(body: dict):
    """Combined TTS + lip-sync in one call: text → synced MP4.
    Returns a single MP4 where the audio track (TTS voice) and the video track
    (lip-synced face) are already muxed together by ffmpeg inside Wav2Lip. The
    frontend plays this UNMUTED as the single source of truth — no separate
    audio element, so voice and avatar can never drift apart."""
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "empty text"})
    wav_bytes = await _voice.synthesize(text)      # Piper TTS → WAV
    mp4_bytes = await _lipsync.render_bytes(wav_bytes)  # Wav2Lip → muxed MP4
    return RawResponse(content=mp4_bytes, media_type="video/mp4")
```

Wav2Lip's inference.py already muxes audio into the output (the ffmpeg command
`ffmpeg -y -i audio -i result.avi ... outfile` at the end of inference). Verify
with `ffprobe` — a correct output has two streams: `codec_type=video` AND
`codec_type=audio`. If audio is missing, the mux step in inference.py is broken.

## Client: muted-video + separate-audio playback (the correct pattern)

```javascript
// Per sentence: fetch audio (WAV) and video (lip-sync MP4) IN PARALLEL, then
// start both at the same instant when both are ready. Video is MUTED (autoplay-
// safe on every clip); audio carries the voice (persistent, gesture-unlocked).

async function processTTSQueue() {
  if (state.ttsAnimating) return;
  if (state.ttsQueue.length === 0) {
    setMode('idle');
    setIdleAvatar();   // reset to poster (not frozen last frame)
    maybeAutoListen();
    return;
  }
  state.ttsAnimating = true;
  setMode('talking');

  // Prefetch pipeline: while clip N plays, clip N+1 is already rendering.
  let pending = fetchClip(state.ttsQueue.shift());
  while (pending) {
    const clip = await pending;                              // clip N ready
    let nextPending = null;
    if (state.ttsQueue.length > 0)                           // start clip N+1 NOW
      nextPending = fetchClip(state.ttsQueue.shift());
    if (clip) await playClip(clip);
    pending = nextPending;
  }
  state.ttsAnimating = false;
  setMode('idle');
  setIdleAvatar();
  maybeAutoListen();
}

// Fetch audio + video in parallel. Returns null only if audio fails (video is
// optional — if lipsync is down, clip.videoBlob is null and we play audio-only).
async function fetchClip(text) {
  const audioP = fetch('/api/jarvis/tts', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).then(r => r.ok ? r.blob() : null).catch(() => null);
  const videoP = fetch('/api/jarvis/talk', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).then(r => r.ok ? r.blob() : null).catch(() => null);
  const [audioBlob, videoBlob] = await Promise.all([audioP, videoP]);
  if (!audioBlob) return null;
  return { audioBlob, videoBlob: (videoBlob && videoBlob.size > 1000) ? videoBlob : null };
}

// Play one clip: video muted (face) + audio (voice), started together.
function playClip(clip) {
  return new Promise((resolve) => {
    let resolved = false;
    const audioUrl = URL.createObjectURL(clip.audioBlob);
    const audio = audioEl();                 // persistent element (see below)
    const video = state.avatarVideo;
    let audioReady = false, videoReady = !clip.videoBlob, started = false;

    const cleanup = () => {
      if (resolved) return;
      resolved = true;
      audio.oncanplay = null; audio.onended = null; audio.onerror = null;
      if (video) { video.oncanplay = null; video.onended = null; video.onerror = null; }
      URL.revokeObjectURL(audioUrl);
      if (video && video.currentSrc) URL.revokeObjectURL(video.currentSrc);
      resolve();
    };
    const startIfReady = () => {
      if (started || !audioReady || !videoReady) return;
      started = true;
      if (clip.videoBlob && video) video.play().catch(() => {});   // muted → never blocked
      audio.play().catch(() => cleanup());
    };

    // ── Audio (voice) ──
    audio.oncanplay = () => { audioReady = true; startIfReady(); };
    audio.onended = cleanup;
    audio.onerror = cleanup;
    audio.src = audioUrl;
    audio.load();

    // ── Video (face) — MUTED so autoplay is never blocked ──
    if (clip.videoBlob && video) {
      const videoUrl = URL.createObjectURL(clip.videoBlob);
      video.pause();
      try { video.currentTime = 0; } catch (e) {}
      video.className = 'avatar-video talking';
      video.loop = false;
      video.muted = true;                     // THE KEY: muted = never autoplay-blocked
      video.oncanplay = () => { videoReady = true; startIfReady(); };
      video.onended = cleanup;
      video.onerror = cleanup;
      video.src = videoUrl;
      video.load();
    }
    setTimeout(cleanup, 30000);
  });
}

// Persistent audio element — unlocked ONCE by the user gesture (mic click) and
// reused for every clip so play() is never rejected by the autoplay policy.
function audioEl() {
  if (!state.ttsAudioEl) state.ttsAudioEl = new Audio();
  return state.ttsAudioEl;
}
```

### Why muted video + separate audio (and NOT one unmuted video)

Browsers block **unmuted** `video.play()` / `audio.play()` unless a user gesture
(click, keypress) is active in the call stack. A voice assistant's mic-click
unlocks audio for the FIRST clip. But follow-up clips — started from a
`setTimeout`, a resolved Promise, or a queue loop far from the original click —
are OUTSIDE the gesture context and get silently rejected with
`NotAllowedError`. The symptom: "first sentence works, follow-up sentences the
face doesn't move / the voice cuts out."

**Muted video autoplay is never blocked** — `video.muted = true` makes
`play()` always allowed. So the face (video) plays muted, and the voice comes
from a separate persistent audio element that retains the gesture unlock. Both
start at the same instant (gated by `startIfReady`), so there's no desync.

Do NOT try to simplify this back to a single unmuted video — it will pass
headless tests (which often use `--autoplay-policy=no-user-gesture-required`)
and freeze in the real browser.

## Multi-Sentence Sequencing (prefetch pipeline)

The TTS queue drives sentence-by-sentence playback. Each sentence fetches
audio + video in parallel (~3-6s for the Wav2Lip render). To avoid multi-second
gaps BETWEEN sentences, the `processTTSQueue` function above already uses a
prefetch pipeline: while clip N plays, clip N+1 is already being fetched.
The render time is hidden behind playback.

The FIRST sentence still has a cold-start delay (nothing playing to hide its
render behind). Every subsequent sentence flows with no gap as long as
playback duration ≥ render duration.

**Do NOT try to fix latency by merging streams or reverting to a single
unmuted video** — that reintroduces the autoplay freeze (see Autoplay Pitfall).

## Conversation Mode (Auto-Listen Loop)

A toggle that, when ON, automatically starts mic recording after the avatar
finishes talking:

```javascript
state.conversationMode = false;

// UI (in renderJarvisView, next to mic button)
`<label class="conv-toggle" title="Auto-listen after JARVIS replies">
  <input type="checkbox" id="jConvToggle">
  <span class="conv-slider"></span>
  <span class="conv-label">CONV</span>
</label>`

// Wiring
const convToggle = $('#jConvToggle');
convToggle.addEventListener('change', () => { state.conversationMode = convToggle.checked; });

// Triggered from processTTSQueue when queue empties
function maybeAutoListen() {
  if (state.conversationMode && !state.recording && state.voiceAvailable) {
    startRecording();
  }
}
```

## State-Driven Visual Indicator

```javascript
function setMode(mode) {
  state.mode = mode;
  const video = state.avatarVideo;
  if (video) {
    video.classList.remove('idle', 'listening', 'thinking', 'talking');
    video.classList.add(mode);
  }
}
```

## CSS

```css
.avatar-video {
  width: 100%; height: 100%; object-fit: cover;
  display: block; background: var(--bg-2); border-radius: 50%;
}
.avatar-video.idle { animation: avatarBreathe 4s ease-in-out infinite; }
@keyframes avatarBreathe {
  0%, 100% { transform: scale(1); opacity: 0.97; }
  50% { transform: scale(1.015); opacity: 1; }
}
.avatar-wrap.talking .avatar-video { box-shadow: inset 0 0 20px rgba(94,234,212,.15); }
.avatar-wrap.thinking .avatar-video { box-shadow: inset 0 0 20px rgba(251,191,36,.12); }
.avatar-wrap.listening .avatar-video { box-shadow: inset 0 0 20px rgba(94,234,212,.1); }
.conv-toggle { display: flex; align-items: center; gap: 6px; cursor: pointer;
  font-size: 10px; letter-spacing: 1px; color: var(--text-faint); }
.conv-toggle input { display: none; }
.conv-slider { width: 34px; height: 18px; border-radius: 9px; background: var(--panel-3);
  border: 1px solid var(--border-l); position: relative; transition: background .2s; }
.conv-slider::after { content: ''; position: absolute; top: 1px; left: 1px;
  width: 14px; height: 14px; border-radius: 50%; background: var(--text-dim);
  transition: transform .2s, background .2s; }
.conv-toggle input:checked + .conv-slider { background: rgba(124,92,255,.3); border-color: var(--accent); }
.conv-toggle input:checked + .conv-slider::after { transform: translateX(16px); background: var(--accent); }
```

## Reference Image Constraints (Wav2Lip)

The reference face image (`static/avatar/reference.jpg`) is used in TWO places:
1. Browser poster (the idle face shown in the `<video>` element)
2. Wav2Lip source face (what gets animated when talking)

**Image dimensions are load-bearing for GPU inference.** Wav2Lip's face
detector (S3FD) loads the full frame into GPU memory. The known-good size is
**512x512**. A larger image (e.g. an 882x1444 phone screenshot dropped in raw)
triggers an OOM: `RuntimeError: Image too big to run face detection on GPU`,
which surfaces as a 500 on the `/talk` endpoint — silent from the static gate.

When replacing the reference image, normalize it to 512x512 first:
```python
import cv2
src = cv2.imread('new_face.png')
H, W = src.shape[:2]
scale = 512 / min(W, H)          # downscale shorter side to 512
img = cv2.resize(src, (int(W*scale), int(H*scale)), interpolation=cv2.INTER_AREA)
x = (img.shape[1] - 512)//2; y = (img.shape[0] - 512)//2
crop = img[y:y+512, x:x+512]
cv2.imwrite('static/avatar/reference.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
```
Requirements for the source image: front-facing (head-on), mouth fully visible
(not obscured by hair/beard/hand), neutral expression, even lighting, plain
background. A turned head produces a worse-looking result even if it renders.

## Autoplay Pitfall (do NOT use a single unmuted video — freezes on follow-up)

The 2nd-iteration design "fixed" the desync (below) by merging audio+video into
one muxed MP4 and playing it **unmuted** in a single `<video>` element. This
traded desync for a worse, harder-to-diagnose bug:

```javascript
// DEPRECATED — freezes on follow-up clips in real browsers. Do not use.
function playTalkVideo(mp4Blob) {
  const video = state.avatarVideo;
  video.muted = false;          // <-- unmuted = autoplay-blocked on clip 2+
  video.src = URL.createObjectURL(mp4Blob);
  video.play().catch(() => {}); // silently rejected on follow-up clips
}
```

**Why it fails**: browsers block **unmuted** `play()` unless a user gesture is
active in the call stack. The mic-click unlocks the FIRST clip. But follow-up
clips (started from `setTimeout`, resolved Promises, or a queue loop) are
outside the gesture context → `NotAllowedError` → video freezes on the last
frame while the audio track of the new clip... wait, there IS no separate audio
track being played, so actually nothing plays. The user sees a frozen face and
no voice.

**Why it passed tests for 3+ iterations**: the headless Playwright tests used
`--autoplay-policy=no-user-gesture-required`, which DISABLES the restriction
entirely. The test reproduced a fictional browser, not the real one. See the
runtime-verification skill's `references/browser-media-playback.md` for the
full testing protocol.

**The fix is the current pattern**: muted video (never blocked) + separate
persistent audio (gesture-unlocked). This is NOT the same as the original
dual-track design — both elements start at the same instant (gated by
`startIfReady`), so there is no desync.

## Desync Pitfall (do NOT play audio + video on independent timers)

The 1st-iteration design fetched TTS audio and lip-sync video separately and
played them on independent timers:

```javascript
// DEPRECATED — causes visible voice/face desync. Do not use.
function playTTS(wavBlob) {
  const audio = new Audio(URL.createObjectURL(wavBlob));
  fetchLipsync(wavBlob).then(v => playLipsyncVideo(v, finish)); // parallel
  audio.play();   // <-- starts sound NOW
  // video starts several seconds later when Wav2Lip render + decode finishes
}
```

`audio.play()` fires immediately; the lip-sync video (GPU render + network +
decode) arrives seconds later. Per sentence: voice first, face catch-up second
— the "talk, face moves, talk, face moves" pattern. The comments claiming it
"fixes desync" by stopping audio in the video's finish handler only aligned the
END points, not the START.

**The current pattern avoids this** by fetching both in parallel and gating
`startIfReady` on BOTH being ready — so they start at the same instant. This
is the key difference from the original dual-track design: independent timers
(wrong) vs. a single coordinated start (right).

## Migration Checklist (Three.js → Video Element)

1. **index.html**: Remove the `<script src="three.min.js">` CDN tag and the
   `<script src="/static/avatar.js">` tag.
2. **Delete** `static/avatar.js`.
3. **app.js**: Rewrite `initAvatar()` to create a `<video>` element instead of
   `new JARVISAvatar()`.
4. **app.js**: Replace `avatar.setMode(mode)` / `avatar.setAudioLevel(amp)`
   calls with video element class manipulation.
5. **app.js**: Remove the `createMediaElementSource` / `AnalyserNode` lip-sync
   loop (the server does lip-sync now — no Web Audio analyser needed).
6. **app.js**: Remove FPS counter code referencing `avatar.renderer`.
7. **verify.sh**: Remove the `class JARVISAvatar` check and avatar.js server
   health check. Add checks for `jAvatarVideo`, the `/talk` endpoint usage,
   and `playTalkVideo`.
8. **CSS**: Add `.avatar-video`, `@keyframes avatarBreathe`, state glow classes.

## Pitfalls

- **NEVER play a single unmuted `<video>` for the voice.** Chrome's autoplay
  policy silently rejects unmuted `play()` on follow-up clips (after the
  user-gesture context expires) → face freezes, voice silent. Use MUTED video
  (face) + separate persistent audio (voice). See Autoplay Pitfall above.
  (Hit 2026-07-05 — 3 iterations of headless tests passed because they used
  `--autoplay-policy=no-user-gesture-required`; real browser froze.)
- **CACHE-BUST YOUR STATIC FILES.** `<script src="/static/app.js">` (no query
  string) gets cached by the browser. After you edit app.js, the user's browser
  keeps serving the OLD version — every fix is invisible to them. Always use
  `app.js?v=N` and bump N on each change. Symptom: "I fixed it but it's even
  worse now" — they're running stale code. (Hit 2026-07-05.)
- **NEVER split audio + video onto independent play timers** (original
  dual-track design) — they desync. Use the coordinated-start pattern: fetch
  both in parallel, gate `startIfReady` on BOTH ready, start at the same
  instant. See Desync Pitfall above. (Hit 2026-07-05.)
- **Reference image must be ≤512x512** or Wav2Lip face detection OOMs the GPU
  with "Image too big to run face detection on GPU" → 500 on /talk. Normalize
  the image before dropping it in. (Hit 2026-07-05: a raw 882x1444 screenshot
  broke rendering; static gate stayed green.)
- **VIDEO FREEZES ON THE 2nd+ SENTENCE** has TWO causes — fix BOTH:
  (a) unmuted video (autoplay-blocked on follow-up) → use muted video +
  separate audio (see Autoplay Pitfall); (b) stale element state when swapping
  src → `video.pause()` + `video.currentTime = 0` BEFORE assigning new src,
  clear all handlers in `cleanup()`. The current `playClip` handles both.
  (Hit 2026-07-05.)
- **MULTI-SECOND GAPS BETWEEN SENTENCES** if you fetch sequentially
  (fetch→play→fetch→play). Fix with the prefetch pipeline in
  `processTTSQueue` — kick off clip N+1's fetch BEFORE playing clip N.
  (Reported by user 2026-07-05: "he makes a very long break between sentences.")
- **AVATAR STUCK ON LAST FRAME AFTER SPEAKING (mouth stays open).** Calling
  `setMode('idle')` only swaps CSS classes — it does NOT reset the element.
  You MUST also call `setIdleAvatar()` (removes src, `video.load()`, snaps to
  poster) when the TTS queue empties. (Reported by user 2026-07-05.)
- **VOICE GENDER: verify with autocorrelation pitch tracking, NOT FFT.** A
  naive FFT peak picks formants, not f0, and misreports a male voice (~168 Hz)
  as ~195-208 Hz (looks female). Use an autocorrelation tracker (lag-peak in
  60-300 Hz, frame 2048, hop 1024, silence threshold). Script in
  `scripts/verify_voice_pitch.py`. (Hit 2026-07-05.)
- **Verify the lip-sync MP4 has a video track** — `ffprobe` should show
  `codec_type=video`. (The audio track isn't needed for playback since the
  voice comes from the separate WAV, but Wav2Lip muxes it anyway.)
- **Piper voice is a cached singleton** — after swapping the .onnx model file,
  you MUST restart the server. The model loads lazily and is reused; a hot
  file swap has no effect until the process restarts.
