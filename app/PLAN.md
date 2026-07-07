# PLAN — JARVIS Neural Talking-Head Avatar (v2)

> Implements SPEC.md. Bite-sized tasks, TDD-ordered where possible, exact paths.
> For Hermes: use subagent-driven-development / delegate_task per task. Primary model: GLM-5.2.

## Phase 0 — Environment & Reference Image (foundation)

### Task 0.1: Verify Wav2Lip runs in ml-env on this GPU
- Check Wav2Lip install in /home/sinep/ml-env (or clone fresh). Download checkpoint (~500MB).
- Smoke test: run inference on a 1s silent audio + the extracted face → produces a video.
- Verify sm_120 (Blackwell) compatibility. If kernel fails, patch/rebuild.
- Exit criteria: `python inference.py --checkpoint_path ... --face <ref> --audio <1s wav>`
  produces an mp4 with a moving mouth.

### Task 0.2: Auto-extract best reference face frame
- Script: `scripts/extract-face.py` (runs in ml-env).
- Sample face.mp4 at 1fps, detect faces (OpenCV/dlib already installed), score each candidate
  on: frontal (low yaw), sharpness (variance of Laplacian), brightness, mouth-closed symmetry.
- Output: `static/avatar/reference.jpg` (512x512 or 96x96 per Wav2Lip requirement).
- Exit criteria: reference.jpg is a clear front-facing face, visually confirmed.

## Phase 1 — Backend: Lip-Sync Endpoint

### Task 1.1: Wav2Lip inference wrapper module
- File: `lipsync.py` — loads Wav2Lip model lazily (singleton), runs inference via subprocess
  into ml-env OR imports directly if importable.
- Function: `async def render_lipsync(audio_path) -> Path` — returns path to output mp4.
- Exit criteria: unit test — given a 1s wav, returns a valid mp4 path that exists.

### Task 1.2: FastAPI endpoint POST /api/jarvis/lipsync
- In server.py: accepts multipart audio file, writes temp wav, calls lipsync.render_lipsync,
  returns video file StreamingResponse. Lazy-loads model on first call.
- Exit criteria: `curl -F file=@speech.wav localhost:8777/api/jarvis/lipsync` returns an mp4.

### Task 1.3: Sentence splitting + per-sentence TTS→lipsync pipeline
- Modify voice.py / server.py: split streamed reply into sentences, for each: TTS → wav →
  lipsync → mp4. Return a sequence of clips.
- Exit criteria: a full reply produces N mp4 clips, one per sentence.

## Phase 2 — Frontend: Neural Avatar + Live Conversation

### Task 2.1: Rewrite avatar.js as a video-element avatar
- Replace procedural Three.js head with a <video> element that plays lip-sync clips.
- States: idle (fallback breathing animation on last frame), listening, thinking, talking.
- Exit criteria: avatar shows the face video, plays clips, switches states.

### Task 2.2: Wire talking state to play lip-sync clips
- When TTS plays for a sentence, fetch /api/jarvis/lipsync, play the returned video in sync.
- Chain clips for multi-sentence replies.
- Exit criteria: typing a message → reply shows with mouth moving on the face video.

### Task 2.3: Fix mic recording + conversation loop
- Ensure getUserMedia works (add HTTPS note/self-signed option for LAN).
- After talking ends, if conversation-mode toggle is ON, auto-jarvisStartRecording().
- Exit criteria: mic records → STT → reply → auto-listen loop works hands-free.

## Phase 3 — Verify & Polish

### Task 3.1: Full end-to-end verification
- Run all 7 SPEC verification steps manually. Capture evidence.
- Run `bash scripts/verify.sh` — must pass.

### Task 3.2: Update verify.sh for new functions
- Add checks: JARVISAvatar video-based, lipsync endpoint 200, conversation toggle exists.
- Exit criteria: verify.sh green including new checks.

## Notes
- All AI models free/local. Primary coding via GLM-5.2 (per user: Claude tokens low).
- Keep changes minimal; reuse existing voice.py / server.py structure.
- Commit after each task. Pre-commit gate (verify.sh) must pass before each commit.
