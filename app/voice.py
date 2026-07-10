"""NEXUS Agent OS — JARVIS Voice Pipeline.

TTS: Piper (onnx, CPU, zero VRAM) — loaded in-process, streaming synthesis.
STT: faster-whisper large-v3 — the ONE speech-to-text model for the whole
machine (JARVIS mic, dictation, meeting mode), hosted in a killable
subprocess (stt_worker.py). This module is the worker CLIENT: it spawns the
worker on demand, serializes every caller onto its JSON-lines pipe, and kills
it after `voice.stt_idle_timeout` seconds of STT inactivity — process death
reclaims 100% of the VRAM including the CUDA context ctranslate2 pins
(in-process unloading never freed those ~158MiB).

No cloud calls, no API keys, zero cost.
"""
import gc
import io
import os
import json
import wave
import time
import asyncio
import tempfile
import threading
import subprocess
import numpy as np
from pathlib import Path
from typing import Optional

from piper.voice import PiperVoice
from piper.config import SynthesisConfig

PROJECT = Path(__file__).parent
PIPER_MODEL = PROJECT / "models" / "piper_voice.onnx"
PIPER_CONFIG = PROJECT / "models" / "piper_voice.onnx.json"
STT_WORKER = PROJECT / "stt_worker.py"
STT_LOG = PROJECT / "logs" / "stt_worker.log"
(PROJECT / "logs").mkdir(exist_ok=True)

# ── STT worker client state ──
_stt_proc: Optional[subprocess.Popen] = None
_stt_proc_key: Optional[tuple] = None  # (model, device, compute) of the live worker
_stt_loaded = False                    # last reported model-in-memory state
_stt_gpu_block_until = 0.0  # after a CUDA failure, spawn on CPU until this time
GPU_RETRY_COOLDOWN = 600.0  # seconds on CPU before giving CUDA another chance
# Serializes ALL pipe access: the async JARVIS path (via asyncio.to_thread),
# the dictation session thread and the meeting worker thread. Must be a
# threading.Lock, not asyncio — two of the three callers are plain threads.
_stt_io_lock = threading.Lock()
_warm_guard = threading.Lock()
_warm_thread: Optional[threading.Thread] = None

# ── TTS state ──
_tts_voice: Optional[PiperVoice] = None
_tts_loaded_path: Optional[str] = None  # which .onnx is currently loaded
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
# STT and TTS idle timers are SEPARATE (memory-audit finding #10: frequent
# CPU-TTS completions used to keep the GPU whisper resident past its window).
import time as _time
IDLE_TIMEOUT = 300.0  # TTS idle unload — MUST exceed the 240s chat/stream
# ceiling, or Piper unloads mid-'thinking' and the first reply sentence pays
# a cold reload right when the user is waiting
_last_stt_use = 0.0
_last_tts_use = 0.0


def _touch_stt():
    global _last_stt_use
    _last_stt_use = _time.time()


def _touch_tts():
    global _last_tts_use
    _last_tts_use = _time.time()


# ── STT worker lifecycle ────────────────────────────────────────────────────

def _stt_spawn_key() -> tuple:
    """(model, device, compute) the next worker spawn should use, honoring
    settings and the post-CUDA-failure cooldown."""
    model = _conf("voice.stt_model", "large-v3")
    pref = _conf("voice.stt_device", "auto")
    if pref == "cpu":
        device = "cpu"
    elif pref == "cuda":
        device = "cuda"
    else:  # auto
        device = "cpu" if _time.time() < _stt_gpu_block_until else "cuda"
    compute = _conf("voice.stt_compute", "int8_float16")
    return model, device, compute


def _worker_env() -> dict:
    """start.sh sets LD_LIBRARY_PATH for cuDNN/cuBLAS; re-derive it here as
    belt-and-braces so the worker gets CUDA libs even when the parent wasn't
    launched through start.sh (manual runs, tests)."""
    env = dict(os.environ)
    dirs = [
        os.path.expanduser("~/ml-env/lib/python3.14/site-packages/nvidia/cu13/lib"),
        os.path.expanduser("~/ml-env/lib/python3.14/site-packages/nvidia/cudnn/lib"),
    ]
    current = env.get("LD_LIBRARY_PATH", "")
    missing = [d for d in dirs if d not in current]
    if missing:
        env["LD_LIBRARY_PATH"] = ":".join(missing + ([current] if current else []))
    return env


def _spawn_stt_worker(key: tuple) -> subprocess.Popen:
    model, device, compute = key
    print(f"[voice] spawning stt worker: {model} on {device} ({compute})", flush=True)
    logf = open(STT_LOG, "ab")  # worker stderr — NEVER devnull (respawn loops
    try:                        # must be diagnosable; audit lesson)
        return subprocess.Popen(
            [str(PROJECT / ".venv" / "bin" / "python"), str(STT_WORKER),
             "--model", model, "--device", device, "--compute", compute],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=logf,
            cwd=str(PROJECT), text=True, bufsize=1, env=_worker_env())
    finally:
        logf.close()  # child holds its own dup of the fd


def _stt_worker_alive() -> bool:
    return _stt_proc is not None and _stt_proc.poll() is None


def _kill_stt_worker(reason: str = ""):
    global _stt_proc, _stt_proc_key, _stt_loaded
    p, _stt_proc = _stt_proc, None
    _stt_proc_key = None
    _stt_loaded = False
    if p is not None:
        try:
            p.kill()
            p.wait(timeout=5)
        except Exception:
            pass
        if reason:
            print(f"[voice] stt worker killed: {reason}", flush=True)


def _ask_stt_sync(req: dict, timeout: float = 90.0) -> dict:
    """One request/response on the worker pipe, serialized by _stt_io_lock.

    Timeout discipline: a timer kills the worker if the response doesn't land
    in time — pipe EOF then unblocks readline, so neither sync (dictation/
    meeting) nor async (JARVIS) callers can hang forever, and the desynced
    pipe is never reused (same rationale as the vision worker's
    kill-and-respawn: a late reply would answer the NEXT request)."""
    global _stt_proc, _stt_proc_key, _stt_gpu_block_until, _stt_loaded
    with _stt_io_lock:
        key = _stt_spawn_key()
        if not _stt_worker_alive() or _stt_proc_key != key:
            if _stt_proc_key not in (None, key):
                _kill_stt_worker(f"config change {_stt_proc_key} -> {key}")
            else:
                _kill_stt_worker()
            _stt_proc = _spawn_stt_worker(key)
            _stt_proc_key = key
        _touch_stt()
        op = req.get("op", "?")
        timer = threading.Timer(
            timeout, _kill_stt_worker, [f"{op} timed out after {timeout:.0f}s"])
        timer.daemon = True
        timer.start()
        try:
            _stt_proc.stdin.write(json.dumps(req) + "\n")
            _stt_proc.stdin.flush()
            line = _stt_proc.stdout.readline()
        except Exception as e:
            _kill_stt_worker(f"pipe error on {op}: {e!r}")
            raise RuntimeError(f"stt worker pipe error: {e}") from e
        finally:
            timer.cancel()
        _touch_stt()
        if not line:
            _kill_stt_worker(f"died mid-{op}")
            raise RuntimeError(f"stt worker died mid-request ({op})")
        resp = json.loads(line)
        if resp.get("fallback"):
            # The worker had to drop to CPU (OOM after lock-wait + eviction).
            # Block CUDA at the next spawn too, so an idle-kill + respawn
            # during sustained contention doesn't pay a doomed CUDA load.
            _stt_gpu_block_until = _time.time() + GPU_RETRY_COOLDOWN
        if "loaded" in resp:
            _stt_loaded = bool(resp["loaded"])
        elif "text" in resp:
            _stt_loaded = True
        if resp.get("error"):
            raise RuntimeError(resp["error"])
        return resp


def _transcribe_path(path: str, language: Optional[str] = None,
                     beam_size: int = 3, vad_filter: bool = True,
                     initial_prompt: Optional[str] = None) -> str:
    resp = _ask_stt_sync({
        "op": "transcribe", "path": path, "language": language,
        "beam_size": beam_size, "vad_filter": vad_filter,
        "initial_prompt": initial_prompt,
        "condition_on_previous_text": False,
    })
    return resp.get("text", "")


# ── STT: audio bytes → text ──
# The browser sends webm/opus (compressed container). faster-whisper can
# decode any ffmpeg-supported format when given a file path, so we save
# to a temp file and hand the worker the path. Never np.frombuffer() a
# compressed container.

def _detect_format(audio_bytes: bytes) -> str:
    """Detect audio format from magic bytes."""
    if audio_bytes[:4] == b'RIFF':
        return '.wav'
    if audio_bytes[:4] == b'OggS' or audio_bytes[:4] == b'\x1a\x45\xdf\xa3':
        return '.webm'
    if audio_bytes[:3] == b'ID3' or audio_bytes[:2] == b'\xff\xfb':
        return '.mp3'
    return '.webm'  # default assumption for MediaRecorder output


def _transcribe_bytes_sync(audio_bytes: bytes) -> str:
    ext = _detect_format(audio_bytes)
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        lang = _conf("voice.stt_language", "en") or None  # empty = autodetect
        return _transcribe_path(tmp_path, language=lang, beam_size=3)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def transcribe(audio_bytes: bytes) -> str:
    """Async wrapper — the pipe call runs in a thread pool (it blocks on the
    io-lock + worker response; self-times-out via _ask_stt_sync's timer)."""
    return await asyncio.to_thread(_transcribe_bytes_sync, audio_bytes)


def transcribe_pcm(pcm, sample_rate: int = 16000,
                   language: Optional[str] = None, beam_size: int = 5,
                   vad_filter: bool = True,
                   initial_prompt: Optional[str] = None) -> str:
    """SYNC entry for the dictation and meeting threads: float32 mono PCM →
    text via the shared worker (writes a temp WAV, same one-path protocol)."""
    pcm = np.clip(np.asarray(pcm, dtype=np.float32), -1.0, 1.0)
    if pcm.size == 0:
        return ""
    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(tmp_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes((pcm * 32767.0).astype("<i2").tobytes())
        return _transcribe_path(tmp_path, language=language,
                                beam_size=beam_size, vad_filter=vad_filter,
                                initial_prompt=initial_prompt)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def warm_stt() -> dict:
    """Non-blocking: start loading the STT model in the background. Called on
    JARVIS mic-press and on the dictation hotkey-down so large-v3 loads WHILE
    the user is still speaking. Safe from any thread; dedup-guarded."""
    global _warm_thread
    with _warm_guard:
        if _stt_loaded and _stt_worker_alive() and _stt_proc_key == _stt_spawn_key():
            return {"warming": False, "loaded": True}
        if _warm_thread is not None and _warm_thread.is_alive():
            return {"warming": True, "loaded": False}

        def _warm():
            try:
                _ask_stt_sync({"op": "warm"}, timeout=120.0)
            except Exception as e:
                print(f"[voice] stt warm failed: {e!r}", flush=True)

        _warm_thread = threading.Thread(target=_warm, daemon=True, name="stt-warm")
        _warm_thread.start()
        return {"warming": True, "loaded": False}


# ── TTS ─────────────────────────────────────────────────────────────────────

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
    _touch_tts()
    return _tts_voice


def _drop_tts():
    global _tts_voice, _tts_loaded_path
    if _tts_voice is not None:
        try:
            del _tts_voice
        except Exception:
            pass
        _tts_voice = None
        _tts_loaded_path = None
        gc.collect()


def unload_voice_models():
    """Kill the STT worker + drop Piper. Called on idle timeout / teardown."""
    _kill_stt_worker("unload requested")
    _drop_tts()


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
            _touch_tts()
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
    model, device, compute = _stt_proc_key or _stt_spawn_key()
    try:
        stt_idle = float(_conf("voice.stt_idle_timeout", "300"))
    except (TypeError, ValueError):
        stt_idle = 300.0
    return {
        "tts_loaded": _tts_voice is not None,
        "stt_loaded": _stt_loaded and _stt_worker_alive(),
        "stt_worker_alive": _stt_worker_alive(),
        "tts_engine": "piper (onnx CPU)",
        "tts_voice": os.path.basename(_tts_loaded_path or _tts_target()).replace(".onnx", ""),
        "stt_engine": f"faster-whisper {model} ({device}, {compute}) [worker]",
        "stt_gpu_cooldown_s": max(0, int(_stt_gpu_block_until - _time.time())),
        "cost": "$0.00 — fully local",
        "last_stt_use": int(_last_stt_use),
        "last_tts_use": int(_last_tts_use),
        "stt_idle_timeout": stt_idle,
        "idle_timeout": IDLE_TIMEOUT,
    }


def check_and_unload_idle():
    """Called periodically by the server (15s loop). STT: kill the worker
    after `voice.stt_idle_timeout` s of STT inactivity (process death = full
    VRAM reclaim). TTS: drop Piper after IDLE_TIMEOUT s of TTS inactivity.
    The timers are independent — see the memory-audit note above."""
    did = False
    try:
        stt_idle = float(_conf("voice.stt_idle_timeout", "300"))
    except (TypeError, ValueError):
        stt_idle = 300.0
    if (_stt_worker_alive() and _last_stt_use
            and (_time.time() - _last_stt_use) > stt_idle):
        # never kill mid-request: the io-lock is held while a request is in
        # flight — try-acquire and skip this tick if the worker is busy
        if _stt_io_lock.acquire(blocking=False):
            try:
                _kill_stt_worker(f"idle > {stt_idle:.0f}s — VRAM freed")
            finally:
                _stt_io_lock.release()
            did = True
    if (_tts_voice is not None and _last_tts_use
            and (_time.time() - _last_tts_use) > IDLE_TIMEOUT):
        _drop_tts()
        did = True
    return did
