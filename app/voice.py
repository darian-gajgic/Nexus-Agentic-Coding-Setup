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
import traceback
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
from piper.config import SynthesisConfig

PROJECT = Path(__file__).parent
PIPER_MODEL = PROJECT / "models" / "piper_voice.onnx"
PIPER_CONFIG = PROJECT / "models" / "piper_voice.onnx.json"

# ── Lazy singletons (loaded once, reused across requests) ──
_stt_model: Optional[WhisperModel] = None
_stt_loaded_key: Optional[tuple] = None  # (model_name, device) actually loaded
_stt_gpu_block_until = 0.0  # after a CUDA failure, skip the GPU until this time
GPU_RETRY_COOLDOWN = 600.0  # seconds on CPU before giving CUDA another chance
_tts_voice: Optional[PiperVoice] = None
_tts_loaded_path: Optional[str] = None  # which .onnx is currently loaded
_stt_lock = asyncio.Lock()
_tts_lock = asyncio.Lock()


def _conf(key: str, default: str) -> str:
    """Settings-registry lookup that degrades to the default if the registry
    (and its db import) isn't available — voice must work standalone."""
    try:
        import settings_registry as sreg
        v = sreg.conf(key)
        return v if v not in (None, "") else default
    except Exception:
        return default

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


def _drop_stt():
    global _stt_model, _stt_loaded_key
    _stt_model = None
    _stt_loaded_key = None


def unload_voice_models():
    """Unload TTS + STT models from GPU memory. Called after idle timeout."""
    global _tts_voice, _tts_loaded_path
    _drop_stt()
    if _tts_voice is not None:
        try:
            del _tts_voice
        except Exception:
            pass
        _tts_voice = None
        _tts_loaded_path = None


def _stt_target() -> tuple:
    """(model_name, device) the next load should use, honoring settings and
    the post-CUDA-failure cooldown."""
    model_name = _conf("voice.stt_model", "medium.en")
    pref = _conf("voice.stt_device", "auto")
    if pref == "cpu":
        device = "cpu"
    elif pref == "cuda":
        device = "cuda"
    else:  # auto
        device = "cpu" if _time.time() < _stt_gpu_block_until else "cuda"
    return model_name, device


def _get_stt() -> WhisperModel:
    global _stt_model, _stt_loaded_key
    key = _stt_target()
    if _stt_model is None or _stt_loaded_key != key:
        _drop_stt()
        model_name, device = key
        compute = "float16" if device == "cuda" else "int8"
        print(f"[voice] loading STT {model_name} on {device} ({compute})", flush=True)
        _stt_model = WhisperModel(model_name, device=device, compute_type=compute)
        _stt_loaded_key = key
    _touch_voice()
    return _stt_model


def _tts_target() -> str:
    """Absolute path of the .onnx voice to use. Setting `voice.tts_voice` (abs or
    relative to the app dir) picks a voice; anything missing/broken → the base
    Piper model, which is always present. All Piper voices here are 22050 Hz — the
    rate the WS/HTTP paths assume; a non-22050 voice is refused so playback can't
    silently run at the wrong speed."""
    v = _conf("voice.tts_voice", "")
    if v:
        p = v if os.path.isabs(v) else str(PROJECT / v)
        if os.path.exists(p) and os.path.exists(p + ".json"):
            try:
                import json as _json
                sr = _json.load(open(p + ".json")).get("audio", {}).get("sample_rate")
                if sr in (None, 22050):
                    return p
                print(f"[voice] ignoring {os.path.basename(p)} — {sr}Hz != 22050", flush=True)
            except Exception:
                return p  # unreadable config → trust it, Piper will validate
    return str(PIPER_MODEL)


def _syn_config() -> SynthesisConfig:
    """Per-synthesis Piper config. Speed = setting `voice.tts_speed` (1.0 = the
    voice's native pace); Piper's length_scale is the inverse, so 1.25× → 0.8.
    Read fresh each call so a speed change applies to the next sentence live."""
    try:
        speed = float(_conf("voice.tts_speed", "1.0"))
    except (TypeError, ValueError):
        speed = 1.0
    speed = min(2.0, max(0.5, speed))  # sane bounds; extremes garble Piper
    return SynthesisConfig(length_scale=1.0 / speed)


def _get_tts() -> PiperVoice:
    global _tts_voice, _tts_loaded_path
    target = _tts_target()
    if _tts_voice is None or _tts_loaded_path != target:
        try:
            _tts_voice = PiperVoice.load(target, config_path=target + ".json")
            _tts_loaded_path = target
            print(f"[voice] loaded TTS voice {os.path.basename(target)}", flush=True)
        except Exception as e:
            if target != str(PIPER_MODEL):
                print(f"[voice] voice {os.path.basename(target)} failed to load "
                      f"({e!r}) — falling back to base model", flush=True)
                _tts_voice = PiperVoice.load(str(PIPER_MODEL), config_path=str(PIPER_CONFIG))
                _tts_loaded_path = str(PIPER_MODEL)
            else:
                raise
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


def _run_transcribe(tmp_path: str) -> str:
    model = _get_stt()
    lang = _conf("voice.stt_language", "en") or None  # empty = autodetect
    if lang and _stt_loaded_key and _stt_loaded_key[0].endswith(".en"):
        lang = "en"  # english-only checkpoints reject other language hints
    segments, _info = model.transcribe(tmp_path, language=lang, beam_size=3, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    _touch_voice()  # completion counts as use — long turns aged out mid-flight
    return text


def _transcribe_sync(audio_bytes: bytes) -> str:
    """Transcribe audio bytes (webm, wav, mp3 — any ffmpeg-supported format).

    Self-healing: a CUDA hiccup (OOM / cudaErrorInvalidDevice under VRAM
    contention with the vision worker or ollama) used to surface as a silent
    500 to the browser. Now: log it, drop + reload the model and retry once;
    if that also fails, block the GPU for GPU_RETRY_COOLDOWN and answer from
    a CPU int8 model — STT degrades instead of dying.
    """
    ext = _detect_format(audio_bytes)

    # Save to temp file — faster-whisper uses ffmpeg to decode any format
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    global _stt_gpu_block_until
    try:
        try:
            return _run_transcribe(tmp_path)
        except Exception as e:
            print(f"[voice] STT failed ({e!r}) — dropping model and retrying", flush=True)
            traceback.print_exc()
            # loaded_key is None when the LOAD itself failed — judge by target
            was_cuda = (_stt_loaded_key or _stt_target())[1] == "cuda"
            _drop_stt()
            try:
                return _run_transcribe(tmp_path)
            except Exception as e2:
                if not was_cuda:
                    raise  # already on CPU — a third identical attempt won't help
                print(f"[voice] STT retry failed ({e2!r}) — CPU fallback for "
                      f"{GPU_RETRY_COOLDOWN:.0f}s", flush=True)
                traceback.print_exc()
                _stt_gpu_block_until = _time.time() + GPU_RETRY_COOLDOWN
                _drop_stt()
                return _run_transcribe(tmp_path)
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
    chunks = list(voice.synthesize(text, _syn_config()))

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
            for chunk in voice.synthesize(text, _syn_config()):
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
    model_name, device = _stt_loaded_key or _stt_target()
    return {
        "tts_loaded": _tts_voice is not None,
        "stt_loaded": _stt_model is not None,
        "tts_engine": "piper (onnx CPU)",
        "tts_voice": os.path.basename(_tts_loaded_path or _tts_target()).replace(".onnx", ""),
        "stt_engine": f"faster-whisper {model_name} ({device})",
        "stt_gpu_cooldown_s": max(0, int(_stt_gpu_block_until - _time.time())),
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
