# Cross-Provider Usage & Cost Aggregation

Recipe for the `GET /api/usage` endpoint of an agent control plane — aggregate token
usage and estimated cost across every provider the user actually runs (here: GLM-5.2 via
Z.AI, Claude Code, and Hermes Agent). Pure stdlib. Validated against a manual single-file
spot-check (the two bugs below were caught by exactly that check).

## Data sources (where token usage actually lives)

| Provider | Source | Token field | Model field | Timestamp field |
|----------|--------|-------------|-------------|-----------------|
| GLM-5.2 (Z.AI) | `~/.claude-glm/projects/*/*.jsonl` | `message.usage.{input,output}_tokens` | `message.model` | `timestamp` (ms epoch) |
| Claude Code | `~/.claude/projects/*/*.jsonl` | `message.usage.{input,output,cache_read,cache_creation}_tokens` | `message.model` | `timestamp` (ms epoch) |
| Hermes Agent | `~/.hermes/state.db` → `messages.token_count` | `token_count` (total) | `sessions.model` | `timestamp` (s epoch) |

Project name is recoverable from the parent dir: `-home-sinep-research-harness` → `research/harness`.

## BUG #1 — transcript usage records are SNAPSHOTTED, not per-turn (30-50x overcount)

Claude Code writes the SAME `message.usage` block onto every `assistant` line within a turn.
A 5-message turn reports the same `(input, output, cache_read, cache_creation, model)` tuple
5 times. Summing naively → $90,000 reported for ~$2,550 of real spend.

```python
seen = set()  # dedupe per file
for line in open(path, errors="replace"):
    rec = json.loads(line)
    usage = (rec.get("message") or {}).get("usage")
    if not usage: continue
    in_tok  = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)
    cr      = usage.get("cache_read_input_tokens", 0)
    cc      = usage.get("cache_creation_input_tokens", 0)
    key = (in_tok, out_tok, cr, cc, rec["message"].get("model"))
    if key in seen: continue   # <-- the fix
    seen.add(key)
    ...aggregate...
```

Verification: before the fix, a single 5-assistant-message file summed to 5x the true
turn. After, it sums to 1x.

## BUG #2 — cache_read and cache_creation are priced differently from base input

Anthropic prompt-cache pricing: `cache_read` ≈ **10%** of the input rate; `cache_creation`
≈ **1.25x** the input rate. Pricing all tokens at the base input rate overcounts cache_read
~10x (and cache_read dominates long-context sessions, so this alone inflated Claude's
apparent spend to ~$90k).

```python
PRICE_TABLE = {  # USD per 1M tokens
    "glm-5.2":       {"in": 0.5,  "out": 0.5},
    "claude-opus":   {"in": 15.0, "out": 75.0},
    "claude-sonnet": {"in": 3.0,  "out": 15.0},
    "default":       {"in": 1.0,  "out": 3.0},
}

def cost(in_tok, out_tok, model_cls, cache_read=0, cache_creation=0):
    p = PRICE_TABLE.get(model_cls, PRICE_TABLE["default"])
    base = (in_tok/1e6)*p["in"] + (out_tok/1e6)*p["out"]
    cache = (cache_read/1e6)*(p["in"]*0.10) + (cache_creation/1e6)*(p["in"]*1.25)
    return base + cache
```

**Always sanity-check the aggregate** against a manual single-file calculation before
trusting it. Spot-check: one known session, hand-summed, compared to the endpoint's number
for that file. The $90k figure looked wrong precisely because a small session should not
cost $0.85 × N-turns × 5; the manual check proved it.

## Model classification (normalize variant names → price class)

```python
def classify(model: str) -> str:
    m = (model or "").lower()
    if "glm" in m:    return "glm-5.2"
    if "opus" in m:   return "claude-opus"
    if "sonnet" in m: return "claude-sonnet"
    if "haiku" in m:  return "claude-haiku"
    if "qwen" in m:   return "qwen"          # $0 — free/local
    if any(k in m for k in ("ollama","gemma","llama")): return "ollama"  # $0
    return "default"
```

Local models (Ollama, Qwen on GPU) are $0 — track their tokens for volume but never cost them.

## Response shape (what the frontend consumes)

```json
{
  "providers": [
    {"id": "glm",    "name": "GLM-5.2 (Z.AI)", "sessions": 49,
     "input_tokens": 936307, "output_tokens": 295862,
     "cache_read_tokens": 0, "est_cost_usd": 1.10},
    {"id": "claude", "name": "Claude Code", "sessions": 30,
     "input_tokens": 494508, "output_tokens": 6390143,
     "cache_read_tokens": 1106532394, "est_cost_usd": 2550.16},
    {"id": "hermes", "name": "Hermes Agent", "sessions": 36, "est_cost_usd": 0.00}
  ],
  "totals": {"sessions": 115, "total_tokens": 8113439, "est_cost_usd": 2551.26},
  "timeseries": [{"day": "2026-07-04", "models": {"glm-5.2": 42000, "claude-opus": 880000}}],
  "per_model": {"claude-opus": {"in": 494508, "out": 6390143, "cost": 487.98}},
  "top_projects": [{"project": "research/harness", "tokens": 482100000}],
  "price_table": { "...": "..." },
  "cache_ttl": 60
}
```

Cache the full parse for 60s — transcript parsing is ~100ms across ~80 files and there is
no reason to re-parse on every dashboard poll.

## What NOT to do

- Don't source cost from provider billing APIs — they lag, they need creds, they don't break
  down by local project. Local transcripts are authoritative for per-project attribution.
- Don't sum cache_read into input_tokens at full rate — that's the $90k bug.
- Don't forget the dedupe `seen` set — that's the other $90k bug.
- Don't present a cost figure without a "estimates from local transcripts × price table"
  disclaimer; prices drift and users will screenshot the number.
