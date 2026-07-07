"""lipsync.py — Wav2Lip neural lip-sync renderer.

Loads the Wav2Lip model lazily (singleton) and renders a lip-synced video from a
reference face image + an audio file. Inference runs in /home/sinep/ml-env (the env
with working CUDA 13 / Blackwell support) via subprocess, so the nexus server's own
venv stays clean.

Public API:
    async def render(audio_path: str) -> Path   # returns mp4 path
    def status() -> dict                          # readiness for the API
"""
import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

PROJECT = Path(__file__).parent
REFERENCE_FACE = PROJECT / "static" / "avatar" / "reference.jpg"
WAV2LIP_DIR = Path("/home/sinep/Wav2Lip")
WAV2LIP_CHECKPOINT = WAV2LIP_DIR / "checkpoints" / "wav2lip_gan.pth"
ML_PY = "/home/sinep/ml-env/bin/python"  # the env with torch+CUDA working
INFERENCE_SCRIPT = WAV2LIP_DIR / "inference.py"

_lock = asyncio.Lock()  # serialize GPU inference (one render at a time)
_ready: bool | None = None


def status() -> dict:
    """Report whether the lip-sync pipeline is available."""
    global _ready
    if _ready is None:
        _ready = (
            REFERENCE_FACE.is_file()
            and WAV2LIP_CHECKPOINT.is_file()
            and INFERENCE_SCRIPT.is_file()
            and os.access(ML_PY, os.X_OK)
        )
    return {
        "available": bool(_ready),
        "reference_face": str(REFERENCE_FACE) if REFERENCE_FACE.is_file() else None,
        "checkpoint": str(WAV2LIP_CHECKPOINT) if WAV2LIP_CHECKPOINT.is_file() else None,
        "ml_env": ML_PY if os.access(ML_PY, os.X_OK) else None,
    }


async def render(audio_path: str) -> Path:
    """Render a lip-synced MP4 from the reference face + the given audio file.

    Args:
        audio_path: path to a WAV file (16kHz mono recommended).
    Returns:
        Path to the output MP4.
    Raises:
        RuntimeError: if Wav2Lip fails or prerequisites are missing.
    """
    if not status()["available"]:
        raise RuntimeError("lip-sync pipeline not available (see /api/jarvis/lipsync/status)")

    fd, out_name = tempfile.mkstemp(suffix=".mp4", prefix="lipsync_")
    os.close(fd)  # mkstemp's fd leaked once per spoken sentence — close it
    out = Path(out_name)
    cmd = [
        ML_PY, str(INFERENCE_SCRIPT),
        "--checkpoint_path", str(WAV2LIP_CHECKPOINT),
        "--face", str(REFERENCE_FACE),
        "--audio", str(audio_path),
        "--outfile", str(out),
    ]
    try:
        async with _lock:  # one GPU inference at a time
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(WAV2LIP_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                # a wedged render must never hold the lock forever — that
                # freezes every subsequent /talk in the conversation
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise RuntimeError("Wav2Lip inference timed out after 120s (killed)")
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            tail = (stdout or b"").decode(errors="replace")[-1500:]
            raise RuntimeError(f"Wav2Lip inference failed (rc={proc.returncode}):\n{tail}")
        return out
    except Exception:
        out.unlink(missing_ok=True)  # no partial mp4 left behind on failure
        raise


# Convenience: render from raw wav bytes (used by the endpoint)
async def render_bytes(wav_bytes: bytes) -> bytes:
    """Render lip-sync from raw WAV bytes; return MP4 bytes."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as af:
        af.write(wav_bytes)
        audio_path = af.name
    mp4_path = None
    try:
        mp4_path = await render(audio_path)
        return mp4_path.read_bytes()
    finally:
        os.unlink(audio_path)
        if mp4_path is not None:
            mp4_path.unlink(missing_ok=True)  # was leaked on every sentence
