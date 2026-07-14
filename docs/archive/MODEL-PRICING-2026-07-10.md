# Model Pricing Reference — verified 2026-07-10

Verified against official sources on 2026-07-10: [Anthropic pricing docs](https://platform.claude.com/docs/en/about-claude/pricing) and [Z.AI pricing docs](https://docs.z.ai/guides/overview/pricing). All prices **USD per 1M tokens**.

These are the three models in our stack (see `~/knowledge/WORKFLOW.md`): GLM-5.2 for bulk implementation/drafting (Hermes), Opus 4.8 and Fable 5 on the frontier side for specs, reviews, judging, and hard decisions.

## GLM-5.2 (Z.AI official API)

| | Price |
|---|---|
| Input | **$1.40** (flat — no long-context surcharge, full 1M window) |
| Cache writes / storage | **Free** (limited-time promotion) |
| Cache hits | **$0.26** |
| Output | **$4.40** |

Notes:
- Lower figures seen on aggregator sites ($0.68–$0.93 in / $2.16 out / $0.13 cache) are **third-party hosts**, not Z.AI. DeepInfra is cheapest at ~$0.93 input; OpenRouter showed a temporary 62%-off promo (~$0.53 / $1.67).
- Our GLM coding-plan subscription (Hermes) is **not** metered at these rates — they apply only to pay-as-you-go API keys.

## Claude Opus 4.8 (`claude-opus-4-8`)

| | Price |
|---|---|
| Input | **$5** |
| Cache writes | **$6.25** (5-min TTL) / **$10** (1-hour TTL) |
| Cache hits & refreshes | **$0.50** |
| Output | **$25** |
| Batch API (50% off) | $2.50 in / $12.50 out |
| Fast mode (research preview) | $10 in / $50 out |

## Claude Fable 5 (`claude-fable-5`)

| | Price |
|---|---|
| Input | **$10** |
| Cache writes | **$12.50** (5-min TTL) / **$20** (1-hour TTL) |
| Cache hits & refreshes | **$1** |
| Output | **$50** |
| Batch API (50% off) | $5 in / $25 out |

## Rules of thumb

- **Anthropic cache multipliers** (all models): writes = 1.25× input (5-min TTL) or 2× (1-hour TTL); reads = 0.1× input. 5-min cache pays off after one read; 1-hour after two.
- **Cost ladder per 1M output tokens**: GLM-5.2 $4.40 → Opus 4.8 $25 (~5.7×) → Fable 5 $50 (~11.4×).
- Both Opus 4.8 and Fable 5 include the **full 1M context window at standard pricing** (no long-context premium).
- Fable 5 / Opus 4.7+ / Sonnet 5 use a newer tokenizer (~30% more tokens for the same text than Sonnet 4.6 and earlier) — factor this in when comparing per-token prices across generations.
- US-only inference (`inference_geo: "us"`) adds a 1.1× multiplier on all Anthropic token categories.

## Sources

- [Anthropic pricing docs](https://platform.claude.com/docs/en/about-claude/pricing)
- [Z.AI pricing docs](https://docs.z.ai/guides/overview/pricing)
- [OpenRouter — GLM-5.2](https://openrouter.ai/z-ai/glm-5.2)
- [Artificial Analysis — GLM-5.2 providers](https://artificialanalysis.ai/models/glm-5-2/providers)
- [DeepInfra — GLM-5.2 pricing comparison](https://deepinfra.com/blog/glm-5-2-pricing-benchmarks-cost-comparison)
