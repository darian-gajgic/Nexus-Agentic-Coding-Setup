"""NEXUS Agent OS — JARVIS Voice Pipeline.

GPU-accelerated STT (faster-whisper) and TTS (Piper) running locally.
No cloud calls, no API keys, zero cost.
"""
import io
import os
import wave
import time
import asyncio
import tempfile
import numpy as np
from pathlib import Path
from typing import Optional

# ── CUDA preload (must happen before ctranslate2 import) ──
import ctypes, glob
for _pattern in [
    "/usr/local/lib/ollama/cuda_v12/libcublas.so.12",
    "/usr/local/lib/ollama/cuda_v12/libcublasLt.so.12",
    "/usr/local/lib/ollama/cuda_v12/libcudart.so.12",
]:
    try:
        ctypes.CDLL(_pattern, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        pass

from faster_whisper import WhisperModel
from piper.voice import PiperVoice

PROJECT = Path(__file__).parent
PIPER_MODEL = PROJECT / "models" / "piper_voice.onnx"
PIPER_CONFIG = PROJECT / "models" / "piper_voice.onnx.json"

# ── Lazy singletons (loaded once, reused across requests) ──
_stt_model: Optional[WhisperModel] = None
_tts_voice: Optional[PiperVoice] = None
_stt_lock = asyncio.Lock()
_tts_lock = asyncio.Lock()

# ── Idle model unloading ──
# Track when each model was last used. After IDLE_TIMEOUT seconds of inactivity,
# the model is unloaded from GPU memory to free VRAM for other models.
import time as _time
IDLE_TIMEOUT = 300.0  # seconds of inactivity before unloading — MUST exceed
# the 240s chat/stream ceiling, or models unload mid-'thinking' and the
# first reply sentence pays a cold reload right when the user is waiting
_last_voice_use = 0.0  # shared: TTS + STT both count as "voice" use


def _touch_voice():
    """Record that a voice model was just used (resets the idle timer)."""
    global _last_voice_use
    _last_voice_use = _time.time()


def unload_voice_models():
    """Unload TTS + STT models from GPU memory. Called after idle timeout."""
    global _stt_model, _tts_voice
    if _stt_model is not None:
        try:
            del _stt_model
        except Exception:
            pass
        _stt_model = None
    if _tts_voice is not None:
        try:
            del _tts_voice
        except Exception:
            pass
        _tts_voice = None


def _get_stt() -> WhisperModel:
    global _stt_model
    if _stt_model is None:
        _stt_model = WhisperModel("medium.en", device="cuda", compute_type="float16")
    _touch_voice()
    return _stt_model


def _get_tts() -> PiperVoice:
    global _tts_voice
    if _tts_voice is None:
        _tts_voice = PiperVoice.load(
            str(PIPER_MODEL),
            config_path=str(PIPER_CONFIG),
        )
    _touch_voice()
    return _tts_voice


# ── STT: audio bytes → text ──
# The browser sends webm/opus (compressed container). faster-whisper can
# decode any ffmpeg-supported format when given a file path, so we save
# to a temp file and let it handle decoding. This is the correct approach
# — never try to np.frombuffer() a compressed container.

def _detect_format(audio_bytes: bytes) -> str:
    """Detect audio format from magic bytes."""
    if audio_bytes[:4] == b'RIFF':
        return '.wav'
    if audio_bytes[:4] == b'OggS' or audio_bytes[:4] == b'\x1a\x45\xdf\xa3':
        return '.webm'
    if audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb':
        return '.mp3'
    return '.webm'  # default assumption for MediaRecorder output


def _transcribe_sync(audio_bytes: bytes) -> str:
    """Transcribe audio bytes (webm, wav, mp3 — any ffmpeg-supported format)."""
    ext = _detect_format(audio_bytes)

    # Save to temp file — faster-whisper uses ffmpeg to decode any format
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        model = _get_stt()
        segments, _info = model.transcribe(tmp_path, language="en", beam_size=3, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        _touch_voice()  # completion counts as use — long turns aged out mid-flight
        return text
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def transcribe(audio_bytes: bytes) -> str:
    """Async wrapper — runs STT in a thread pool."""
    async with _stt_lock:
        return await asyncio.to_thread(_transcribe_sync, audio_bytes)


# ── TTS: text → WAV bytes ──

def _synthesize_sync(text: str) -> bytes:
    """Generate speech, return WAV file bytes (22.05kHz mono 16-bit)."""
    voice = _get_tts()
    chunks = list(voice.synthesize(text))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        for chunk in chunks:
            wav.writeframes(chunk.audio_int16_array.tobytes())

    return buf.getvalue()


async def synthesize(text: str) -> bytes:
    """Async wrapper — runs TTS in a thread pool."""
    async with _tts_lock:
        return await asyncio.to_thread(_synthesize_sync, text)


async def synthesize_stream(text: str):
    """Stream raw PCM (16-bit mono 22050 Hz) chunks as Piper produces them.
    Piper yields audio incrementally — first chunk lands in ~100-300 ms, which
    is what makes the WS voice path feel instant vs. the old whole-file WAV.
    The blocking iterator runs in a thread; chunks cross over via a queue."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=8)
    DONE = object()

    def _produce():
        try:
            voice = _get_tts()
            for chunk in voice.synthesize(text):
                loop.call_soon_threadsafe(q.put_nowait, chunk.audio_int16_array.tobytes())
        except Exception as e:
            loop.call_soon_threadsafe(q.put_nowait, e)
        finally:
            _touch_voice()
            loop.call_soon_threadsafe(q.put_nowait, DONE)

    async with _tts_lock:
        t = asyncio.get_running_loop().run_in_executor(None, _produce)
        while True:
            item = await q.get()
            if item is DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item
        await t


# ── Health check ──

def voice_status() -> dict:
    return {
        "tts_loaded": _tts_voice is not None,
        "stt_loaded": _stt_model is not None,
        "tts_engine": "piper (onnx GPU)",
        "stt_engine": "faster-whisper medium.en (cuda float16)",
        "cost": "$0.00 — fully local",
        "last_voice_use": int(_last_voice_use),
        "idle_timeout": IDLE_TIMEOUT,
    }


def check_and_unload_idle():
    """Called periodically by the server. Unloads models idle > IDLE_TIMEOUT."""
    if _last_voice_use == 0:
        return False  # never used
    if (_time.time() - _last_voice_use) > IDLE_TIMEOUT:
        if _stt_model is not None or _tts_voice is not None:
            unload_voice_models()
            return True
    return False
