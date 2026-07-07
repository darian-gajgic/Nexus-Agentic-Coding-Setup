# Provider Parameters — Authoritative Reference

Condensed capability/parameter tables for the providers in use, sourced from
each provider's official docs. **Re-verify against the live docs before
asserting a value** — these tables are a memory aid, not the source of truth.
See skill Section 1 for why derived copies drift.

## Z.AI / GLM-5.2 — reasoning_effort

Source: https://docs.z.ai/guides/capabilities/thinking (retrieved 2026-07-05)

GLM-5.2 (and GLM-5.1/5) support the `reasoning_effort` parameter when
`thinking: {type: "enabled"}` (deep thinking is enabled by default on GLM-5.2).

| Value     | Behavior (per Z.AI docs)                          |
|-----------|---------------------------------------------------|
| `max`     | DEFAULT + recommended. Deep reasoning.            |
| `xhigh`   | Mapped to `max` server-side.                      |
| `high`    | Enhanced reasoning.                               |
| `medium`  | Mapped to `high`.                                 |
| `low`     | Mapped to `high`.                                 |
| `minimal` | Model skips thinking.                             |
| `none`    | Model skips thinking.                             |

So `max` is the canonical top value per Z.AI's docs.

### Hermes config interaction — the validator gotcha (Tier 1)

Hermes's generic validator does NOT include `max`:

```python
# hermes_constants.py
VALID_REASONING_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")
parse_reasoning_effort("max")  # -> None  (treated as invalid -> reasoning disabled)
```

So `agent.reasoning_effort: xhigh` in config.yaml is deliberate: it is the
highest value Hermes's validator recognizes. Do not "fix" the config to
`max` directly — the validator rejects it and reasoning silently disables.

### The bundled-vs-user-override split (Tier 2 — and why file-reading misled us)

The BUNDLED ZAI profile at
`~/.hermes/hermes-agent/plugins/model-providers/zai/__init__.py`
emits ONLY `{"thinking": {"type": "enabled"}}` and does NOT forward
`reasoning_effort`. If you read that file you will conclude nothing is sent.

But a USER-OVERRIDE at
`~/.hermes/plugins/model-providers/zai/__init__.py`
loads AFTER the bundled profile (providers/__init__.py:_discover_providers,
last-writer-wins) and DOES forward it, mapping the Hermes effort scale onto
Z.AI's two wire-valid values:

```python
_EFFORT_MAP = {
    "minimal": "high", "low": "high", "medium": "high",
    "high": "high", "xhigh": "max", "max": "max",
}
# -> emits extra_body = {"thinking": {"type":"enabled"}, "reasoning_effort": "max"}
```

**This override is the update-safe fix** — it lives outside the git repo and
survives `hermes update` (the bundled file would be overwritten). The override
also logs `[zai-override] reasoning_effort=max` on every call for easy
verification. See skill Section 7 for the general lesson and the
`get_provider_profile(...).__module__` check.

### Verification: the override IS live and effective

Multi-run measurement (3 trials per level, hard prompt, GLM-5.2 coding-plan
endpoint, 2026-07-05) — `usage.completion_tokens_details.reasoning_tokens`:

| effort sent to API          | reasoning_tokens (approx) |
|-----------------------------|---------------------------|
| `"high"`                    | ~2,243                    |
| server default (omitted)    | ~4,930  (near-max)        |
| `"max"` (config via override) | ~6,000                  |

`max` produces ~2.7x the reasoning of `high`. The override's explicit `max`
is even ~20% deeper than the near-max server default. So the user IS getting
the deepest reasoning GLM-5.2 offers. (Earlier single-run numbers of ~293/~303
were noise from an easy prompt — see skill Section 8. Do not quote them.)

### Verifying it yourself

```bash
# 1. Confirm the override is the live registered profile:
python3 -c "
import sys; sys.path.insert(0, '/home/sinep/.hermes/hermes-agent')
from providers import get_provider_profile as g
print(g('zai').__module__)
"   # -> _hermes_user_provider_zai  (override active)

# 2. Confirm it fires on every call:
grep 'zai-override' ~/.hermes/logs/errors.log | tail -5

# 3. Measure depth across effort levels (run 3x per level for comparisons):
bash ~/.hermes/skills/software-development/agent-operations-handbook/scripts/probe-zai-reasoning.sh
```

## xAI (Grok) — reasoning_effort  (NOT this setup's provider)

Source: https://docs.x.ai/developers/model-capabilities/text/reasoning

Distinct company from Z.AI. Values for grok-4.3 reasoning models:
`none`, `low` (default), `medium`, `high`. There is NO `max`/`xhigh` here.
Don't confuse the two providers' parameter spaces.

## Verification procedure — "is my reasoning level actually taking effect?"

When a user asks whether a reasoning/thinking parameter is actually working,
or challenges a provider-parameter claim:

1. **Identify the provider** (Z.AI is not xAI; check `model.provider` in config).
2. **Check the live docs** — `web_search` for the provider's official docs
   page on the parameter, `web_extract` it, read the authoritative table.
   Do NOT reason from Hermes's internal constants or from memory.
3. **Check the LIVE registered profile, not a file path** (skill Section 7):
   `get_provider_profile(name).__module__` tells you whether the bundled or a
   user-override version is active. Only then inspect/trace that one.
4. **Measure empirically** — the objective signal is
   `usage.completion_tokens_details.reasoning_tokens`. Call the real endpoint
   with the parameter varied (low / high / max), **3+ runs per level on a
   genuinely hard prompt**, and compare medians. Single-run numbers are noise.

The script `scripts/probe-zai-reasoning.sh` automates step 4 for Z.AI.
