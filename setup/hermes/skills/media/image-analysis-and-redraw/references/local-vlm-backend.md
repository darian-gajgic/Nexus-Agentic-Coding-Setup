# Local VLM backend setup + the Qwen2.5-VL misdiagnosis case study

Session-grounded reference for `image-analysis-and-redraw`. Covers pointing
Hermes' own `auxiliary.vision` at a local Ollama VLM (so `vision_analyze` and
`computer_use` captures work without a paid cloud vision API), and a debugging
case where the obvious diagnosis (Blackwell GPU incompatibility) was wrong and
the real cause was an Ollama/llama.cpp integration bug.

## Wiring auxiliary.vision to a local Ollama VLM

Hermes routes image analysis (`vision_analyze`, screenshot interpretation
during `computer_use`) through `auxiliary.vision` in `~/.hermes/config.yaml`.
Point it at a local Ollama model to avoid per-call cloud cost:

```yaml
auxiliary:
  vision:
    provider: ollama
    model: gemma3:12b      # or gemma3:4b — both report capabilities: ['completion','vision']
```

Verification that the backend serves vision correctly (bypasses any in-session
config snapshot, so you can test before a `/reset`):

```bash
# 1. model advertises vision capability?
curl -s http://localhost:11434/api/show -d '{"name":"gemma3:12b"}' | jq '.capabilities'

# 2. OpenAI-compatible endpoint actually reads an image?
base64 -w0 img.png | curl -s http://localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma3:12b","messages":[{"role":"user","content":[
    {"type":"text","text":"describe this"},
    {"type":"image_url","image_url":{"url":"data:image/png;base64,<B64>"}}]}]}'
```

Config changes are snapshotted at session start. A running session keeps using
the OLD `auxiliary.vision` until `/reset` or a restart — call the Ollama API
directly (above) to get vision working in the current session immediately.

## Case study: the Qwen2.5-VL misdiagnosis

Symptom: `ollama run qwen2.5vl:7b` + an image produced "The of" (6 garbage
tokens) on an RTX 5070 Ti (Blackwell, sm_120). Claude Code diagnosed it as a
**Blackwell GPU architecture problem** and chased CUDA/driver fixes.

That diagnosis was wrong. Live evidence on the same GPU:

- `qwen2.5vl:7b` + image → "The of" (garbage), 174s, NO CUDA error in journal
- `llava:latest` + same image → correct, detailed, 21s
- `gemma3:4b` + same image → correct, read app name + CPU%

If it were Blackwell, the other two models would ALSO crash. They didn't. The
GPU's vision path was fine.

**Real root cause:** a known Ollama garbage-output bug for the Qwen2-VL /
Qwen2.5-VL architecture specifically — issue #14388, upstream llama.cpp commit
`e3af5563b` ("store mrope data in KV cell") introduced an M-RoPE
sequence-position regression that breaks Qwen2.5-VL image decoding. The same
GGUF files work correctly in `llama.cpp`/`llama-mtmd-cli` directly.

**The lesson — distinguish the two Blackwell vision failure modes:**

1. Blackwell CUDA crash (issue #14446, RTX 5080/5090): vision path dies with
   "illegal memory access" at num_gpu≥1. THIS is the Blackwell bug.
2. Garbage-output bug (issue #14388): model runs clean, no CUDA error, but any
   image → random tokens. This is an Ollama/llama.cpp mmproj+M-RoPE bug.

If you see "garbage tokens" (not a CUDA crash) from a Qwen-VL model on
Blackwell, do NOT chase the GPU. Use `gemma3` (4b/12b) or run `llama.cpp`
directly. Chasing Blackwell/CUDA/driver on a garbage-output bug wastes hours
because the GPU path works — the bug is in the model-integration code.

## Why a separate "vision-works" check belongs in every analysis session

`vision_analyze` silently falls back to a paid cloud VLM when the local one is
misconfigured, and the fallback's errors (e.g. Z.AI code 1311 "subscription
plan does not yet include access to GLM-5V-Turbo") look like a billing problem
but are actually an entitlement/endpoint mismatch. Before reasoning about an
image, confirm which backend actually answered. A session that thinks it has
working vision but is hitting a broken fallback will produce confident garbage.

## GPU sharing with a concurrent agent

Ollama keeps models warm by default, which blocks a co-running agent from
loading. Free VRAM after your inference:

```bash
curl -s http://localhost:11434/api/generate -d '{"model":"gemma3:12b","keep_alive":0}'
```

Check before YOU load: `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader`
and `curl -s http://localhost:11434/api/ps`. OCR (tesseract) and numpy pixel
analysis are CPU-only — use them freely while the GPU is occupied; reserve the
VLM call for the one pass that needs it.
