---
name: rendered-image-assets
description: "Produce fixed-dimension image-file deliverables (Instagram/Facebook ads, social preview/OG cards, story cards, posters, thumbnails) by composing a self-contained HTML/CSS/SVG file and screenshotting it at exact pixel dimensions with a headless browser. Use when the PNG/JPG is the deliverable, not an openable web page. Covers the Playwright render recipe, the font-load/device-scale details that cause blurry or fallback-font output, self-contained SVG hero illustration for zero-licensing-risk brand work, logo-zone placeholders, and visual QA on the rendered file. Do NOT use for interactive prototypes (use claude-design), faithful redraw of an existing screenshot (use image-analysis-and-redraw), or photoreal imagery a diffusion model does better."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [design, html, image, social, ads, marketing, playwright, svg, creative, artifact]
    category: creative
    related_skills: [claude-design, popular-web-designs, image-analysis-and-redraw, content-repurposing]
---

# Rendered image assets (HTML/CSS/SVG → PNG at exact pixel dims)

The deliverable here is a **fixed-dimension image file** the user posts or embeds —
an Instagram/Facebook ad (1080×1080, 1080×1350), an Open Graph / social preview card
(1200×630), a story card (1080×1920), a poster, a thumbnail, a hero card. In a
CLI/API environment the cleanest, highest-fidelity path is to **compose the design as
a single self-contained HTML file (HTML + CSS + inline SVG) and screenshot it at exact
pixel dimensions with a headless browser.** You get typographic control, crisp vector
artwork, and an editable source — none of which a diffusion model can match for
text-heavy or brand-precise layouts.

This is the sibling of `claude-design` (which produces an openable HTML artifact the
user interacts with) and the inverse of `image-analysis-and-redraw` (which
reconstructs an *existing* image). Here you author the source and render the pixels.

## When to use / when not to

Use when:
- Fixed-dimension social / marketing image assets (ads, story cards, carousels, preview cards).
- Posters, flyers, thumbnails where text + brand precision matters more than photographic realism.
- Any "the PNG/JPG is the deliverable, not the page" request.
- Compliance-sensitive / health / regulated-category ads where stock-photo licensing or model releases are a risk the user didn't ask for.

Do NOT use for:
- **Interactive artifacts or multi-state prototypes** — those stay as openable HTML (use `claude-design`).
- **Faithful redraw of an existing screenshot/photo** — use `image-analysis-and-redraw` (PIL pixel-compositing tier).
- **Photoreal hero imagery** a diffusion model does better — generate that and composite it in, or drop in a user-supplied photo.
- **Authoring a design-token spec file** — use `design-md`.

Composes well with: `popular-web-designs` (steal a known brand's colors/type as the
visual vocabulary), `content-repurposing` (the caption that pairs with the image),
and the marketing/content/brand playbooks under `~/knowledge/domains/`.

## The render recipe (Playwright, Chromium)

Write the HTML at the **logical** target size (e.g. `width:1080px; height:1080px` on
`<body>`, `overflow:hidden`), then render headless:

```python
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

HTML = (Path("ad.html")).resolve().as_uri()
OUT = Path("ad.png")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 1080, "height": 1080},
            device_scale_factor=2,          # 2× → 2160×2160, crisp on retina / zoom / print
        )
        page = await ctx.new_page()
        await page.goto(HTML, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")  # webfonts MUST be loaded before screenshot
        await page.wait_for_timeout(500)             # let layout + font paint settle
        await page.screenshot(
            path=str(OUT),
            clip={"x": 0, "y": 0, "width": 1080, "height": 1080},
            type="png",
        )
        await browser.close()

asyncio.run(main())
```

### The three load-bearing details (learned by doing each wrong first)

1. **`device_scale_factor=2`** — without it the PNG is blurry on retina and when the user zooms. Logical 1080 → 2160×2160 source; it is still a 1080×1080 asset to Instagram.
2. **`document.fonts.ready` before the screenshot** — `networkidle` fires when the network settles, but webfonts (Google Fonts) paint a frame later. Skip this and you screenshot fallback-system-font text that reflows once the real font lands. Symptom: the rendered text looks fine to you but the user sees a different typeface.
3. **`wait_until="networkidle"` + a short settle timeout** — not `domcontentloaded`; the SVG gradients / clip-paths / fonts need a paint cycle to land.

### Ship the editable source, not just the PNG

Always deliver **both** the PNG and the editable source (`ad.html` + `render.py`, or
equivalent). Operators almost always want to swap a logo, tweak copy, or restyle — a
black-box PNG forces a full redo, while the HTML + script is a one-line rerender:
`.venv/bin/python render.py`. Keep the HTML self-contained (inline CSS, inline SVG,
webfonts via `<link>` to Google Fonts or system fonts) so it rerenders identically
anywhere.

## Self-contained SVG illustration = zero licensing risk

For health / food / regulated-category ads especially, pulling a stock photo
introduces licensing + model-release risk the user may not have signed up for. A
**hand-authored inline SVG illustration** (a glass of juice, a product silhouette, an
abstract motif) has none of that, renders razor-crisp at any scale, and is trivially
recolorable. Reach for it by default for ad hero imagery; only drop in a raster photo
when the user supplies one or explicitly asks for photographic realism.

SVG `<linearGradient>` / `<radialGradient>`, `<clipPath>`, `<filter>` (Gaussian blur
for contact shadows), and layered `<ellipse>` / `<path>` produce surprisingly
appetizing results — condensation droplets on glass, fruit with specular highlights,
soft window light — at zero marginal cost. This is the technique that lets a CLI/API
agent produce an "appetizing" food/beverage ad with no image-gen tool and no asset
library.

If the SVG gets large, keep it inline anyway (portability beats tidiness for a
one-shot artifact) — or split into a `.svg` file loaded via `<img>`.

## Logo zones and operator placeholders

Reserve explicit negative space for the brand mark (a bottom-right zone is conventional)
and put a clearly-marked placeholder there — italic, soft-accent-color "your brand" text
works well. State in the deliverable that the operator must replace it. Do NOT silently
ship a fake logo: that is invented content, and on a compliance-gated ad it can read as
a fabricated brand. The placeholder signals "edit me" rather than pretending to be final.

## Visual QA on the rendered PNG

Always look at the rendered file before declaring done. Claiming "image looks good"
without inspecting it is the same failure mode as claiming code works without running it.

### Local small-VLM regime (Ollama qwen3-vl, ~4096 context)

A 2160² PNG will blow the context window (`exceed_context_size_error`). **Downscale a
JPEG preview** and run vision on that:

```python
from PIL import Image
Image.open("ad.png").convert("RGB").resize((540,540), Image.LANCZOS).save("preview.jpg", quality=88)
```

The model reads layout, legibility, and composition fine at 540px; it only needs full
resolution for reading small text or exact values (use OCR / `image-analysis-and-redraw`
for that). Verify crispness separately with `PIL.Image.open` dimensions + aspect check.

Ask the vision model **concrete yes/no questions** (is the headline legible? is there
clear logo space? any overlap or cut-off? does the hero read as intended?), not open-ended
"is this good?" — concrete questions get reliable answers.

## Ad-hoc verification (not suite-green)

No canonical test/lint/build command exists for a designed image asset. Run focused
artifact checks and label them **ad-hoc verification, not suite-green**:

- PNG opens (`PIL.Image.open` + `.verify()`) and is exact target aspect (1:1 etc.) + ≥ target width.
- HTML structural tags balanced (`html`/`head`/`body`/`style`/`svg`/`defs`).
- The render script compiles (`py_compile`).
- On-image copy strings from the copy doc are present **verbatim** in the HTML (catches copy-doc drift — a headline typo between the written spec and the rendered artifact).
- Every cross-referenced file in the deliverable resolves.
- Kill-list / forbidden-claim sweep — **scoped to ad-FACING text only** (see pitfall).

The full worked example (apple-juice Instagram ad, including the compliance-claims
table pattern) is in `references/rendered-image-assets.md`. For regulated-category
(nicotine/alcohol/pharma) typography-only ads, see
`references/regulated-category-ads.md` — covers stat-as-hero layout, hashtag
include/exclude strategy, platform ad-review prep, and a caption reading-level script.

## Compliance-gated marketing ads (extra discipline)

When the asset carries health, financial, or income claims, or anything a regulator
could read as a disease/medical claim:

- **Read the predecessor research brief** (or produce one) and use only the angles it backs. Never invent benefits. Every on-image and in-caption claim must trace to a source.
- **Build a claims-and-sources table** in the deliverable: each claim as it appears → claim type (factual / structure-function / nutrient-content / hedged) → the source backing it → compliance status + operator action. This is what lets the user (or their legal) verify before posting.
- **Reserve explicit operator to-dos** for anything market-specific: e.g. EU/DACH "source of vitamin C" is illegal below 15% DV; EFSA has rejected several polyphenol health-claim petitions. The agent can't sign off locally — flag it.
- Run the final facing copy through `claim-verification` or the domain RUBRIC's kill-list; gate the deliverable through `frontier-judge` (`cjudge <file> <domain>`) before any paid boost.

## Regulated-category ads (nicotine, alcohol, pharma, cannabis) — typography-only by default

For nicotine/vaping, alcohol, prescription drug, or cannabis ads, **skip the SVG hero
illustration entirely** and use a **pure-typography layout**. Product imagery (even
abstract silhouettes) can read as promotion in these categories — the safer default is
a giant stat or number as the visual anchor, with all messaging carried by type
hierarchy. This pattern was validated on a vaping harm-reduction Instagram ad
(1080×1080) and passed platform review expectations.

### Typography-only ad anatomy

- **Giant accent-color number/stat** (300px / weight 900) as the single biggest element — this IS the hero. No illustration.
- **Eyebrow audience pill** at top (e.g. "21+ ADULT SMOKERS") — sets the audience scope immediately, before the viewer reads anything else.
- **Proof line** under the headline citing the source study by name and scope ("104 studies · 30,000+ people · Cochrane 2025").
- **Harm acknowledgment + dual-use warning** if applicable ("Switch completely. Smoking and vaping together may be worse than smoking alone").
- **CTA to a public health service**, not a commercial entity or store ("Talk to your local stop-smoking service" — not "Shop now").
- **Disclaimer microcopy** at the bottom (risks disclosed, long-term effects unknown, audience restriction restated).
- **Logo placeholder** bottom-right ([BRAND] in dashed border) — never a fake logo.

### Hashtag strategy for regulated categories

Deliberately **exclude** lifestyle/youth-coded hashtags. For vaping/nicotine:

**Include:** `#smokingcessation #quitsmoking #harmreduction #stopsmoking #publichealth #smokefree #cessation #evidencebased` — smoker/cessation/policy-coded tags that reach the right audience without lifestyle framing.

**Exclude by design:** `#vape #vaping #vapelife #vapenation #ecig #vapecommunity` — youth-lifestyle coded, these both flag platform review AND invert the harm-reduction framing (they say "vaping is a lifestyle" when the ad says "vaping is a quitting tool with risks").

The exclusion principle generalizes: in any regulated category, lifestyle/identity
hashtags are both a compliance risk and a message-inversion risk.

### Platform ad-review documentation

Include a "Posting Notes" section in `deliverable.md` covering:

- **Audience restriction setup** on the platform (Meta: age 21+ minimum, cessation-interest targeting only, exclude vape/ecig interest audiences).
- **Expected review flags** and why the ad should pass (no product image, no brand, no retailer link, no purchase CTA, public-health CTA, cessation framing, peer-reviewed evidence).
- **Appeal strategy** if rejected (prepare a review-note submission stating the ad's public-health/cessation purpose with citations).
- **Landing page check** (CTA must resolve to a real public health resource — NHS, CDC, state quitline — not a commercial store).

This is distinct from the claims-and-sources table: the claims table protects against
regulatory/legal risk; the platform-review section protects against the ad being
rejected before it can run at all.

### Caption reading-level check

For public health ads, run a Flesch-Kincaid grade check on the caption (target Grade
7–8). Also verify: word count 95–135, hook ≤ 125 chars, exactly 1 CTA, 0 exclamation
marks, and a you/we ratio favoring "you" (the reader) over "we" (the brand). See
`references/regulated-category-ads.md` for a ready-to-run script.

## Pitfalls

- **Scoping kill-list / forbidden-claim sweeps to ad-FACING text only.** On any compliance-gated marketing deliverable, a naive grep for banned phrases ("detox", "superfood", "lowers cholesterol") across the whole deliverable file produces ~100% false positives — because the compliance section *correctly* lists those terms as things-to-avoid. Extract only the user-facing text (on-image copy from HTML text nodes + the caption block) and sweep THAT; never the compliance documentation. A real session shipped 2/8 FAIL from this, then 8/8 PASS once scoped correctly.
- **Screenshotting before webfonts load.** `networkidle` ≠ fonts painted. Always `await document.fonts.ready` + a short settle before the screenshot, or the PNG ships with fallback-font text.
- **Shipping a PNG without its editable source.** The operator will want to swap the logo or tweak copy; a black-box PNG forces a full redo. Always ship HTML + render script alongside.
- **`device_scale_factor=1`.** Produces a blurry asset on retina. Default to 2 unless the target platform specifically downsamples.
- **Fake logos / fabricated stats on the image.** Invented content is worse than a clearly-marked placeholder. Use "your brand"-style placeholders and cite every figure.
- **Calling the render "verified" from fluent vision prose alone.** A VLM that writes a confident description may be confabulating. Ask concrete yes/no questions and, for any text/value, confirm via dimensions/OCR rather than trusting the prose.
