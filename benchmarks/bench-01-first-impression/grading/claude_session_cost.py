#!/usr/bin/env python3
"""Token usage + API-equivalent cost from Claude Code session transcript(s).

Usage:  python3 claude_session_cost.py <session.jsonl> [more.jsonl ...]

Sums per-model usage across all assistant messages (deduped by message id,
keeping the last occurrence — streaming rewrites the same id), including
subagent sidechains, and prices them with the rates verified in the repo's
MODEL-PRICING-2026-07-10.md. Cache writes use the 5m/1h breakdown when the
transcript provides one, else they are priced at the 5-minute rate (1.25x).

This is an API-EQUIVALENT figure for comparison — subscription usage is not
billed per token.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime

# USD per 1M tokens: (input, output) — MODEL-PRICING-2026-07-10.md
PRICES = {
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-4-8": (5.0, 25.0),
}


def price_for(model):
    for prefix, p in PRICES.items():
        if model.startswith(prefix):
            return p
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)

    by_id = {}          # message id -> (model, usage)
    first_ts = last_ts = None
    user_turns = 0

    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = obj.get("timestamp")
                if ts:
                    first_ts = min(first_ts or ts, ts)
                    last_ts = max(last_ts or ts, ts)
                if obj.get("type") == "user" and not obj.get("isMeta"):
                    user_turns += 1
                if obj.get("type") != "assistant":
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage")
                mid = msg.get("id")
                if usage and mid:
                    by_id[mid] = (msg.get("model", "unknown"), usage)

    agg = defaultdict(lambda: defaultdict(int))
    for model, u in by_id.values():
        a = agg[model]
        a["input"] += u.get("input_tokens", 0)
        a["output"] += u.get("output_tokens", 0)
        a["cache_read"] += u.get("cache_read_input_tokens", 0)
        cc = u.get("cache_creation") or {}
        w5 = cc.get("ephemeral_5m_input_tokens")
        w1 = cc.get("ephemeral_1h_input_tokens")
        if w5 is None and w1 is None:
            a["cache_w5m"] += u.get("cache_creation_input_tokens", 0)
        else:
            a["cache_w5m"] += w5 or 0
            a["cache_w1h"] += w1 or 0

    total_usd = 0.0
    total_tokens = 0
    unpriced = []
    print(f"{'model':<28}{'input':>10}{'output':>10}{'cache-rd':>12}{'cache-w5m':>11}{'cache-w1h':>11}{'USD':>10}")
    for model, a in sorted(agg.items()):
        tok = a["input"] + a["output"] + a["cache_read"] + a["cache_w5m"] + a["cache_w1h"]
        total_tokens += tok
        p = price_for(model)
        if p:
            pin, pout = p
            usd = (a["input"] * pin + a["output"] * pout + a["cache_read"] * 0.1 * pin
                   + a["cache_w5m"] * 1.25 * pin + a["cache_w1h"] * 2.0 * pin) / 1e6
            total_usd += usd
            usd_s = f"{usd:>10.4f}"
        else:
            unpriced.append(model)
            usd_s = f"{'?':>10}"
        print(f"{model:<28}{a['input']:>10}{a['output']:>10}{a['cache_read']:>12}{a['cache_w5m']:>11}{a['cache_w1h']:>11}{usd_s}")

    wall = ""
    if first_ts and last_ts:
        try:
            t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            wall = f"  wall-clock {(t1 - t0).total_seconds() / 60:.1f} min"
        except ValueError:
            pass
    print(f"TOTAL tokens={total_tokens}  API-equivalent USD={total_usd:.4f}  user-turns={user_turns}{wall}")
    if unpriced:
        print(f"WARNING unpriced models (tokens counted, $ excluded): {sorted(set(unpriced))}")


if __name__ == "__main__":
    main()
