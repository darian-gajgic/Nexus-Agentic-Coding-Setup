# CUDA Mixed-Version Coexistence: onnxruntime-gpu (CUDA 13) + ctranslate2 (CUDA 12)

On systems with NVIDIA Blackwell GPUs (RTX 50-series, sm_120), the driver ships
CUDA 13.x. But some libraries are compiled against specific CUDA major versions:

- `onnxruntime-gpu` 1.27+ → needs `libcudart.so.13`, `libcublas.so.13`
- `ctranslate2` 4.8.0 → needs `libcublas.so.12` (dlopen'd at runtime, NOT linked)

Running both in the same Python process requires making both CUDA versions
discoverable simultaneously.

## The Problem

1. **onnxruntime-gpu** imports fine once its .so can find `libcudart.so.13`
2. **ctranslate2** calls `dlopen("libcublas.so.12")` at runtime (when a CUDA
   operation is first executed), NOT at import time — so import succeeds but
   `model.transcribe()` fails with:
   ```
   RuntimeError: Library libcublas.so.12 is not found or cannot be loaded
   ```
3. Python 3.14 has **no prebuilt wheels** for `nvidia-cuda-runtime-cu13` or
   `nvidia-cublas-cu13` — they fail to compile from source.
4. `LD_LIBRARY_PATH` set in `sitecustomize.py` does NOT work — the dynamic
   linker reads it at process start, before Python runs.

## The Solution (3 techniques combined)

### Technique 1: patchelf — set rpath on onnxruntime .so files

This makes onnxruntime find CUDA 13 libs without any environment variable:

```bash
ORT_SO=".venv/lib/python3.14/site-packages/onnxruntime/capi/onnxruntime_pybind11_state.cpython-314-x86_64-linux-gnu.so"
CUDA13="/home/user/ml-env/lib/python3.14/site-packages/nvidia/cu13/lib"
CUDNN="/home/user/ml-env/lib/python3.14/site-packages/nvidia/cudnn/lib"

patchelf --set-rpath "$CUDA13:$CUDNN:\$ORIGIN" "$ORT_SO"
# Also patch the CUDA provider .so:
patchelf --set-rpath "$CUDA13:$CUDNN:\$ORIGIN" \
  ".venv/lib/python3.14/site-packages/onnxruntime/capi/libonnxruntime_providers_cuda.so"
```

Use **absolute paths** in rpath (not `$ORIGIN/../../../lib`) — the relative
traversal is fragile across package layouts.

### Technique 2: ctypes RTLD_GLOBAL preload — for ctranslate2's dlopen

ctranslate2 uses `dlopen("libcublas.so.12")` which searches the standard
dynamic linker path. Since we can't use LD_LIBRARY_PATH (see problem #4 above),
preload the library into the global symbol table before ctranslate2 runs:

```python
# sitecustomize.py — runs at Python startup, BEFORE any imports
import ctypes
# CUDA 12 libs (for ctranslate2/faster-whisper)
for lib in [
    "/usr/local/lib/ollama/cuda_v12/libcublas.so.12",
    "/usr/local/lib/ollama/cuda_v12/libcublasLt.so.12",
    "/usr/local/lib/ollama/cuda_v12/libcudart.so.12",
]:
    try:
        ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        pass
# CUDA 13 libs (for onnxruntime-gpu) — belt and suspenders with patchelf
import glob, os
for lib_dir in [
    "/path/to/nvidia/cu13/lib",
    "/path/to/nvidia/cudnn/lib",
]:
    if os.path.isdir(lib_dir):
        for so in sorted(glob.glob(f"{lib_dir}/*.so*")):
            try: ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
            except OSError: pass
```

**Why sitecustomize.py?** It runs before any user import. The `RTLD_GLOBAL`
flag makes the loaded symbols available to all subsequent `dlopen()` calls in
the process — including ctranslate2's runtime library loading.

### Technique 3: Finding existing CUDA libraries on the system

Before installing anything, search for existing CUDA libraries. They're often
bundled with other tools:

```bash
# Common locations:
find / -name 'libcudart.so*' 2>/dev/null
# /usr/local/lib/ollama/cuda_v12/   ← Ollama bundles CUDA 12
# /usr/local/lib/ollama/cuda_v13/   ← Ollama bundles CUDA 13
# ~/.cache/uv/archive-*/nvidia/cu13/ ← uv package cache
# ml-env venv site-packages/nvidia/ ← another Python env
```

Ollama is a particularly good source — it bundles both CUDA 12 and 13 runtime
libraries in `/usr/local/lib/ollama/cuda_v{12,13}/`.

## Verifying

```bash
# onnxruntime sees CUDA:
python3 -c "import onnxruntime; print('CUDA EP:', 'CUDAExecutionProvider' in onnxruntime.get_available_providers())"

# ctranslate2 can load cublas:
python3 -c "
import ctypes
ctypes.CDLL('/usr/local/lib/ollama/cuda_v12/libcublas.so.12', mode=ctypes.RTLD_GLOBAL)
from faster_whisper import WhisperModel
m = WhisperModel('medium.en', device='cuda', compute_type='float16')
print('STT loaded on GPU')
"
```

## Pitfalls

- **Do NOT install `nvidia-cuda-runtime-cu13` via pip on Python 3.14** — the
  wheels don't exist and building from source fails. Use existing system libs.
- **Do NOT rely on `LD_LIBRARY_PATH` in `sitecustomize.py`** — the dynamic
  linker has already initialized by the time Python code runs. Use `ctypes.CDLL`
  with `RTLD_GLOBAL` instead.
- **patchelf rpath must be absolute** — `$ORIGIN/../../..` is fragile across
  different package layouts and venv structures.
- **Both CUDA versions can coexist in the same process** — CUDA 12 and 13
  runtimes are designed to be side-by-side compatible as long as each library
  finds its own version.
