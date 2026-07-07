---
name: local-vision-models
description: |
  Diagnose and run local multimodal vision (image-input) models in the
  GGUF / Ollama / llama.cpp ecosystem. Use when a local vision model
  produces garbage output, crashes on image input, is not detected as
  vision-capable, or when choosing a local vision backend for an agent
  (e.g. a Hermes auxiliary.vision config). Carries the known Qwen2.5-VL
  garbage-output bug, the gemma3-on-consumer-GPU findings, and a
  one-command verification recipe.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [vision, multimodal, ollama, llama.cpp, gguf, vlm, local-models, debugging]
    category: mlops
    related_skills: [llama-cpp, serving-llms-vllm, systematic-debugging]
---

# Local Vision Models (GGUF / Ollama / llama.cpp)

Local vision models fail in distinctive ways that are easy to misdiagnose
as GPU defects. This skill gets the classification right on the first
look so you don't burn time on the wrong fix.

## When to use

- A local vision model produces garbage / empty / random-token output
  on images but works on text
- A local vision model crashes specifically on image input (text-only
  works fine)
- A host framework says the model "does not support images" even though
  it is multimodal
- You are choosing a local vision backend for an agent or gateway and
  need to know what actually works on the target GPU
- Someone blames the GPU architecture (Blackwell, ROCm, etc.) for a
  vision-model problem — verify before accepting that

## Step 1: classify the failure (the fork that matters)

Run the model text-only, then with a real image. The combination tells
you the root cause:

| Text | Image | Diagnosis |
|---|---|---|
| works | garbage tokens (1-10 random words) | Runner mmproj / M-RoPE integration bug (model + weights are fine) |
| works | hard crash (CUDA error, runner exit) | GPU architecture kernel bug — see Blackwell note below |
| works | "model does not support images" / ignored | Host didn't detect vision capability (config/naming), not the model |
| works | OOM / eviction thrash, degraded or slow | VRAM too small; projector forced to CPU |
| works | fluent, specific, WRONG numbers on dense dashboards | VLM numeric confabulation (not an integration bug — a model-class limit) |

This split is the first fork. Garbage-vs-crash-vs-silent have different
root causes and different fixes. Classify before proposing any fix.

## Step 2: confirm with a known-good model on the SAME GPU

Before accepting any "the GPU is the problem" theory, run a second
vision model on the same hardware with the same image. If it produces
correct output, the GPU is fine and the bug is in the first model's
integration. This single test falsifies most architecture-blame theories
in under a minute.

## Known issues

### Ollama Qwen2.5-VL / Qwen2-VL garbage output — NOT a GPU bug

Verified on RTX 5070 Ti (Blackwell sm_120), Ollama 0.30.10: the model
loads clean, runs on GPU with zero CUDA errors, decodes the image, then
emits ~6 tokens of word salad. Root cause is Ollama's mmproj + M-RoPE
handling for the Qwen2-VL architecture (upstream llama.cpp commit
`e3af5563b`; tracked in Ollama issue #14388, llama.cpp issue #17930).
The SAME GGUF files work correctly in `llama-mtmd-cli` / llama-server.

Do NOT chase Blackwell/CUDA/driver here — the path is a garbage-output
integration bug, not a crash. See the reference file for the full
reproduction and evidence.

### Blackwell (RTX 50-series) vision crash — a DIFFERENT bug

There IS a real Blackwell vision bug (Ollama issue #14446, RTX 5080/5090):
vision inference dies with `illegal memory access` / `device kernel
image is invalid` at num_gpu>=1, text-only works. This is a **crash**,
not garbage. It is a different root cause from the Qwen2.5-VL garbage
bug above. Garbage = integration bug; crash = kernel bug. Classify first.

### gemma3 on consumer 12 GB Blackwell — works well

Verified on RTX 5070 Ti 12 GB with a dense screenshot: `gemma3:4b`
correct (~43 s), `gemma3:12b` best output — read specific values like
"GPU Memory 2.93GB/8GB (37%)", consistent across runs (26-83 s). The
12 b reaches a stable full-GPU offload (35/35 layers) once VRAM
clears, even though transient logs during contention show only 23/49
layers + projector on CPU. `llava:latest` is a reliable baseline.

**Counterintuitive lesson:** on 12 GB, gemma3:12b can be the RIGHT
choice even when offload math looks too tight. Do not predict
degradation from a single log snapshot during memory contention — run it.

## Choosing a local vision backend

For an agent auxiliary-vision config (e.g. Hermes `auxiliary.vision`):

1. **gemma3 (4b or 12b)** — first-party Ollama model, no import bugs,
   works on consumer GPUs. 12b if VRAM allows (>=8 GB free after the
   main model), 4b as a safe default.
2. **llama.cpp + Qwen2.5-VL GGUF** — if you specifically want Qwen2.5-VL
   quality, run it under llama-server (not Ollama) and point the config
   at that OpenAI-compatible endpoint. Same weights, working integration.
3. **llava** — reliable baseline, lower quality than gemma3.

Avoid on Ollama today: qwen2.5vl / qwen2-vl (garbage-output bug until
Ollama rebases past the fix).

## Verify before declaring it works

Always run the real image test before reporting success. A correct
result reads back actual values from the image (app names, percentages,
labels) — not "it should work" reasoning. See the reference file for the
one-command recipe. This pairs with the `systematic-debugging` skill's
verify-don't-guess rule.

**Critical pitfall — don't verify with your eyes closed.** Fluent,
specific prose is NOT evidence of correct vision. VLMs confabulate
plausible numbers on dense dashboards (see next section). If you ask a
VLM to "describe this screenshot" and it returns "System Monitor, GPU
1%, VRAM 2.93GB/8GB (37%)" — that output reads as authoritative but may
be largely fabricated. You MUST compare values against ground truth
(either the user's truth table or an OCR pre-pass) before declaring the
model works. Declaring success on prose fluency alone is a calibration
failure that bites in head-to-head benchmarks and production alike.

## VLM numeric confabulation on dense dashboards

Distinct from the garbage-output and crash bugs above. The model runs
fine, reads the scene semantically ("this is a system monitor"), but
**hallucinates precise numeric values** for small-text readouts
(percentages, frequencies, temperatures, byte counts). The output is
fluent and confident — exactly the failure mode that fools you into
thinking the model is working.

Measured on the same dense screenshot (KDE System Monitor with 8 numeric
fields) against a ground-truth table:

| Backend | Exact-value accuracy | Failure shape |
|---|---|---|
| gemma3:12b (two runs, two different observers) | ~1/8 (13%) | confident wrong numbers |
| gemma3:4b | low | got app name + panel, missed most values |
| llava | low | generic scene description, no values |
| qwen2.5vl:7b | 0/8 | garbage ("The of") — different bug |

**Root cause (model-class limit, NOT an integration bug):** small/quantized
VLMs "know" what a dashboard panel looks like and generate plausible
values rather than reading pixels. More VRAM / a bigger model reduces but
does not eliminate this — even a 27b will confabulate digits on dense
small-font readouts. This is the same family of hallucination as LLM
arithmetic errors: plausible output, no grounding.

**The fix is OCR-first, not a bigger VLM.** For any task where the user
needs exact values from a dashboard, form, table, or code listing, run
tesseract OCR and treat its output as ground truth for the numbers;
reserve the VLM for semantic description (scene, layout, colors) where
it does not need to be pixel-accurate. See the `scripts/ocr-first-extract.py`
recipe — a hybrid OCR+layout-parser pipeline scored 8/8 (100%) on the
same screenshot where the best VLM scored 1/8, using zero GPU.

## The general solution: 3-layer hybrid (VLM + OCR + pixels)

The findings above resolve into one architecture that handles ANY image —
dashboards, frontends, photos, screenshots during computer control. No
single layer works alone; each compensates for the others' failure modes.

| Layer | Tool | Owns | Weakness |
|---|---|---|---|
| 1. Semantics | local VLM (gemma3:12b) | what each region IS, graph shapes, colors, positions | hallucinates exact numbers |
| 2. Text/values | tesseract OCR | exact digits, zero confabulation | can't see shapes/layout/meaning |
| 3. Geometry/color | numpy pixel analysis | exact palette, region bounds, graph polylines | can't label what anything is |

**Merge rule (the part that makes it general):** the VLM labels each
region's TYPE, then each region routes to its specialist — text regions
to OCR, graph regions to the pixel-tracer, icons/layout to the VLM.
Numbers ALWAYS from OCR. Shapes/colors ALWAYS from pixels. Meaning
ALWAYS from VLM. Each layer's weakness is covered by another's strength.

This is what scales the dashboard fix to "see frontends and control the
PC": computer_use captures and vision_analyze outputs feed this pipeline.
OCR deterministically handles any number/form/code readout; the VLM
handles "is this button enabled / does the layout look right"; pixels
verify colors and positions. Wire it as OCR → VLM, with OCR winning any
conflict on numbers.

## Graph-tracing pitfall: line vs area (mode matters)

When the pixel layer traces a graph region for its polyline, the trace
mode MUST match the graph's render style or you silently miss the graph
entirely.

- **Thin line graphs** (e.g. a usage sparkline): trace the TOPMOST
  reddish pixel per column. `mode=line`.
- **Filled area / plateau graphs** (e.g. VRAM usage sitting at 47%, a
  temperature plateau): the topmost-pixel heuristic returns the flat
  TOP of the fill, which looks correct — BUT if the fill is tall (a high
  plateau), naive top-of-fill loses the shape variation. Use the
  median of the top quartile of reddish y-values per column to track the
  plateau's contour. `mode=area`.

**Concrete miss this cost:** on the KDE System Monitor screenshot, a
`mode=line`-only tracer correctly caught the thin Total Usage sparkline
but MISSED the Video Memory Usage graph entirely (a high plateau that
steps down at 85%) — it was misclassified as a progress bar. The
Temperature plateau was misclassified as a text row. Both were invisible
to the line tracer because they're area fills, not thin lines. The VLM
layer ("this is a high-plateau area graph stepping down near the right")
catches what the pixel tracer alone misses. This is why the layers must
merge, not compete.

See `scripts/vision-pipeline-v2.py` for the integrated 3-layer
implementation with both trace modes and the VLM-as-region-labeled call.

## GPU sharing etiquette (shared single-GPU machines)

Running a local vision model loads GB of VRAM via Ollama, and on a shared
single-GPU machine the user may be running their own GPU work in parallel
(another agent in a head-to-head benchmark, a game, a render, a second
model). Treat the GPU like the user's cursor in `computer_use`: **don't
grab it without checking, and release it the moment you're done.** The
user has enforced this explicitly — skipping it is one of the fastest ways
to lose trust on a shared machine.

Hard rules:

1. **Check before you load.** Query state before any call that puts a
   model in VRAM:
   ```
   nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
   curl -s http://localhost:11434/api/ps     # ollama models currently resident
   nvidia-smi --query-gpu=memory.free --format=csv,noheader
   ```
   If a model is already resident or free VRAM is tight, assume someone
   else is mid-work.

2. **If the GPU is busy, don't load.** Wait, or pick a CPU-only path.
   Don't evict another process's model. For OCR / pixel-analysis work
   there is often a zero-GPU alternative (tesseract, numpy) — prefer it
   when the GPU is contested.

3. **Unload the moment your inference is done.** Ollama keeps models
   resident for ~5 min after the last call (`keep_alive` default), which
   silently holds GB of VRAM after you've stopped. Explicitly release:
   ```
   curl -s http://localhost:11434/api/generate \
     -d '{"model":"gemma3:12b","keep_alive":0}' >/dev/null
   ```
   Then re-check `nvidia-smi` / `/api/ps` to confirm the model actually
   unloaded before reporting "done."

4. **Report GPU state on completion** of any GPU-touching task: which
   processes hold VRAM and how much is free. The user should never have
   to ask "are you still holding the GPU?" — that question means you
   skipped this step.

This applies to every tool that loads a model — `vision_analyze` with a
local backend, ad-hoc `execute_code` that spins up a VLM, delegated
subagents that call Ollama. Same rule everywhere: check, load, unload,
confirm.

## Blind reconstruction when NO VLM backend works

Distinct from everything above: sometimes you have no working vision
backend at all (auxiliary VLM out of credit, wrong plan entitlement,
local VLM broken, no key for a paid one). A user still asks you to
"reconstruct / draw / reproduce this image." You can — via raw pixel
analysis, no model. OCR gets the text; **pixel analysis gets the
visuals** (graph polylines, region colors, icon positions, panel
geometry) that OCR can't see.

Core rule: **measure, don't guess.** A reconstruction built from numpy
measurements scored 79.6% palette-overlap and was recognizable; one
built from plausible guesses scored ~30% and was rated 3/10. Everything
you'd invent — the graph shape, the accent color, the icon layout — can
be extracted deterministically. Run
`scripts/pixel-analysis-probe.py <image>` for the one-shot measurement
dump (palette, accent bbox + color, graph polyline normalized for SVG,
icon centers, panel bands). Full technique + the headless-Chromium
render recipe + the objective fidelity check are in
`references/blind-image-reconstruction.md`.

Honest scope: pixel analysis yields a **schematic likeness** (correct
structure, colors, graph shape, layout) — NOT pixel-exact fidelity. Icon
glyphs are stand-ins, fonts differ, radii are approximate. Declare these
limits to the user rather than confabulating the parts you can't measure.

## Position-faithful rendering (the 1/10 to 8/10 jump for redraws)

The biggest scoring jump in UI redraw came from ONE change: render every
extracted element at its **measured (x,y) coordinate**, not stacked in a
flex column. A generic card-dumping renderer (emit cards top-to-bottom)
scored 1/10 on a dashboard even with perfect extraction — because the
original layout is two-dimensional and stacking flattens it. The same
data rendered with `position:absolute; left:{x}px; top:{y}px` jumped to
~8/10, recognized and correct.

This is the technique to reach for when the task is "reconstruct /
redraw this screenshot" AND the goal is a faithful likeness. It is the
render counterpart to the 3-layer extraction: extraction gets the data,
position-faithful rendering places it correctly. Full pitfalls + recipe
in `references/position-faithful-ui-render.md`; working implementation
in `scripts/render-faithful.py`.

The OCR label-value pairing has specific failure modes that cost
exact-value accuracy (all hit in practice — see the reference for fixes):

- **sidebar words merged into the value row** ("Drive 1.85 GHz"): strip
  the prefix before matching; don't gate value rows on center-x.
- **two-column value rows** ("0% 0%" for Encoder/Decoder): split at
  midpoint, left half to the left field, right half to the right field.
- **OCR drops a label word** ("Power" not "Power Usage"): tolerant
  regex like `^Power(\s*Usage)?$`.
- **graph above the label, not below**: assign graphs by y-overlap with
  the label-value span, not by "nearest below."

Honest ceiling: ~8/10 for structured single-window dashboards. Higher
fidelity needs pixel synthesis or a generative image model. Complex
scenes (wallpapers, overlapping windows, thumbnails of other images) do
NOT generalize to this technique — declare that rather than overfitting
to one image.

## References

- **[multimodal-vision-pitfalls.md](references/multimodal-vision-pitfalls.md)** — full reproduction of the Qwen2.5-VL garbage-output bug, the gemma3-on-12 GB evidence table, the Blackwell crash distinction, the VLM-confabulation evidence table, and the one-command verification recipe (text-only + image + journal grep)
- **[blind-image-reconstruction.md](references/blind-image-reconstruction.md)** — reconstruct a UI from raw pixels when no VLM backend works. Measure-don't-guess rule, the four key measurements (region avg, accent polyline, variance-peak icon rows, panel-bbox classify), headless-Chromium render recipe (with the `chrome-linux64` path gotcha), and the palette-overlap fidelity check for objective self-scoring
- **[scripts/ocr-first-extract.py](scripts/ocr-first-extract.py)** — reusable OCR-first value-extraction pipeline (tesseract + layout parser). 8/8 vs VLM 1/8 on dense dashboards. Run it as the deterministic numbers path; layer a VLM on top for semantics only.
- **[scripts/vision-pipeline-v2.py](scripts/vision-pipeline-v2.py)** — the integrated 3-layer pipeline (VLM semantics + OCR values + pixel geometry) with the line-vs-area graph-tracing modes and the VLM-as-region-labeled merge call. Use this when the task is "understand any image" rather than just "extract numbers."
- **[scripts/pixel-analysis-probe.py](scripts/pixel-analysis-probe.py)** — one-shot pixel-analysis dump for blind reconstruction: dominant palette, accent bbox + median color, normalized graph polyline (ready for SVG), sidebar icon y-centers, panel row bands. No GPU, no model, no network.
- **[position-faithful-ui-render.md](references/position-faithful-ui-render.md)** — the technique that took a UI redraw from 1/10 (stacked cards) to ~8/10 (every element at its measured x,y). Covers the core placing-vs-stacking principle, the five OCR label-value pairing pitfalls (sidebar-word contamination, two-column "0% 0%", dropped label words, graph-above-label, value-crossing), graph-to-label assignment by y-overlap, the SVG normalization (with the y-flip), and the render-at-native-resolution-then-scale recipe. Honest ceiling and scope.
- **[scripts/render-faithful.py](scripts/render-faithful.py)** — position-faithful renderer for structured dashboards (GNOME Resources, htop, Task Manager). Extracts label+value bboxes via OCR, detects graph bands via pixel scan, assigns graphs by y-overlap, renders every element at measured coordinates. Customize the FIELDS list for a new app. Zero GPU, zero VLM in the critical path.
