# Multimodal Vision Pitfalls — Evidence and Recipes

Session-derived detail for the `local-vision-models` skill. Contains the
reproduction transcripts, the evidence table, and the verification recipe.

## 1. Qwen2.5-VL garbage output (verified 2026-07)

Environment: RTX 5070 Ti Laptop (Blackwell, sm_120, 12 GB), Ollama
0.30.10, CUDA 13.2 / driver 595, ARCHS include 1200, BLACKWELL_NATIVE_FP4=1.

Model loads and runs clean on GPU. Journal shows no CUDA errors:
`llama_prepare_model_devices: using device CUDA0 ... 6080 MiB free`,
`image decoded (batch 1/2) in 465 ms`, `image decoded (batch 2/2) in 648 ms`.

Live result with a real screenshot (Resources_Monitor.png):

```
qwen2.5vl:7b   174.3 s   prompt_eval_count: 4050   eval_count: 6
RESPONSE: "The of"
```

Text-only inference on the same model works. So the GPU path is healthy;
the failure is the runner's handling of the vision projector.

### Root cause

Ollama's mmproj (vision projector) + M-RoPE handling for the Qwen2-VL
architecture is broken. Upstream llama.cpp commit `e3af5563b` ("store
mrope data in KV cell", Dec 2025) introduced a sequence-position
regression specific to Qwen2.5-VL image decoding:

```
init: the tokens of sequence 0 in the input batch have inconsistent
sequence positions ... for M-RoPE, it is required that the position
satisfies: X < Y
llama_decode: failed to decode, ret = -1
```

Tracked in Ollama issue #14388 and llama.cpp issue #17930. The SAME GGUF
files produce correct OCR output under `llama-mtmd-cli` from a current
llama.cpp build — proving the weights are intact and the bug is in the
Ollama integration layer.

### Why "it's Blackwell" is the wrong diagnosis here

There is a real Blackwell vision crash bug (Ollama issue #14446,
RTX 5080/5090): vision inference dies with `illegal memory access` at
num_gpu>=1 while text-only works. That bug is a **crash** — the runner
terminates with a CUDA error. This Qwen2.5-VL bug is **garbage output** —
the runner completes and emits tokens, just nonsense. Different symptom,
different root cause. Garbage = integration bug; crash = kernel bug.

The falsification test is one command: run `gemma3:4b` or `llava` on the
same GPU with the same image. If they produce correct output (they do),
the GPU is fine and the architecture is not the problem.

### Workarounds (ranked)

1. Use gemma3 (first-party Ollama model, no import bug).
2. Run the Qwen2.5-VL GGUF under llama.cpp llama-server instead of
   Ollama, and point the agent's vision config at that endpoint.
3. Wait for Ollama to rebase past the upstream fix (no timeline).

## 2. gemma3 on consumer 12 GB Blackwell — evidence table

Same machine, same screenshot, same prompt, temperature 0.1:

| Model | Time | prompt_tok | Output quality |
|---|---|---|---|
| `qwen2.5vl:7b` | 174 s | 4050 | **Garbage** ("The of") |
| `llava:latest` | 21 s | 617 | Correct, detailed |
| `gemma3:4b` | 43 s | 309 | Correct — app name + CPU% |
| `gemma3:12b` | 26-83 s | 309 | **Best** — read "Top GPU Usage: 1%", "GPU Memory Usage: 2.93GB/8GB (37%)", noticed overlay window; consistent across 2 runs |

### The counterintuitive VRAM lesson

gemma3:12b Q4_K_M is 8.1 GB weights + ~600 MB vision projector + KV
cache + activations. On 12 GB it does NOT always fit — during VRAM
contention (multiple models resident), the journal showed only 23/49
layers offloaded with `disabling multimodal projector offload
reason=limited-vram` and repeated `predicted to exceed available memory,
evicting` events. That snapshot looks like a degraded pipeline.

BUT once other models unloaded and VRAM cleared (5.6 GiB used), Ollama's
scheduler reached a stable full-GPU offload (35/35 layers) and output
quality was clean and better than the 4b — no degradation on repeat.

**Do not predict degradation from a single log snapshot taken during
memory contention. Run the model.** A model that looks too big on paper
can be the right choice once the scheduler settles. This was a live
prediction error: I forecast gemma3:12b would be worse than 4b based on
offload math and r/LocalLLaMA anecdotes; one run falsified it.

## 3. Verification recipe (one command each)

```bash
# A. text-only sanity (should always work on any model)
curl -s http://localhost:11434/api/generate -d '{
  "model":"<vision-model>","prompt":"say OK","stream":false,
  "options":{"num_predict":3}}'

# B. real image — use a screenshot with text + numbers + color for a
#    strong signal. A 1x1 pixel is NOT enough to exercise vision.
B64=$(base64 -w0 /path/to/screenshot.png)
curl -s http://localhost:11434/api/generate -d "{
  \"model\":\"<vision-model>\",
  \"prompt\":\"Describe this screenshot. List specific numbers and text you can read.\",
  \"stream\":false,\"images\":[\"$B64\"],
  \"options\":{\"num_predict\":150,\"temperature\":0.1}}"

# C. classify the failure mode from the journal
journalctl -u ollama --no-pager -n 100 | grep -iE \
  'cuda error|illegal|evicting|mmproj|offload|exit status|no endpoints'
```

### Interpreting results

- Correct = reads back actual values from the image (app names,
  percentages, labels). Strong signal.
- Garbage = a few tokens of disconnected words, often switching
  languages. Integration bug.
- Crash = CUDA error + `llama runner terminated` / `exit status`.
  Kernel bug.
- Silent = `eval_count: 1` or empty response, no error logged. Often a
  capability-detection failure in the host, not the model.

### Generating a strong test image

```python
from PIL import Image, ImageDraw, ImageFont
img = Image.new('RGB', (512, 512), 'white')
d = ImageDraw.Draw(img)
d.rectangle([100, 100, 412, 412], fill='red')
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
except Exception:
    font = ImageFont.load_default()
d.text((140, 240), "HELLO", fill='black', font=font)
img.save('/tmp/test_vision.png')
```

A real screenshot with text/numbers/diagrams (e.g. a system monitor) is
an even stronger probe than synthetic shapes.

## 4. VLM numeric confabulation on dense dashboards

Distinct from the garbage-output and crash bugs. The VLM runs cleanly
and reads the scene semantically, but **fabricates precise numeric
values** for small-text readouts. The output is fluent and confident —
the danger is it reads as authoritative.

### Evidence: head-to-head against a ground-truth table

Same dense screenshot (KDE System Monitor, 8 numeric fields). Two
independent observers ran gemma3:12b; truth was known.

| Backend | Exact-value accuracy | Failure shape |
|---|---|---|
| gemma3:12b (observer A, full view) | 1/8 (13%) | confident wrong numbers: VRAM 0.00GB, freq 850MHz, power 5.3W, temp 47°C |
| gemma3:12b (observer B) | 1/8 (13%) | different wrong numbers: VRAM 2.93GB/8GB (37%) — fabricated but plausible |
| gemma3:4b | low | got app name + CPU panel, never reached GPU fields |
| llava:latest | low | generic scene description, no values read |
| qwen2.5vl:7b | 0/8 (0%) | garbage ("The of") — different bug, see §1 |
| **OCR-first pipeline (tesseract)** | **8/8 (100%)** | deterministic; also captured bonus fields (encoder/decoder %, temp-highest) |

Both gemma3:12b runs produced output that, read in isolation, looked
like a correct system-monitor description. Only comparison against
ground truth exposed that the specific numbers were confabulated.

### Why this happens (model-class limit)

Small/quantized VLMs "know" what a dashboard panel looks like and
generate plausible values rather than reading pixels. Same failure
family as LLM arithmetic errors: plausible output, no grounding. More
VRAM or a bigger model reduces but does not eliminate it — a 27b will
still confabulate digits on dense small-font readouts. This is NOT an
integration bug like §1; you cannot fix it by switching runners or
rebuilding weights.

### Fix: OCR-first, VLM-second

For tasks needing exact values, run tesseract OCR and treat its output
as ground truth for numbers; reserve the VLM for semantic description
(scene, layout, colors) where pixel-accuracy is not required. The
hybrid pipeline:

- scored 8/8 (100%) where the best VLM scored 1/8 (13%)
- used 0 MiB GPU (OCR is CPU-only) — does not compete with other models
- is deterministic — same image, same output every time

See `scripts/ocr-first-extract.py` for a reusable implementation
(label-above-value, two-column grid, and combined-value-line patterns).
The only dashboard-specific part is the label/value spec list; the
layout-detection primitives generalize.

### Calibration pitfall — do not declare success on prose fluency

Live lesson from this session: after a gemma3:12b run returned
"System Monitor, GPU 1%, GPU Memory 2.93GB/8GB (37%)", I declared the
model working and recanted an earlier "degraded" prediction. Both
halves of that were wrong — the numbers were confabulated, and I
verified output quality by reading the prose rather than checking
values against truth. The user's ground-truth table exposed it.

Rule: when a VLM reads back specific numeric values, those values are
claims, not evidence. Verify claims against ground truth (user's truth
table or an OCR pre-pass) before reporting success. Fluent prose is
the failure mode's camouflage, not proof of correctness. This applies
to any VLM-evaluation task, not just local models.

## 5. When this matters for agent vision backends
(e.g. Hermes `auxiliary.vision` pointing at Ollama), the failure modes
above manifest as the agent being "blind" — it captures/screenshots fine
but the vision model returns nothing useful. The diagnosis is the same:
classify the failure (garbage vs crash vs silent) before changing
config, GPU drivers, or models. Most "my agent can't see" reports on
Qwen2.5-VL are the garbage-output integration bug, not a hardware fault.
