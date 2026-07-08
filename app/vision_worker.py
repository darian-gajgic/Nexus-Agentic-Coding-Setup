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
import json
import sys
import traceback

import torch
from PIL import Image

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SIGLIP_ID = "google/siglip-so400m-patch14-384"
SDXL_ID = "stabilityai/sdxl-turbo"

_siglip = None       # (model, processor)
_ocr = None          # RapidOCR engine
_sdxl = None         # diffusers pipeline (cpu-offloaded)


def _get_siglip():
    global _siglip
    if _siglip is None:
        from transformers import AutoModel, AutoProcessor
        model = AutoModel.from_pretrained(SIGLIP_ID, torch_dtype=torch.float16).to(DEVICE).eval()
        processor = AutoProcessor.from_pretrained(SIGLIP_ID)
        _siglip = (model, processor)
    return _siglip


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


def op_embed_image(req):
    # transformers 5.x: get_*_features returns token-level states for SigLIP —
    # the pooled embedding lives on the tower's pooler_output (verified: 1152-d)
    model, processor = _get_siglip()
    img = Image.open(req["path"]).convert("RGB")
    inputs = processor(images=img, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        feat = model.vision_model(pixel_values=inputs["pixel_values"].half()).pooler_output
    vec = torch.nn.functional.normalize(feat[0].float(), dim=-1).cpu().tolist()
    out = {"vec": vec}
    if req.get("ocr"):
        try:
            result, _ = _get_ocr()(req["path"])
            out["ocr"] = " ".join(r[1] for r in (result or []) if len(r) > 1)[:4000]
        except Exception:
            out["ocr"] = ""
    return out


def op_embed_text(req):
    model, processor = _get_siglip()
    inputs = processor(text=[req["text"]], return_tensors="pt",
                       padding="max_length", truncation=True).to(DEVICE)
    with torch.no_grad():
        feat = model.text_model(**inputs).pooler_output
    return {"vec": torch.nn.functional.normalize(feat[0].float(), dim=-1).cpu().tolist()}


def op_generate(req):
    pipe = _get_sdxl()
    size = int(req.get("size", 768))
    steps = int(req.get("steps", 2))
    img = pipe(prompt=req["prompt"][:800], num_inference_steps=steps,
               guidance_scale=0.0, width=size, height=size).images[0]
    img.save(req["out"])
    torch.cuda.empty_cache()
    return {"ok": True, "out": req["out"]}


OPS = {
    "ping": lambda req: {"ok": True, "device": DEVICE},
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
