---
name: image-analysis-and-redraw
description: |
  Analyze a screenshot or image to UNDERSTAND it, EXTRACT exact data from it,
  and RECONSTRUCT/REDRAW it faithfully — when your vision backend is a small
  local VLM (e.g. Ollama gemma3:12b) rather than a top-tier hosted model.
  Covers the 3-layer OCR+VLM+pixel pipeline, why HTML redraw caps at ~3/10
  and PIL pixel-compositing is the path to 8/10, and the verify-don't-predict
  discipline that prevents confident-but-wrong conclusions about images.
version: 1.0.0
metadata:
  hermes:
    tags: [vision, ocr, image-analysis, screenshot, redraw, vlm, local-models]
    category: media
---

# Image analysis and redraw (small-local-VLM regime)

You are operating in a regime where your vision model is a small/quantized local
VLM (7-12B) rather than a frontier hosted model. In this regime three things are
true and they shape everything:

1. The VLM **hallucinates precise numbers** on dense dashboards. It "knows" what
   a GPU panel looks like and generates plausible values rather than reading
   pixels. Confident, wrong, plausible-looking output is the failure mode.
2. The VLM is **good at semantics** — "this is a sidebar with N rows, that is a
   high-plateau area graph, the app is GNOME Resources." Use it for that.
3. Faithful **redraw** of an arbitrary image is a separate, hard problem from
   understanding it. HTML/CSS reconstruction caps at ~3/10 fidelity because it
   cannot reproduce pixel-level font rendering, icon artwork, and anti-aliased
   graph curves. PIL pixel-compositing (render text/graphs/panels directly to a
   PNG canvas at measured coordinates) is the realistic path to 7-8/10.

## The 3-layer pipeline (the core technique)

For any image you must understand, extract data from, or redraw:

| Layer | Tool | Strength | Weakness |
|-------|------|----------|----------|
| 1. Semantics | VLM (gemma3:12b via Ollama `/v1/chat/completions`) | names regions, identifies graph shapes/colors, reads layout | hallucinates exact numbers |
| 2. Values/text | `tesseract` (psm 11 sparse, psm 6 column-aware) | exact digits/words, zero hallucination | blind to shapes, graphs, meaning |
| 3. Geometry/color | `numpy` on the pixel array | exact palette, accent, region boundaries, traced graph polylines | can't label what anything IS |

**Merge rule:** the VLM labels each region's TYPE → text regions route to OCR,
graph regions route to the pixel-tracer (mode=`line` for thin line graphs =
topmost reddish pixel per column; mode=`area` for filled plateaus = top-quartile
median), semantics stay from the VLM. **Numbers ALWAYS from OCR; shapes/colors
ALWAYS from pixels; meaning ALWAYS from VLM.** Each layer's weakness is covered
by another's strength.

A worked example and the full evidence (including a truth table showing a 12B
VLM scoring 1/8 on exact values while OCR scored 8/8) is in
`references/redraw-fidelity-and-ocr.md`.

## Redraw: choose the fidelity tier deliberately

Redraw is NOT one task — it's a spectrum. Pick the tier that matches the goal:

- **Structure-only (HTML/CSS, ~3/10):** fine when you only need to show you
  understood the layout. Cheap, fast, editable. Do NOT promise more.
- **Faithful (PIL pixel-compositing, targets 7-8/10):** required when the user
  wants the image to *look like* the original. Render at native resolution.
  Use `ImageDraw.rounded_rectangle` for panels, `ImageFont.truetype` with the
  system font for anti-aliased text, `draw.line(..., joint='curve')` for graphs,
  and fill area-graphs with a semi-transparent polygon of the measured accent
  color. Measure every element's bbox from the original and place it at those
  exact coordinates — do NOT stack cards generically.
- **Do not reach for a diffusion model** for faithful redraw of a specific UI.
  A diffusion model generates "a system monitor," not THIS monitor with THESE
  exact values. Wrong tool. (It's the right tool for "generate a pretty image
  in this style" — a different task.)

Common redraw failure: the generic "card-dumping" renderer. If you take the
VLM's region list and emit cards top-to-bottom, you destroy the layout and score
1/10 even with perfect data. Layout IS the image. Render at measured (x,y).

## The verify-don't-predict discipline (load-bearing)

In this session I twice made confident claims about images I could not see,
based on logs + web anecdotes, when a single test would have settled it:

1. I predicted gemma3:12b would be "degraded/unreliable on 12GB" from a
   transient VRAM log snapshot + Reddit reports. A 1-command test showed it
   worked well. I had to publicly recant.
2. I declared a reconstruction "working" because its prose sounded good —
   without checking a single value against ground truth. A truth table showed
   the values were largely confabulated.

**Rule: when verification is one command away, prediction-from-logs is the
wrong move.** Reasoning from indirect signals (logs, web reports, plausible
prose) is for when direct verification is expensive or impossible. Image work
is almost never that — `tesseract` + a pixel sample is seconds. Run it.

Corollary: **fluent output is not verified output.** A VLM that writes
"5.97 GB / 12.82 GB (37%)" in confident prose may be fabricating. Treat any
VLM-read number as unverified until OCR or pixel-analysis confirms it.

## Small-VLM context-window limit → downscale a preview

A 2160² PNG (the output of a 2×-device-scale render) blows a 4096-token local
VLM context (`exceed_context_size_error`, 4277 tokens > 4096). The fix is to
**render a small JPEG preview and run the VLM on that**: the model reads layout,
legibility, and composition perfectly at 540px; it only needs full resolution
for reading small text or exact values.

```python
from PIL import Image
Image.open("asset.png").convert("RGB").resize((540,540), Image.LANCZOS).save("preview.jpg", quality=88)
```

Rule: when vision returns a context-size error on a large image, downscale to
~500–600px before retrying — do not treat it as "vision is broken" (that hardens
into a self-imposed refusal). Verify crispness separately by checking the
source PNG's dimensions/aspect with `PIL.Image.open`, not by re-running vision.

## Working alongside another agent on the same GPU

When a concurrent agent (Claude Code, a second Hermes, etc.) shares your GPU:

- **Check before you load.** `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`
  and `curl -s http://localhost:11434/api/ps`. If models are resident, wait or
  use a CPU-only path.
- **Prefer CPU-only layers where possible.** OCR (tesseract) and pixel analysis
  (numpy) are CPU-only — run them freely, they don't touch the GPU.
- **Unload when done.** Ollama keeps models warm by default:
  `curl -s http://localhost:11434/api/generate -d '{"model":"gemma3:12b","keep_alive":0}'`
  Free the VRAM so the other agent can load.
- **Call the VLM via the Ollama API, not by loading weights yourself.** One
  resident gemma3:12b serves both agents; you loading your own copy wastes VRAM.

Details on pointing Hermes' own auxiliary.vision at the local VLM, plus a
Qwen2.5-VL misdiagnosis case study, are in `references/local-vlm-backend.md`.

## When NOT to use this skill

- **Frontend DOM testing** — use the browser/Playwright tools for DOM-accurate
  assertions (element present, text content, enabled state). This skill is for
  when you must reason about pixels the DOM can't give you: screenshots, native
  apps, photos, dashboards-without-an-API.
- **Generating images** — that's image_gen / diffusion, a different task.
- **One-off "what's in this photo"** — just call the VLM; no pipeline needed.
  The pipeline earns its cost on dense, numeric, or must-be-redrawn images.
