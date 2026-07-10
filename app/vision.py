"""NEXUS Agent OS — JARVIS visual memory + image understanding/creation.

Three capabilities, all local (the Z.AI coding-plan key covers no vision or
image models — verified 2026-07-08, error 1113):

1. VISUAL MEMORY — webcam/screen frames the browser posts are embedded with
   SigLIP (so400m-384, 1152-dim) + OCR'd (RapidOCR), stored in the same local
   qdrant that holds mem0, collection `jarvis_vision`. Natural-language recall
   ("when did I show you the red box?") = SigLIP text embedding → vector
   search, with an OCR keyword boost (hybrid, Recall/Screenpipe style).
2. UNDERSTANDING — a frame or uploaded image is described by a local ollama
   VLM (qwen3-vl:8b, already pulled) so JARVIS can answer about what it sees.
3. CREATION — SDXL-Turbo (fp16, cpu-offloaded: ~3-4GB VRAM during steps only)
   renders images into the JARVIS session file exchange.

SigLIP + OCR + SDXL run in ONE persistent ml-env subprocess (vision_worker.py,
JSON-lines protocol). The worker is spawned on demand and KILLED after
VISION_IDLE_TIMEOUT of no use — process exit is the VRAM guarantee, the same
discipline as the retired Wav2Lip subprocess. GPU here is the 12GB laptop
5070 Ti: never keep vision models resident alongside whisper + ollama.
"""
import asyncio
import base64
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx

import gpu_lock

PROJECT = Path(__file__).parent
FRAMES_ROOT = PROJECT / "workspaces" / "jarvis"
ML_PY = os.path.expanduser("~/ml-env/bin/python")
WORKER = PROJECT / "vision_worker.py"

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
COLLECTION = "jarvis_vision"
DIM = 1152
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
VLM_MODEL = os.environ.get("JARVIS_VLM_MODEL", "qwen3-vl:8b")

VISION_IDLE_TIMEOUT = 600.0     # default worker idle-kill; setting vision.idle_timeout overrides
DUP_COSINE = 0.985              # frames this similar to the previous one are skipped
FRAME_KEEP = 4000               # per-user cap; oldest frames beyond it are pruned


def _conf(key: str, default: str) -> str:
    """Settings-registry lookup that degrades to the default if unavailable."""
    try:
        import settings_registry as sreg
        v = sreg.conf(key)
        return v if v not in (None, "") else default
    except Exception:
        return default


def _vlm_keep_alive() -> str:
    """How long ollama holds the VLM after a describe. Short by default so the
    6-8GB model frees VRAM for other models once JARVIS is done looking; long
    enough that back-to-back describes within one turn reuse the warm model."""
    return _conf("vision.vlm_keep_alive", "60s")

_worker: subprocess.Popen | None = None
_worker_lock = asyncio.Lock()
_last_use = 0.0
_last_vec: dict[str, list] = {}   # f"{user}:{kind}" -> last indexed vector (dedup)
_qdrant_ready = False


# ── worker lifecycle ────────────────────────────────────────────────────────

def _spawn_worker() -> subprocess.Popen:
    return subprocess.Popen(
        [ML_PY, str(WORKER)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, cwd=str(PROJECT), text=True, bufsize=1,
    )


def _worker_alive() -> bool:
    return _worker is not None and _worker.poll() is None


def _ask_worker_sync(req: dict, timeout: float = 180.0) -> dict:
    """One request/response on the worker pipe. Caller holds _worker_lock."""
    global _worker, _last_use
    if not _worker_alive():
        _worker = _spawn_worker()
    _last_use = time.time()
    _worker.stdin.write(json.dumps(req) + "\n")
    _worker.stdin.flush()
    line = _worker.stdout.readline()
    _last_use = time.time()
    if not line:
        raise RuntimeError("vision worker died mid-request")
    resp = json.loads(line)
    if resp.get("error"):
        raise RuntimeError(resp["error"])
    return resp


def _kill_and_respawn_worker(reason: str):
    """After a request timeout the abandoned reader thread is still blocked on
    stdout.readline() and the JSON-lines protocol is desynced (the late reply
    would answer the NEXT request). Kill the worker — pipe EOF unblocks the
    reader — and respawn fresh so the next request starts on a clean pipe."""
    global _worker
    w, _worker = _worker, None
    if w is not None:
        try:
            w.kill()
            w.wait(timeout=5)
        except Exception:
            pass
    print(f"[vision] worker killed + respawned: {reason}", flush=True)
    _worker = _spawn_worker()


async def _ask_worker(req: dict, timeout: float = 180.0) -> dict:
    async with _worker_lock:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_ask_worker_sync, req, timeout), timeout)
        except TimeoutError:
            await asyncio.to_thread(
                _kill_and_respawn_worker,
                f"{req.get('op')} timed out after {timeout:.0f}s")
            raise


def _idle_timeout() -> float:
    try:
        return float(_conf("vision.idle_timeout", str(VISION_IDLE_TIMEOUT)))
    except (TypeError, ValueError):
        return VISION_IDLE_TIMEOUT


def check_and_unload_idle():
    """Called from the server's periodic unloader (same cadence as voice)."""
    global _worker
    if _worker_alive() and _last_use and (time.time() - _last_use) > _idle_timeout():
        try:
            _worker.kill()
        except Exception:
            pass
        _worker = None
        return True
    return False


def vision_status() -> dict:
    return {
        "worker_alive": _worker_alive(),
        "vlm_model": VLM_MODEL,
        "last_use": int(_last_use),
        "idle_timeout": VISION_IDLE_TIMEOUT,
    }


# ── qdrant ──────────────────────────────────────────────────────────────────

def _qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=QDRANT_URL, timeout=20)


def _ensure_collection():
    global _qdrant_ready
    if _qdrant_ready:
        return
    from qdrant_client.models import Distance, VectorParams
    c = _qdrant()
    if not c.collection_exists(COLLECTION):
        c.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=DIM, distance=Distance.COSINE))
    _qdrant_ready = True


def _cos(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))  # both normalized


# ── frames: ingest + search ─────────────────────────────────────────────────

def _frames_dir(user_id: str) -> Path:
    d = FRAMES_ROOT / user_id / "frames"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pin_looked_frame(user_id: str, jpeg: bytes) -> Path:
    """Pin the exact frame JARVIS just described to a stable per-user path.

    describe_image sees the turn's raw bytes, but ingest_frame is
    fire-and-forget AND dedups — the described frame may never land on disk
    under a timestamp name, and by edit time max(mtime) points at a LATER
    capture. The edit skill prefers this pin so "edit what you just saw"
    operates on the described frame, not the newest one.
    """
    path = _frames_dir(user_id) / ".last-looked.jpg"
    tmp = path.with_name(".last-looked.jpg.tmp")
    tmp.write_bytes(jpeg)
    os.replace(tmp, path)   # atomic — a reader never sees a half-written pin
    return path


async def ingest_frame(user_id: str, jpeg: bytes, kind: str, note: str = "") -> dict:
    """Store + index one webcam/screen/upload frame for this user.
    Near-duplicates of the PREVIOUS indexed frame (per user+kind) are skipped —
    a static scene at 1 frame per few seconds must not flood the collection."""
    from PIL import Image
    import io as _io
    img = Image.open(_io.BytesIO(jpeg)).convert("RGB")
    img.thumbnail((768, 768))
    ts = time.time()
    name = f"{int(ts * 1000)}-{kind}.jpg"
    path = _frames_dir(user_id) / name
    img.save(path, "JPEG", quality=82)

    r = await _ask_worker({"op": "embed_image", "path": str(path), "ocr": True})
    vec, ocr = r["vec"], r.get("ocr", "")

    key = f"{user_id}:{kind}"
    prev = _last_vec.get(key)
    if prev is not None and _cos(prev, vec) > DUP_COSINE:
        path.unlink(missing_ok=True)   # same scene — keep the earlier frame
        return {"indexed": False, "dup": True}
    _last_vec[key] = vec

    from qdrant_client.models import PointStruct
    _ensure_collection()
    pid = str(uuid.uuid4())
    await asyncio.to_thread(
        _qdrant().upsert, COLLECTION,
        [PointStruct(id=pid, vector=vec, payload={
            "user": user_id, "kind": kind, "ts": ts, "file": name,
            "ocr": ocr, "note": note[:400],
        })])
    asyncio.get_running_loop().run_in_executor(None, _prune_old, user_id)
    return {"indexed": True, "id": pid, "ocr_chars": len(ocr)}


def _prune_old(user_id: str):
    """Keep the newest FRAME_KEEP frames per user (points + jpgs)."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        c = _qdrant()
        flt = Filter(must=[FieldCondition(key="user", match=MatchValue(value=user_id))])
        n = c.count(COLLECTION, count_filter=flt).count
        if n <= FRAME_KEEP:
            return
        pts, _ = c.scroll(COLLECTION, scroll_filter=flt, limit=n,
                          with_payload=["ts", "file"], with_vectors=False)
        pts.sort(key=lambda p: p.payload.get("ts", 0))
        doomed = pts[: n - FRAME_KEEP]
        c.delete(COLLECTION, points_selector=[p.id for p in doomed])
        for p in doomed:
            (FRAMES_ROOT / user_id / "frames" / p.payload.get("file", "")).unlink(missing_ok=True)
    except Exception:
        pass


async def search_frames(user_id: str, query: str, limit: int = 12) -> list[dict]:
    """Hybrid recall: SigLIP text→image similarity + OCR keyword boost."""
    _ensure_collection()
    r = await _ask_worker({"op": "embed_text", "text": query})
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    flt = Filter(must=[FieldCondition(key="user", match=MatchValue(value=user_id))])
    hits = (await asyncio.to_thread(
        lambda: _qdrant().query_points(
            COLLECTION, query=r["vec"], query_filter=flt,
            limit=max(limit * 3, 30), with_payload=True))).points
    terms = [t for t in query.lower().split() if len(t) > 2]
    out = []
    for h in hits:
        p = h.payload or {}
        ocr = (p.get("ocr") or "").lower()
        boost = 0.12 * sum(1 for t in terms if t in ocr) if ocr else 0.0
        out.append({
            "id": str(h.id), "score": round(h.score + min(boost, 0.3), 4),
            "sim": round(h.score, 4), "kind": p.get("kind"), "ts": p.get("ts"),
            "file": p.get("file"), "ocr": (p.get("ocr") or "")[:300],
            "note": p.get("note") or "",
        })
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


async def vision_counts(user_id: str) -> dict:
    _ensure_collection()
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    flt = Filter(must=[FieldCondition(key="user", match=MatchValue(value=user_id))])
    n = await asyncio.to_thread(lambda: _qdrant().count(COLLECTION, count_filter=flt).count)
    return {"frames": n}


async def forget_all(user_id: str) -> int:
    _ensure_collection()
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    c = _qdrant()
    flt = Filter(must=[FieldCondition(key="user", match=MatchValue(value=user_id))])
    n = c.count(COLLECTION, count_filter=flt).count
    await asyncio.to_thread(c.delete, COLLECTION, points_selector=flt)
    import shutil
    shutil.rmtree(FRAMES_ROOT / user_id / "frames", ignore_errors=True)
    _last_vec.pop(f"{user_id}:webcam", None)
    _last_vec.pop(f"{user_id}:screen", None)
    return n


# ── understanding: local VLM via ollama ─────────────────────────────────────

async def warm_vlm() -> None:
    """Preload the VLM into ollama (fired when an image lands in the file
    exchange) so a following 'analyze this' doesn't pay the cold start. Uses the
    same short keep_alive as describe — so a dropped-but-never-asked image can't
    camp 6-8GB of VRAM."""
    try:
        # opportunistic prewarm: hold the cross-process GPU lock while ollama
        # loads the 6-8GB model so it doesn't collide with STT/SigLIP/SDXL
        async with gpu_lock.gpu_section_async("vlm-warm", timeout=10.0):
            async with httpx.AsyncClient(timeout=240) as client:
                await client.post(f"{OLLAMA_URL}/api/generate",
                                  json={"model": VLM_MODEL, "keep_alive": _vlm_keep_alive()})
    except Exception:
        pass


async def unload_vlm() -> None:
    """Evict the VLM from VRAM NOW (keep_alive:0). Called when JARVIS finishes a
    turn that used its eyes — the local model shouldn't hold the card once the
    task is done and the (cloud) chat model has taken over. no-op if not loaded."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{OLLAMA_URL}/api/generate",
                              json={"model": VLM_MODEL, "keep_alive": 0})
    except Exception:
        pass


async def describe_image(jpeg: bytes, prompt: str = "") -> str:
    """Ask the local VLM what's in the image. Used for 'look at this' turns."""
    q = prompt.strip() or (
        "Describe what you see, concisely but completely: objects, people, "
        "text (transcribe it), UI elements, anything notable.")
    # 12GB card shared with the user's dictation tool (~3.3GB resident): the
    # VLM often runs partially CPU-offloaded, so keep the generation short
    # and allow the slow path to finish instead of ReadTimeout-ing at 120s.
    # keep_alive is short so the model frees VRAM soon after the turn; the chat
    # endpoint also evicts it explicitly once the turn ends (unload_vlm).
    # The load + generation is the heaviest burst on the shared card — hold the
    # cross-process GPU lock so STT/SigLIP/SDXL don't OOM into it.
    async with gpu_lock.gpu_section_async("vlm-describe", timeout=60.0):
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json={
                "model": VLM_MODEL, "stream": False,
                "keep_alive": _vlm_keep_alive(),
                "messages": [{"role": "user", "content": q,
                              "images": [base64.b64encode(jpeg).decode()]}],
                "options": {"num_predict": 256},
            })
            r.raise_for_status()
            return (r.json().get("message") or {}).get("content", "").strip()


# ── creation: SDXL-Turbo via the worker ─────────────────────────────────────

async def generate_image(prompt: str, out_path: Path, size: int = 768) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 12GB card: evict the ollama VLM first (it idles at ~6GB for 5 min after
    # a describe call) so SDXL's working set fits. keep_alive=0 = unload now.
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{OLLAMA_URL}/api/generate",
                              json={"model": VLM_MODEL, "keep_alive": 0})
    except Exception:
        pass
    await _ask_worker({"op": "generate", "prompt": prompt,
                       "out": str(out_path), "steps": 3, "size": size},
                      timeout=300)
    return out_path
