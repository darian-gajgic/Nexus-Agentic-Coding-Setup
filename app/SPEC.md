# SPEC — JARVIS Neural Talking-Head Avatar (v2)

> ⚠️ HISTORICAL (superseded 2026-07-08): the Wav2Lip avatar this spec describes
> was retired. The live avatar is the Three.js particle head (`static/jarvis3d.js`)
> driven by WS TTS (`/ws/jarvis/tts`); `/api/jarvis/talk` + `/api/jarvis/lipsync`
> return 410 Gone. See `docs/JARVIS-VOICE.md` §0 for the current stack.

> Spec-driven build, 2026-07-03. Treat as a client deliverable.
> Source of truth. The implementation must satisfy every numbered requirement.

## Context & Goal

The current JARVIS feature has two failures: (1) the "avatar" is a sequence of static
cycling frames (not a 3D/animated face), and (2) the conversation mode (speak → listen →
reply) is broken — mic recording fails, and there is no continuous live loop.

Goal: replace the avatar with a NEURAL TALKING-HEAD — your real face, lip-synced to TTS
audio via a local Wav2Lip model — and ship a working live conversation mode. Free/local only.

## Technical Approach (decided)

- **Avatar:** Wav2Lip (local, GPU, ~500MB model). Input: one reference photo of your face.
  For each TTS reply (streamed per sentence), the server renders a short lip-synced video
  clip; the browser plays it. Neural lip-sync, real face.
- **Conversation mode:** continuous loop — mic records → STT (faster-whisper) → LLM
  (GLM-5.2 via Hermes API) → TTS (Piper) per sentence → Wav2Lip render → play → auto-listen.
- **HTTPS for mic:** getUserMedia needs a secure context. Fix via localhost (already works)
  or a local self-signed cert + explicit browser trust.
- **Inference env:** `/home/sinep/ml-env` (torch 2.14 + CUDA 13.0, working). The nexus
  server stays in its own venv but shells out to ml-env for Wav2Lip inference.

## Requirements (numbered, testable)

### Avatar
1. The avatar displayed is the user's REAL face (from the video), not a procedural mesh
   and not a cycling static frame.
2. While TTS audio plays, the avatar's mouth is lip-synced (Wav2Lip neural model).
3. Source face image is auto-extracted from `/home/sinep/jarvis/face.mp4` — best
   front-facing, well-lit, neutral-mouth frame — using a face-detection quality scorer.
4. The rendered avatar video plays smoothly in the browser at the TTS audio's natural rate.
5. Avatar state drives the UI: `idle`, `listening` (mic active), `thinking` (LLM processing),
   `talking` (lip-sync video playing). Visual indicator for each state.
6. Between talking clips (idle), a subtle fallback animation shows so the face is never
   frozen/static — e.g. the last video frame gently "breathes" (scale/opacity micro-motion).

### Conversation Mode (live loop)
7. Clicking the mic button starts recording; clicking again stops and submits. This MUST
   work (was broken).
8. After the avatar finishes talking, conversation mode auto-resumes listening (if enabled
   via a toggle) so it feels like a live conversation — no need to click again each time.
9. A "conversation mode" toggle clearly indicates whether auto-listen is on.
10. Mic recording works over the access method the user actually uses (localhost OR LAN IP
    via HTTPS). If LAN/HTTP, document/provide the HTTPS fix.

### Backend
11. New endpoint `POST /api/jarvis/lipsync` accepts an audio file, runs Wav2Lip against the
    reference face, returns a video file (mp4/webm) the browser can play. Must be streaming-
    friendly: one call per sentence, returns fast enough for live feel (~1-3s/sentence).
12. Wav2Lip runs in `/home/sinep/ml-env` (the env with working CUDA). Models cached under
    the project (gitignored). Cold-start load is lazy (first request loads model, subsequent
    reuse the loaded model).
13. The existing STT (faster-whisper) and TTS (Piper) pipelines remain unchanged and working.
14. The chat flow (SSE streaming from Hermes API) is preserved — the reply is split into
    sentences, each sentence is TTS'd then lip-synced then played in sequence.

## Out of Scope (explicitly)
- Real-time 60fps neural generation (technically impossible with Wav2Lip — it renders
  offline then plays. This is stated, not hidden.)
- Multi-face / other people's faces.
- Fine emotion control (happy/sad/angry driving) — Wav2Lip does lip-sync, not emotion.
  Emotion is out of scope for this version.
- Mobile/responsive polish (desktop dashboard only).
- VTuber full-body — head/face only, as the source video shows.

## Verification (the exact end-to-end check that proves it works)

1. Start server: `cd /home/sinep/nexus-agent-os && bash start.sh`
2. Open `http://localhost:8777` in a browser → JARVIS view.
3. Avatar shows the user's real face (not a procedural mesh), in `idle` state with subtle motion.
4. Type a message → send. Observe: reply streams, TTS plays, and the avatar's MOUTH MOVES
   in sync with the audio (lip-sync video), state = `talking`.
5. Click mic → grant permission → speak a short phrase → click mic to stop. Observe: state
   = `listening` then `thinking`, then the spoken text appears and the avatar replies with
   lip-sync.
6. Toggle "conversation mode" ON. After the avatar finishes talking, it auto-returns to
   listening without a click.
7. `bash scripts/verify.sh` passes (syntax + API + function integrity).

## Risks / Open Questions
- Wav2Lip quality depends on the source frame. If the auto-extracted frame is poor, lip-sync
  looks off. Mitigation: extract multiple candidates, score them, pick the best.
- Per-sentence render delay (~1-3s) on the GPU. Acceptable for "live feel" but not instant.
- Wav2Lip on sm_120 (Blackwell) may need a build tweak — will verify on first run.
- Wav2Lip model + GFPGAN enhancer adds ~1-2GB. Plenty of disk (177GB free).
