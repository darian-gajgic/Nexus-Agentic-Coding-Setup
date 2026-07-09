"""NEXUS Agent OS — cross-process GPU arbiter (audit §3.6).

The 12GB card is shared by faster-whisper STT (nexus server process), SigLIP +
SDXL (ml-env vision worker process) and the ollama VLM (ollama server, driven
by our HTTP calls). Uncoordinated, their multi-GB working sets collide and OOM
each other. This module serializes the heavy GPU sections with an fcntl flock
on a lockfile — it works across unrelated processes and the kernel releases it
on process death, so a crashed holder can never wedge the others.

On acquire timeout the section runs UNSERIALIZED (logged): a slow holder must
degrade the pipeline, never deadlock it — the per-model OOM fallbacks (STT →
CPU, SigLIP → CPU) remain the safety net.

The sync form BLOCKS — call it from a worker thread (asyncio.to_thread), never
on the event loop. Async callers use gpu_section_async, which shifts the
blocking acquire/release into threads.
"""
import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager, contextmanager

LOCK_PATH = os.environ.get("NEXUS_GPU_LOCK",
                           f"/tmp/nexus-gpu-{os.getuid()}.lock")
_POLL = 0.2  # seconds between non-blocking acquire attempts


def _acquire(name: str, timeout: float):
    """Open + flock the lockfile. Returns (fd, got_lock). Never raises —
    an unusable lockfile means 'run unserialized', not 'break the caller'."""
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return None, False
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, True
        except OSError:
            if time.monotonic() >= deadline:
                print(f"[gpu-lock] {name}: not free after {timeout:.0f}s — "
                      f"running unserialized", flush=True)
                return fd, False
            time.sleep(_POLL)


def _release(fd, got: bool):
    if fd is None:
        return
    try:
        if got:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


@contextmanager
def gpu_section(name: str, timeout: float = 60.0, enabled: bool = True):
    """Serialize a heavy GPU section across processes. enabled=False (the CPU
    path) is a no-op so a CPU fallback never queues behind GPU work."""
    if not enabled:
        yield
        return
    fd, got = _acquire(name, timeout)
    try:
        yield
    finally:
        _release(fd, got)


@asynccontextmanager
async def gpu_section_async(name: str, timeout: float = 60.0,
                            enabled: bool = True):
    """gpu_section for async callers — acquire/release run in worker threads
    so the event loop never blocks on the flock."""
    if not enabled:
        yield
        return
    fd, got = await asyncio.to_thread(_acquire, name, timeout)
    try:
        yield
    finally:
        await asyncio.to_thread(_release, fd, got)
