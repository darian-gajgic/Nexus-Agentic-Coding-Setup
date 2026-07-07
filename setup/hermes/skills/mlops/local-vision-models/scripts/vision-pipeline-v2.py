#!/usr/bin/env python3
"""
General 3-layer vision pipeline: VLM (semantics) + OCR (values) + pixels (geometry).

The merge rule that makes it general:
  VLM labels each region's TYPE -> route each region to its specialist.
    text regions   -> OCR (exact numbers, zero hallucination)
    graph regions  -> pixel-tracer with mode = line | area
    icons/layout   -> VLM (semantic only)
  Numbers ALWAYS from OCR. Shapes/colors ALWAYS from pixels. Meaning ALWAYS from VLM.

WHEN: any image-understanding task where a single layer would fail —
dashboards (VLM confabulates numbers), unfamiliar UIs (OCR can't see
layout), blind reconstruction (pixel-only misses plateau graphs).

REQUIREMENTS:
  - tesseract-ocr binary  (apt install tesseract-ocr)
  - PIL, numpy
  - a local VLM via Ollama at http://localhost:11434 (gemma3:12b recommended;
    see SKILL.md "Choosing a local vision backend")

USAGE:
  from vision_pipeline_v2 import vlm_describe, ocr_words, ocr_values, pixel_analysis, trace_graph
  sem = vlm_describe(img_path)                 # Layer 1
  vals = ocr_values(ocr_words(img_path), specs)# Layer 2
  px   = pixel_analysis(img_path)              # Layer 3 (palette, accent)
  line = trace_graph(img_path, y0,y1,x0,x1, mode="area")  # per-region, bbox from VLM

NOTE: the VLM call needs the Ollama backend live. If auxiliary.vision is
still pointed at a broken/paid endpoint, Layer 1 returns an error — but
Layers 2 and 3 still run standalone, which is the blind-reconstruction path.
"""
import base64, json, subprocess, urllib.request, re
from collections import defaultdict, Counter
from PIL import Image
import numpy as np

OLLAMA = "http://localhost:11434"

# ── LAYER 1: VLM SEMANTICS ──────────────────────────────────────────────
def vlm_describe(image_path, model="gemma3:12b", prompt=None):
    """Ask the local VLM for a structured region map. The VLM does NOT read
    numbers (OCR owns those) — it labels what each region IS, its graph shape,
    color, and normalized position."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    prompt = prompt or (
        "You are a vision layer for a drawing agent. Describe this image as JSON: "
        "{app, theme:{bg, accent_hex}, regions:[{name, type, x0, y0, x1, y1, shape, color}]}. "
        "type in [graph_line, graph_area, text_row, bar, icon_row, sidebar, taskbar]. "
        "shape for graphs in [flat, spike_left, plateau_high, jagged, step_down]. "
        "Do NOT read exact numbers — only structure, shapes, colors, positions. "
        "Coords normalized 0-1."
    )
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
        ]}],
        "max_tokens": 800, "temperature": 0.1,
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/v1/chat/completions",
                                 data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]

# ── LAYER 2: OCR EXACT VALUES ───────────────────────────────────────────
def ocr_words(img_path, psm=11, upscale=2):
    im = Image.open(img_path).convert("RGB")
    im2 = im.resize((im.width * upscale, im.height * upscale), Image.LANCZOS)
    big = "/tmp/_ocr_big.png"; im2.save(big)
    r = subprocess.run(["tesseract", big, "-", "--psm", str(psm), "tsv"],
                       capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines()[1:]:
        p = line.split("\t")
        if len(p) < 12: continue
        try: conf = float(p[10])
        except ValueError: continue
        t = p[11].strip()
        if conf < 45 or not t: continue
        x, y, w, h = int(p[6]), int(p[7]), int(p[8]), int(p[9])
        out.append({"t": t, "x": x/upscale, "y": y/upscale,
                    "cx": (x + w/2)/upscale, "cy": (y + h/2)/upscale})
    return out

def ocr_values(words, label_specs):
    """label_specs: list of (field, label_regex, value_regex).
    Returns {field: value} by label-above-value layout proximity."""
    bands = defaultdict(list)
    for w in words:
        bands[round(w["cy"] / 14)].append(w)
    L = [" ".join(z["t"] for z in sorted(bands[k], key=lambda q: q["x"]))
         for k in sorted(bands)]
    result = {}
    for field, lab_re, val_re in label_specs:
        for i, txt in enumerate(L):
            if re.search(lab_re, txt, re.I) and len(txt) < 28:
                for j in range(i + 1, min(i + 4, len(L))):
                    cand = re.sub(r"^(Drive|Ethernet|Wi-Fi|Properties)\s*", "", L[j]).strip()
                    m = re.match(val_re, cand, re.I)
                    if m:
                        result[field] = m.group(1); break
                else: continue
                break
    return result

# ── LAYER 3: PIXEL ANALYSIS ─────────────────────────────────────────────
def pixel_analysis(img_path):
    im = Image.open(img_path).convert("RGB")
    a = np.array(im).astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    q = (a // 32) * 32
    pal = Counter(map(tuple, q.reshape(-1, 3))).most_common(8)
    palette = [f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}" for c, _ in pal]
    reddish = (r > 120) & (r > g + 40) & (r > b + 40)
    accent = None
    if reddish.sum() > 100:
        ac = a[reddish].mean(axis=0).astype(int)
        accent = f"#{ac[0]:02x}{ac[1]:02x}{ac[2]:02x}"
    return {"size": im.size, "palette": palette, "accent": accent}

def trace_graph(img_path, y0, y1, x0, x1, mode="line"):
    """Trace a graph within a bounding box. Bbox should come from the VLM layer.
    mode='line'  — thin line graph: topmost reddish pixel per column.
    mode='area'  — filled plateau: median of the top quartile of reddish y per
                   column, so high-plateau contours are tracked instead of lost."""
    im = Image.open(img_path).convert("RGB")
    a = np.array(im).astype(int)[y0:y1, x0:x1]
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    reddish = (r > 100) & (r > g + 35) & (r > b + 35)
    pts = []
    for x in range(a.shape[1]):
        col = reddish[:, x]
        ys = np.where(col)[0]
        if len(ys):
            top = ys.min() if mode == "line" else int(np.median(ys[:max(1, len(ys) // 4)]))
            pts.append((x0 + x, y0 + top))
    return pts

# ── MERGE ───────────────────────────────────────────────────────────────
def merge(vlm_json, ocr_vals, px):
    """VLM tells us what each region IS; specialists fill exact values/shapes/colors.
    Conflict rule: on numbers, OCR wins; on shapes/colors, pixels win; on meaning, VLM wins."""
    return {
        "semantics": vlm_json,        # region map + shapes (what each region is)
        "exact_values": ocr_vals,     # numbers (OCR, no hallucination)
        "exact_colors": px,           # palette + accent (measured)
        # graph polylines are traced per-region using the VLM's bounding boxes
        # and the matching mode (line vs area)
    }

if __name__ == "__main__":
    IMG = "/home/sinep/Pictures/Resources_Monitor.png"
    print("=== LAYER 3 (pixels) ==="); print(pixel_analysis(IMG))
    print("\n=== LAYER 2 (OCR values) ===")
    specs = [
        ("Total Usage", r"Total\s*Usage", r"(\d+%)"),
        ("VRAM", r"Video\s*Memory\s*Usage", r"([\d.]+\s*GB\s*/\s*[\d.]+\s*GB)"),
        ("GPU Freq", r"GPU\s*Frequency", r"([\d.]+\s*GHz)"),
        ("Power", r"Power\s*Usage", r"([\d.]+\s*W)"),
        ("Temp", r"Temperature", r"(\d+°C)"),
    ]
    print(ocr_values(ocr_words(IMG), specs))
    print("\n=== LAYER 1 (VLM) ===")
    try:
        print(vlm_describe(IMG)[:600])
    except Exception as e:
        print(f"VLM layer unavailable ({type(e).__name__}). Run with a live Ollama gemma3 to populate.")
