# Rendered image assets — worked example & patterns

Reference for the `rendered-image-assets` skill. Session: apple-juice Instagram ad
(task-866aa4d8, 2026-07-06). The full deliverable lives at
`~/nexus-agent-os/workspaces/task-866aa4d8/` — this file distills the reusable parts.

## The deliverable shape (what to ship)

A workspace folder containing:

- `apple_juice_instagram_ad.png` — the 1080×1080 (2× rendered → 2160²) asset.
- `ad.html` — self-contained source (inline CSS, inline SVG hero, Google Fonts via `<link>`).
- `render.py` — the Playwright render script (device_scale_factor=2, `document.fonts.ready`).
- `deliverable.md` — image embed + caption + claims-and-sources table + operator to-dos + rubric self-score.

Ship all four. The HTML + script is a one-line rerender for the operator.

## HTML body discipline for fixed-size assets

```html
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { width:1080px; height:1080px; overflow:hidden; }
  body { font-family:'Inter',sans-serif; background: radial-gradient(...); color:#2B2118; position:relative; }
  .canvas { position:absolute; inset:0; }
  .text-col { position:absolute; left:72px; top:186px; width:512px; z-index:3; }
  /* ... */
</style>
```

- Pin `html,body` to the logical target size and `overflow:hidden` so nothing leaks.
- Position hero elements absolutely within `.canvas` at exact px coordinates — this is a poster, not a flow document. Grid/flexbox are fine for sub-layouts but the top level is absolute positioning against a known canvas.
- Inline the SVG hero illustration directly in the HTML (no external `.svg` file) for portability.
- Webfonts via `<link href="https://fonts.googleapis.com/css2?family=Fraunces...&family=Inter...">`.

## SVG hero illustration (zero-licensing-risk appetizing food imagery)

The apple-juice glass was ~150 lines of inline SVG using only primitives:

- `<linearGradient>` / `<radialGradient>` for juice amber, glass tint, apple red, flesh, leaf.
- `<clipPath>` to contain the juice fill inside the glass outline.
- `<filter id="soft"><feGaussianBlur stdDeviation="10"/></filter>` for contact shadows under the glass and apple.
- Layered `<ellipse>` for condensation droplets (varied opacity 0.4–0.65) and cloudy particulate blotches inside the juice.
- `<path>` with specular highlights for the apple.

This produces an appetizing, on-brand food/beverage hero with no image-gen tool and no
stock library. Recolorable by editing gradient stop hexes. The pattern generalizes to
any product silhouette where a photo isn't available or isn't worth the licensing risk.

## Caption pattern (compliance-gated)

```
[Hook ≤ 125 chars — leads with the strongest defensible benefit angle]

[3–5 line body expanding the benefit story, each line a truthful bullet]

[Portion / moderation context — never hide sugar/acidity]

[Single CTA — e.g. "Find a bottle near you — link in bio."]

[#hashtags 8–10, mix of category + benefit + brand]
```

Checks before shipping the caption:
- Hook ≤ 125 chars (Instagram truncation cutoff).
- Exactly one CTA.
- Zero or one exclamation mark across image + caption combined.
- Every health/benefit phrase traceable to the claims table.
- Moderation/sugar context present and visible (not buried).

## Claims-and-sources table (the compliance core)

Every health/benefit claim on the image or in the caption gets a row:

| # | Claim as it appears | Claim type | Source backing it | Status / action |
|---|---|---|---|---|
| 1 | "Richer in Antioxidants." | Structure-function | Candrawinata 2014; Vallée Marcotte 2022 — cloudy retains 2.5× polyphenols vs clear | ✅ Safe |
| 7 | "Contains vitamin C" | Nutrient content (soft) | USDA — natural ~2mg / ~2–3% DV per 8oz | ⚠️ Hedged — too low for "source of" in EU/DACH; do NOT say "supports immunity" |

Claim types to label: factual / product-definition, nutrition fact, structure-function,
nutrient-content (soft vs "source of"/"excellent source of" — these have legal thresholds),
dietary-guidance, hedged. Status marks: ✅ Safe, ⚠️ Hedged/conditional, ❌ Never.

Include an explicit "Hard rules respected" checklist: no prevent/treat/cure disease;
no "lowers cholesterol" / "boosts immunity" / "detox" / "superfood"; no borrowing
whole-food evidence for a juice product; sugar never hidden.

## Operator to-dos (market-specific things the agent can't sign off)

Flag, don't silently decide:
- Brand + logo replacement (placeholder → real mark, then rerender).
- EU/DACH nutrient-content claim thresholds ("source of vitamin C" needs ≥15% DV).
- EFSA polyphenol health-claim rejections — run exact phrasing past local regulatory review before paid boosting.
- UTMs / landing page wiring before any paid spend (out of scope for the creative asset itself, required before boosting).

## Ad-hoc verification script pattern

No canonical test command for an image asset. Run focused checks, label them ad-hoc:

```python
# 1. PNG valid + exact aspect
from PIL import Image
im = Image.open(png); im.verify(); im = Image.open(png)
assert im.format == "PNG" and abs(im.size[0]/im.size[1] - 1.0) < 0.001 and im.size[0] >= 1080

# 2. HTML balanced structural tags
for t in ["html","head","body","style","svg","defs"]:
    assert html.count(f"<{t}") == html.count(f"</{t}>")

# 3. render script compiles
import py_compile; py_compile.compile(render_py, doraise=True)

# 4. on-image copy present verbatim (catches copy-doc drift)
for s in ["Naturally Cloudy.", "no added sugar", ...]:
    assert s.lower() in html.lower()

# 5. kill-list sweep — SCOPE TO FACING TEXT ONLY (see pitfall in SKILL.md)
facing = (on_image_text_nodes + caption_block).lower()
for term in KILL_LIST:
    assert term not in facing
```

**The scoping pitfall (load-bearing):** check #5 must extract only the user-facing
text — on-image copy from HTML text nodes (strip `<style>`, `<svg>`, tags) plus the
caption block from the deliverable. Sweeping the WHOLE deliverable file produces ~100%
false positives because the compliance section correctly lists the banned terms as
things-to-avoid. A real run failed 2/8 from this, then passed 8/8 once scoped to facing
text only. Never sweep compliance documentation for banned words.
