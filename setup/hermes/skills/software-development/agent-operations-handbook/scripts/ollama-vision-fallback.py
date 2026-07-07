#!/usr/bin/env python3
"""Fallback vision analysis when the built-in `vision_analyze` tool fails.

Two failure modes this bypasses (see SKILL.md Section 2):
  1. Context overflow — large image (e.g. a 3392x2544 PNG) produces
     exceed_context_size_error because the local vision model's num_ctx
     (often 4096) is too small for the image tokens + prompt.
  2. Tool mis-route — `vision_analyze` falls through to the text-only main
     provider and returns HTTP 400 code 1210 "messages.content.type is
     invalid, allowed values: ['text']" (the text provider rejects image input).

The fix for both: downscale the image with PIL to fit the context, then call
the local Ollama vision model directly at its /api/generate endpoint with the
image as base64. This bypasses the tool's routing entirely and runs fully
in-session (no config change / session restart needed, unlike raising num_ctx).

Usage:
    python3 ollama-vision-fallback.py <image_path> ["your question"]

Defaults: model qwen3-vl:8b, endpoint http://localhost:11434, max edge 512px,
JPEG q85. Override MODEL / HOST / PORT / MAX_EDGE env vars as needed.
"""
import base64
import json
import os
import sys
import urllib.request

MODEL = os.environ.get("MODEL", "qwen3-vl:8b")
HOST = os.environ.get("HOST", "localhost")
PORT = os.environ.get("PORT", "11434")
MAX_EDGE = int(os.environ.get("MAX_EDGE", "512"))

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip install Pillow")


def downscale(src_path: str) -> bytes:
    img = Image.open(src_path)
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = "/tmp/_vision_fallback.jpg"
    img.save(out, "JPEG", quality=85)
    with open(out, "rb") as f:
        return f.read()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: ollama-vision-fallback.py <image> [question]")
    img_path = sys.argv[1]
    question = (
        sys.argv[2]
        if len(sys.argv) > 2
        else "Describe this image in detail: subject, setting, colors, style, framing."
    )

    jpg_bytes = downscale(img_path)
    b64 = base64.b64encode(jpg_bytes).decode()

    payload = {
        "model": MODEL,
        "prompt": question,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 1500},
    }
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    print(data.get("response", json.dumps(data)))


if __name__ == "__main__":
    main()
