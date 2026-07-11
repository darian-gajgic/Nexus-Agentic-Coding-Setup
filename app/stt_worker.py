"""NEXUS STT worker — owns the ONE faster-whisper model for the whole machine.

Long-lived subprocess owned by voice.py. JSON-lines protocol on stdin/stdout:
one request object per line in, one response object per line out, same order.
The serial loop IS the request queue — every STT caller on this box (JARVIS
mic, dictation, meeting mode) is serialized right here, which replaces the old
WisprFlow model_lock.

Ops:
  {"op":"ping"}                    -> {"ok":true,"loaded":false,"device":"cuda"}
  {"op":"warm"}                    -> {"ok":true,"loaded":true,"device":"cuda",
                                       "model":"large-v3","compute":"int8_float16",
                                       "elapsed":4.2,"fallback":false}
  {"op":"transcribe","path":P,"language":"en","beam_size":3,"vad_filter":true,
   "initial_prompt":null,"condition_on_previous_text":false}
                                   -> {"text":"...","device":"cuda",
                                       "elapsed":1.3,"fallback":false}

The PARENT enforces idle lifetime by killing this process — VRAM (weights AND
the ~158MiB CUDA context ctranslate2 pins) is freed by process exit, the same
discipline as the vision worker.

GPU-first policy: load on CUDA, WAIT on the cross-process gpu_lock (the
machine's GPU waiting line, shared with SigLIP/SDXL/VLM), evict resident-but-
idle ollama models when VRAM is short, and only fall back to CPU when all of
that failed. CPU is an emergency net, not a placement policy — WisprFlow's
adaptive demote/promote monitor is deliberately NOT ported here: its two
disagreeing GPU probes made it thrash placement every ~10s, leaking host
memory until the kernel OOM-killed the daemon mid-dictation (journal-proven,
2026-07-08). One load per worker life; no reload cycles.

Errors never kill the loop: each request gets {"error": "..."} and the worker
keeps serving. stdout is protocol-only — ALL logging goes to stderr (the
parent pipes it to logs/stt_worker.log).
"""
import argparse
import gc
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request

import gpu_lock  # sys.path[0] is this script's dir — the app tree


def log(msg: str):
    print(f"[stt-worker] {msg}", file=sys.stderr, flush=True)


# ── CUDA preload (must happen before ctranslate2 import) ──
import ctypes
for _lib in [
    "/usr/local/lib/ollama/cuda_v12/libcublas.so.12",
    "/usr/local/lib/ollama/cuda_v12/libcublasLt.so.12",
    "/usr/local/lib/ollama/cuda_v12/libcudart.so.12",
]:
    try:
        ctypes.CDLL(_lib, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        pass

from faster_whisper import WhisperModel

_ap = argparse.ArgumentParser()
_ap.add_argument("--model", default="large-v3")
_ap.add_argument("--device", default="cuda", choices=("cuda", "cpu"))
_ap.add_argument("--compute", default="int8_float16")
args = _ap.parse_args()

_model = None
_device = args.device  # flips to "cpu" after the first CUDA failure, for the
                       # worker's life — a respawn after idle retries CUDA
_fallback_used = False
_test_oom_fired = False  # NEXUS_STT_TEST_OOM=1 injects ONE fake CUDA OOM

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
# weights + CUDA context + decode workspace margin, per compute type
NEEDED_MIB = {"int8_float16": 2500, "int8": 2500, "float16": 3800}


def _is_gpu_failure(e: Exception) -> bool:
    """CUDA-side failure (OOM / cudaErrorInvalidDevice / cuBLAS / cuDNN /
    alloc) — the class of errors where retrying CUDA under VRAM contention
    just fails again, so the right move is straight to CPU."""
    s = str(e).lower()
    return any(sig in s for sig in (
        "out of memory", "cuda", "cublas", "cudnn", "failed to allocate"))


def _http_json(url: str, payload: dict | None = None, timeout: float = 5.0):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _free_vram_mib() -> int:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip().splitlines()[0])
    except Exception:
        return -1


def _evict_idle_ollama():
    """keep_alive:0 every model resident on the MAIN ollama (:11434) — evicts
    resident-but-idle campers (mem0 leftovers, an expired-window VLM). Safe:
    we hold gpu_lock so no Nexus VLM/SigLIP call is mid-flight, and ollama
    never interrupts a model mid-inference — an eviction request queues behind
    any in-flight generation. NEVER touches :11435 (the dictation-cleanup
    gemma is about to be used right after this STT call)."""
    try:
        models = _http_json(f"{OLLAMA_URL}/api/ps").get("models") or []
    except Exception as e:
        log(f"evict: /api/ps unreachable ({e!r})")
        return
    for m in models:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        try:
            _http_json(f"{OLLAMA_URL}/api/generate",
                       {"model": name, "keep_alive": 0}, timeout=10)
            log(f"evict: asked ollama to unload {name}")
        except Exception:
            try:  # embedding-only models reject /api/generate
                _http_json(f"{OLLAMA_URL}/api/embed",
                           {"model": name, "input": "", "keep_alive": 0},
                           timeout=10)
                log(f"evict: asked ollama to unload {name} (embed)")
            except Exception as e:
                log(f"evict: {name} failed ({e!r})")


def _ensure_vram(needed_mib: int):
    """Best-effort make-room before a CUDA model load. Evictions queue behind
    in-flight ollama generations, so re-poll up to ~20s before giving up and
    letting the OOM self-heal be the net."""
    free = _free_vram_mib()
    if free < 0 or free >= needed_mib:
        return
    log(f"need ~{needed_mib}MiB, only {free}MiB free — evicting idle ollama models")
    _evict_idle_ollama()
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        time.sleep(0.5)
        free = _free_vram_mib()
        if free < 0 or free >= needed_mib:
            return
    log(f"still only {free}MiB free after eviction wait — proceeding anyway")


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        compute = "int8" if _device == "cpu" else args.compute
        if _device == "cuda":
            _ensure_vram(NEEDED_MIB.get(args.compute, 3000))
        t0 = time.time()
        log(f"loading {args.model} on {_device} ({compute})")
        _model = WhisperModel(args.model, device=_device, compute_type=compute)
        log(f"loaded in {time.time() - t0:.1f}s")
    return _model


_last_keepalive = 0.0


def _keepalive(force: bool = False):
    """Progress line for the parent's inactivity timer (D4/[26]): one ack on
    request receipt, then one per decoded segment, throttled ≥2s apart. The
    parent's read-loop skips these before any parsing side effects."""
    global _last_keepalive
    now = time.monotonic()
    if not force and now - _last_keepalive < 2.0:
        return
    _last_keepalive = now
    sys.stdout.write(json.dumps({"keepalive": True}) + "\n")
    sys.stdout.flush()


def _test_stall():
    """Gate knob (D4): NEXUS_STT_TEST_STALL_S sleeps in 5s slices with a
    keepalive per slice; NEXUS_STT_TEST_STALL_SILENT=1 suppresses them so the
    parent's inactivity kill can be exercised deterministically."""
    total = float(os.environ.get("NEXUS_STT_TEST_STALL_S", "0") or 0)
    if total <= 0:
        return
    silent = os.environ.get("NEXUS_STT_TEST_STALL_SILENT") == "1"
    t0 = time.monotonic()
    while time.monotonic() - t0 < total:
        time.sleep(min(5.0, max(0.0, total - (time.monotonic() - t0))))
        if not silent:
            _keepalive(force=True)


def _with_gpu_fallback(fn):
    """Run fn inside the cross-process GPU waiting line; on a CUDA failure,
    permanently drop to CPU (for the life of this worker) and rerun. Any OTHER
    failure gets the old in-process pipeline's generic self-heal ([27]): drop
    the model and retry ONCE — transient decode/runtime glitches (an ffmpeg
    hiccup, ctranslate2 state) usually clear on a fresh attempt."""
    global _device, _model, _fallback_used

    def _locked():
        # 45s wait (was 20 in the old in-process path): waiting in the queue
        # beats falling back to CPU. CPU loads skip the lock entirely — the
        # emergency path must not queue behind GPU work.
        with gpu_lock.gpu_section("stt", timeout=45.0,
                                  enabled=_device == "cuda"):
            return fn()

    try:
        return _locked()
    except Exception as e:
        if _device == "cuda" and _is_gpu_failure(e):
            log(f"CUDA failure ({e!r}) — CPU for the rest of this worker's life")
            traceback.print_exc(file=sys.stderr)
            _device = "cpu"
            _model = None
            _fallback_used = True
            gc.collect()  # release the (partially) resident CUDA model
            return fn()
        log(f"STT failure ({e!r}) — dropping model and retrying once")
        traceback.print_exc(file=sys.stderr)
        _model = None
        gc.collect()
        try:
            return _locked()
        except Exception as e2:
            # review K7: the retry can hit a REAL CUDA failure (VRAM taken
            # between attempts) — classify it like a first attempt instead of
            # erroring the request while staying pinned to CUDA.
            if _device == "cuda" and _is_gpu_failure(e2):
                log(f"CUDA failure on the retry ({e2!r}) — CPU for the rest "
                    "of this worker's life")
                traceback.print_exc(file=sys.stderr)
                _device = "cpu"
                _model = None
                _fallback_used = True
                gc.collect()
                return fn()
            raise


def op_warm(req: dict) -> dict:
    t0 = time.time()
    _with_gpu_fallback(_get_model)
    return {"ok": True, "loaded": True, "device": _device, "model": args.model,
            "compute": "int8" if _device == "cpu" else args.compute,
            "elapsed": round(time.time() - t0, 2), "fallback": _fallback_used}


def op_transcribe(req: dict) -> dict:
    # D4/[26]: ack immediately — BEFORE the model load — so the parent's
    # inactivity timer covers the gpu_lock wait + eviction + cold load
    # without a special case.
    _keepalive(force=True)

    def _run():
        global _test_oom_fired
        model = _get_model()
        _test_stall()
        if (os.environ.get("NEXUS_STT_TEST_OOM") == "1"
                and _device == "cuda" and not _test_oom_fired):
            _test_oom_fired = True
            raise RuntimeError("CUDA out of memory (injected test failure)")
        lang = req.get("language")
        if args.model.endswith(".en"):
            lang = "en"  # english-only checkpoints reject other language hints
        segments, _info = model.transcribe(
            req["path"],
            language=lang or None,  # empty/None = autodetect
            beam_size=int(req.get("beam_size", 3)),
            vad_filter=bool(req.get("vad_filter", True)),
            initial_prompt=req.get("initial_prompt") or None,
            # False = WisprFlow's proven setting: short utterances must not
            # condition on earlier text (hallucination-loop guard)
            condition_on_previous_text=bool(
                req.get("condition_on_previous_text", False)),
        )
        # D4/[26]: consume the segment generator in a loop — long decodes
        # (dictation segments run up to dictation.max_seconds=300s of audio)
        # emit progress per decoded segment instead of one silent block.
        parts = []
        for s in segments:
            parts.append(s.text.strip())
            _keepalive()  # ≥2s throttle inside
        return " ".join(parts).strip()

    t0 = time.time()
    text = _with_gpu_fallback(_run)
    elapsed = round(time.time() - t0, 2)
    log(f"ASR [{_device}] {elapsed}s -> {text[:80]!r}")
    return {"text": text, "device": _device, "elapsed": elapsed,
            "fallback": _fallback_used}


OPS = {
    "ping": lambda req: {"ok": True, "loaded": _model is not None,
                         "device": _device},
    "warm": op_warm,
    "transcribe": op_transcribe,
}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = OPS[req["op"]](req)
        except Exception as e:
            resp = {"error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc()[-1500:]}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
