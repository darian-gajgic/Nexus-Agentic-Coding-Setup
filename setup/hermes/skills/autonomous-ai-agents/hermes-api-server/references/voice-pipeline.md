# Voice Pipeline Integration: Mic → STT → Hermes SSE → TTS → Avatar

Pattern for adding real voice conversation to a Hermes-powered UI: the browser
captures mic audio, a GPU-accelerated STT transcribes it, the text goes to
Hermes via the SSE streaming chat endpoint, and the response is spoken back via
GPU TTS — with sentence-by-sentence playback that starts before the full
response is generated.

All processing runs locally on the user's GPU. Zero cloud calls for STT/TTS.

## Architecture

```
Browser (mic)           Backend (FastAPI)           Hermes API (8642)
    │                          │                          │
    │── audio blob ──────────► │                          │
    │   POST /stt              │                          │
    │                    faster-whisper (GPU)              │
    │◄── {text} ───────────── │                          │
    │                          │                          │
    │── POST /chat/stream ──►  │── POST /chat/stream ───► │
    │   (fetch ReadableStream) │   (httpx SSE proxy)      │
    │                          │◄── SSE events ────────── │
    │◄── SSE chunks ────────── │                          │
    │   parse assistant.delta  │                          │
    │   buffer until .!?       │                          │
    │── POST /tts (sentence) ► │                          │
    │                    piper TTS (GPU)                   │
    │◄── WAV audio ◄────────── │                          │
    │   play via Audio element │                          │
    │   (queued, non-blocking) │                          │
```

## Components

### STT: faster-whisper on GPU

```python
# voice.py — lazy singleton, loaded once
import ctypes
# CRITICAL: preload CUDA libs before ctranslate2 import (see CUDA section below)

from faster_whisper import WhisperModel
_stt = WhisperModel("medium.en", device="cuda", compute_type="float16")

def transcribe(audio_bytes: bytes, sample_rate=16000) -> str:
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = _stt.transcribe(audio, language="en", beam_size=3, vad_filter=True)
    return " ".join(s.text.strip() for s in segments).strip()
```

### TTS: Piper (ONNX, GPU via onnxruntime)

```python
from piper.voice import PiperVoice
_tts = PiperVoice.load("models/piper_voice.onnx", config_path="models/piper_voice.onnx.json")

def synthesize(text: str) -> bytes:
    chunks = list(_tts.synthesize(text))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(22050)
        for chunk in chunks:
            wav.writeframes(chunk.audio_int16_array.tobytes())  # NOTE: .audio_int16_array, not .audio
    return buf.getvalue()
```

**Piper AudioChunk attributes** (v1.4.x): `audio_int16_array` (numpy),
`audio_int16_bytes`, `audio_float_array`, `sample_rate`, `sample_width`,
`sample_channels`, `phonemes`. The older `.audio` attribute does NOT exist.

### FastAPI endpoints

```python
@app.post("/api/stt")
async def stt(file: UploadFile = File(...)):
    audio = await file.read()
    text = await transcribe(audio)
    return {"text": text}

@app.post("/api/tts")
async def tts(body: dict):
    wav = await synthesize(body["text"])
    return RawResponse(content=wav, media_type="audio/wav")
```

Requires `python-multipart` for `UploadFile` support:
`.venv/bin/pip install python-multipart`

### Frontend: mic capture + level meter

```javascript
async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1 }
    });
    // Level meter via AnalyserNode
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);

    // Record as webm (browser native), backend handles conversion
    const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    const chunks = [];
    recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = () => processRecording(new Blob(chunks, { type: 'audio/webm' }));
    recorder.start();
}
```

### Frontend: sentence-buffered TTS streaming (the key trick)

The response text streams in via SSE delta events. Instead of waiting for the
full response before speaking, buffer text until a sentence boundary (`.!?`) is
hit, then send that sentence to TTS immediately. This gives ~1-2s perceived
latency instead of waiting for the entire generation.

**IMPORTANT — event name variants:** Different Hermes API versions and proxy
layers emit different SSE event names for text deltas. Handle ALL of them:
`assistant.delta`, `text_delta`, `text`, `content_block_delta`. The delta text
payload may be under `.delta`, `.delta.text`, or `.text` depending on source.
Also handle tool events: `tool.started`, `tool_use`, `tool_call`.

```javascript
const TEXT_EVENTS = ['assistant.delta', 'text_delta', 'text', 'content_block_delta'];

let sentenceBuffer = '';
// Inside the SSE handler:
if (TEXT_EVENTS.includes(eventName)) {
    const parsed = JSON.parse(data);
    const chunk = parsed.delta?.text || parsed.text || parsed.delta || '';
    fullText += chunk;
    sentenceBuffer += chunk;

    // Sentence boundary → speak immediately
    const end = sentenceBuffer.search(/[.!?]\s/);
    if (end >= 0) {
        const sentence = sentenceBuffer.slice(0, end + 1);
        sentenceBuffer = sentenceBuffer.slice(end + 1);
        speakText(sentence);  // queues for playback, non-blocking
    }
}
// After stream ends: speak any remaining text in buffer
```

### Frontend: TTS playback queue

Audio plays sequentially via a queue so sentences don't overlap:

```javascript
let currentAudio = null;
const ttsQueue = [];

async function speakText(text) {
    ttsQueue.push(text);
    if (currentAudio) return;  // queue will process
    while (ttsQueue.length > 0) {
        const sentence = ttsQueue.shift();
        const resp = await fetch('/api/tts', {method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({text: sentence})});
        const blob = await resp.blob();
        currentAudio = new Audio(URL.createObjectURL(blob));
        await new Promise(r => { currentAudio.onended = r; currentAudio.play(); });
        URL.revokeObjectURL(currentAudio.src);
        currentAudio = null;
    }
}
```

### Avatar animation states

The avatar has 4 behavioral modes that sync to the voice pipeline state.
This applies to both frame-cycling avatars (video/sequenced images) and 3D
Three.js head meshes (see `web-dashboard-apps/references/threejs-avatar-pattern.md`):

| State | Trigger | Frame-cycling avatar | 3D Three.js avatar |
|-------|---------|----------------------|--------------------|
| idle | default | slow frame cycling, breathing offset | subtle sway + blink, dim emissive |
| listening | mic recording starts | subtle movement | cyan pulse, faster ring particles |
| thinking | STT transcribing or LLM processing | scanline sweep, fast frame cycle | yellow pulse, extra head rotation |
| talking | TTS audio playing | rapid frame alternation (lip-sync sim) | real jaw deformation via Web Audio AnalyserNode amplitude |

For the 3D avatar, lip-sync uses a Web Audio `AnalyserNode` connected to the TTS
`Audio` element. The per-frame average frequency amplitude drives jaw position
via `avatar.setAudioLevel(avg)`. Smooth interpolation
(`currentJaw += (target - currentJaw) * 0.25`) prevents jitter.

## CUDA Library Coexistence (the hard part)

When running both onnxruntime-gpu (needs CUDA 13) and ctranslate2/faster-whisper
(needs CUDA 12) in the same Python process on a Blackwell GPU (RTX 50-series):

See `references/cuda-mixed-version.md` for the full patchelf + ctypes preload
solution.

## Performance (RTX 5070 Ti)

- STT (faster-whisper medium.en, float16): ~0.2-0.4s for a short utterance
- TTS (Piper, ONNX): ~0.15s for a sentence (30x realtime RTF)
- Total voice turn latency: 2-5s (dominated by LLM generation, not STT/TTS)
- VRAM: ~3-4GB for both models loaded simultaneously

## Models

- STT: `faster-whisper` with `medium.en` model (~1.5GB VRAM, float16)
- TTS: Piper `en_US-amy-medium` voice (~61MB ONNX model)
  - Download from: `https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium/en_US-amy-medium.onnx`
  - Config: same URL with `.json` suffix
