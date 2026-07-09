"""NEXUS vision worker — runs in ~/ml-env (torch + transformers + diffusers).

Long-lived subprocess owned by vision.py. JSON-lines protocol on stdin/stdout:
one request object per line in, one response object per line out, same order.

Ops:
  {"op":"ping"}                                    -> {"ok":true}
  {"op":"embed_image","path":P,"ocr":true}         -> {"vec":[...],"ocr":"text"}
  {"op":"embed_text","text":T}                     -> {"vec":[...]}
  {"op":"generate","prompt":P,"out":PATH,
   "steps":2,"size":768}                           -> {"ok":true,"out":PATH}

Models are lazy singletons. SigLIP stays on GPU (~1GB fp16); SDXL-Turbo runs
with sequential CPU offload so VRAM stays ~3-4GB during the steps only (this
box is the 12GB laptop 5070 Ti). The PARENT enforces idle lifetime by killing
the whole process — GPU memory is freed by process exit, same discipline as
the old Wav2Lip subprocess.

Errors never kill the loop: each request gets {"error": "..."} and the worker
keeps serving.
"""
import gc
import json
import sys
import traceback

import torch
from PIL import Image

import gpu_lock  # sys.path[0] is this script's dir — the app tree

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SIGLIP_ID = "google/siglip-so400m-patch14-384"
SDXL_ID = "stabilityai/sdxl-turbo"

_siglip = None       # (model, processor)
_siglip_device = DEVICE  # flips to "cpu" after a CUDA OOM (this box's 12GB card
                         # is shared with ollama + the user's dictation tool, so
                         # SigLIP must still embed when the GPU is full)
_ocr = None          # RapidOCR engine
_sdxl = None         # diffusers pipeline (cpu-offloaded)


def _siglip_dtype():
    # float16 is a GPU win but slow/patchy on CPU — use float32 there
    return torch.float16 if _siglip_device == "cuda" else torch.float32


def _get_siglip():
    global _siglip
    if _siglip is None:
        from transformers import AutoModel, AutoProcessor
        model = AutoModel.from_pretrained(
            SIGLIP_ID, torch_dtype=_siglip_dtype()).to(_siglip_device).eval()
        processor = AutoProcessor.from_pretrained(SIGLIP_ID)
        _siglip = (model, processor)
    return _siglip


def _drop_siglip():
    global _siglip
    _siglip = None
    gc.collect()
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass


def _is_oom(e: Exception) -> bool:
    """Any CUDA-side failure that means 'the GPU can't serve this right now' —
    classic OOM, cudaErrorInvalidDevice (contended/lost device), cuBLAS/cuDNN
    errors, generic CUDA alloc failures. All warrant the CPU fallback."""
    if isinstance(e, getattr(torch.cuda, "OutOfMemoryError", ())):
        return True
    s = str(e).lower()
    return any(sig in s for sig in (
        "out of memory", "cudaerrorinvaliddevice", "invalid device",
        "cublas", "cudnn", "cuda error", "cuda failed",
        "failed to allocate", "unable to allocate"))


def _siglip_op_with_fallback(fn, req):
    """Run a SigLIP op; on a CUDA OOM, permanently drop to CPU (for the life of
    this worker — a respawn after idle retries CUDA) and rerun. Mirrors the STT
    self-heal so a contended GPU degrades 'seeing' instead of breaking it."""
    global _siglip_device
    try:
        # serialize the GPU section (load + forward) with STT/SDXL/VLM on the
        # shared card; the CPU path skips the lock (must not queue behind GPU)
        with gpu_lock.gpu_section("siglip", timeout=30.0,
                                  enabled=_siglip_device == "cuda"):
            return fn(req)
    except Exception as e:
        if _siglip_device == "cuda" and _is_oom(e):
            _siglip_device = "cpu"
            _drop_siglip()  # free the (partially) resident CUDA model, reload on CPU
            return fn(req)
        raise


def _get_ocr():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def _get_sdxl():
    global _sdxl
    if _sdxl is None:
        from diffusers import AutoPipelineForText2Image
        pipe = AutoPipelineForText2Image.from_pretrained(
            SDXL_ID, torch_dtype=torch.float16, variant="fp16")
        # SEQUENTIAL offload: weights live in RAM and stream through VRAM
        # layer-by-layer (~2GB peak). Slower than model offload, but this is a
        # 12GB card that also hosts whisper + the ollama VLM — never assume
        # free VRAM. empty_cache first so SigLIP fragments don't add up.
        torch.cuda.empty_cache()
        pipe.enable_sequential_cpu_offload()
        _sdxl = pipe
    return _sdxl


def _embed_image(req):
    # transformers 5.x: get_*_features returns token-level states for SigLIP —
    # the pooled embedding lives on the tower's pooler_output (verified: 1152-d)
    model, processor = _get_siglip()
    img = Image.open(req["path"]).convert("RGB")
    inputs = processor(images=img, return_tensors="pt").to(_siglip_device)
    pv = inputs["pixel_values"].to(_siglip_dtype())
    with torch.no_grad():
        feat = model.vision_model(pixel_values=pv).pooler_output
    return torch.nn.functional.normalize(feat[0].float(), dim=-1).cpu().tolist()


def op_embed_image(req):
    vec = _siglip_op_with_fallback(_embed_image, req)
    out = {"vec": vec, "device": _siglip_device}
    if req.get("ocr"):
        try:
            result, _ = _get_ocr()(req["path"])
            out["ocr"] = " ".join(r[1] for r in (result or []) if len(r) > 1)[:4000]
        except Exception:
            out["ocr"] = ""
    return out


def _embed_text(req):
    model, processor = _get_siglip()
    inputs = processor(text=[req["text"]], return_tensors="pt",
                       padding="max_length", truncation=True).to(_siglip_device)
    with torch.no_grad():
        feat = model.text_model(**inputs).pooler_output
    return torch.nn.functional.normalize(feat[0].float(), dim=-1).cpu().tolist()


def op_embed_text(req):
    return {"vec": _siglip_op_with_fallback(_embed_text, req), "device": _siglip_device}


def op_generate(req):
    size = int(req.get("size", 768))
    steps = int(req.get("steps", 2))
    # SDXL's offloaded layers stream through VRAM for the whole run — hold the
    # cross-process lock so STT/SigLIP/VLM bursts don't collide with it
    with gpu_lock.gpu_section("sdxl", timeout=120.0, enabled=DEVICE == "cuda"):
        pipe = _get_sdxl()
        img = pipe(prompt=req["prompt"][:800], num_inference_steps=steps,
                   guidance_scale=0.0, width=size, height=size).images[0]
        img.save(req["out"])
        torch.cuda.empty_cache()
    return {"ok": True, "out": req["out"]}


OPS = {
    "ping": lambda req: {"ok": True, "device": _siglip_device},
    "embed_image": op_embed_image,
    "embed_text": op_embed_text,
    "generate": op_generate,
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
