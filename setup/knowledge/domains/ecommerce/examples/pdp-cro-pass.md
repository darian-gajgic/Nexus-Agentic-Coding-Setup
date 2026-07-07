> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# Exemplar: PDP CRO Pass — Brewline Gooseneck Kettle (own shop)

PLAYBOOK §3 applied to a real-world-shaped situation: a product page built from the
supplier's import text, converting at 0.8% while the shop average is 2.1% — a
conversion problem by the §2 diagnosis (traffic is fine, page is leaky). No price
change, no ads change: page only. Before is shown as shipped; after is the rewrite.

## Before — the weak PDP (as imported)

```
H1: Gooseneck Kettle Pro X-200 (1.0L)

[Image 1: supplier render, white bg]  [Image 2: supplier render, side view]

$44.99        [ - 1 + ]   [ BUY NOW ]   [ Add to Wishlist ]   [ Compare ]

The Pro X-200 utilizes advanced thermal engineering and precision-flow spout
architecture to deliver a premium pouring experience for the discerning coffee
enthusiast. Crafted from high quality food-grade materials with an ergonomic
handle design philosophy, this kettle represents the perfect fusion of form and
function. Whether you are a seasoned barista or just beginning your specialty
coffee journey, the Pro X-200 elevates every brewing ritual to new heights.
Suitable for a wide range of applications and heat sources. Capacity 1.0L.
Weight 540g. Material stainless steel. Please allow slight measurement error.

[Newsletter popup fires on page load: "JOIN OUR LIST FOR 15% OFF!!!"]

(Footer, three clicks away: shipping policy, returns policy)
(Review app installed — 23 reviews, 4.7 stars — but the widget was never placed)
```

## Diagnosis — the 12 checks, before

| # | Check (PLAYBOOK §3) | Verdict |
|---|---|---|
| 1 | Five-second test: what/who/why this one | FAIL — model-number name, no brand, no reason to choose it |
| 2 | Price + CTA above fold on 390px mobile | FAIL — pushed below the paragraph block |
| 3 | One primary CTA, contrasting verb | FAIL — three competing buttons; "BUY NOW" fights wishlist/compare |
| 4 | Shipping cost + window near CTA | FAIL — footer only |
| 5 | Stars near title; photo reviews on page | FAIL — 23 reviews exist, zero shown |
| 6 | Size/capacity answered before CTA | FAIL — "1.0L" in title but never translated to cups/servings |
| 7 | Gallery ≥5 incl. scale + lifestyle | FAIL — 2 renders |
| 8 | First line = benefit, not spec | FAIL — "utilizes advanced thermal engineering" |
| 9 | Objections section (3–5 real Q&A) | FAIL — none; induction question asked 6× in support tickets |
| 10 | Returns/guarantee visible on page | FAIL — footer only |
| 11 | Sticky add-to-cart on mobile | FAIL |
| 12 | Max one popup, delayed ≥10s | FAIL — fires on load, over the content |

Score: 0/12. Also on the RUBRIC kill list: "high quality" and "premium" with no proof,
wall-of-text block, "!!!", jargon above the fold ("precision-flow spout architecture").

## After — the rewritten PDP

```
H1: Brewline Gooseneck Kettle — 1.0 L Stovetop
Subhead: The slow, steady pour that makes home pour-over taste like the café's.

★ 4.7 (23 reviews)   [anchor-links to review section]

[Gallery — 6 images]
 1 Main: kettle, white bg, 3/4 angle
 2 Scale: in-hand pour over a V60 and mug
 3 Lifestyle: stovetop, morning kitchen
 4 Infographic: 1.0 L = 2 large pour-overs; H 5.9" × W 10.2"; works on
   gas / electric / induction
 5 Close-up: spout tip + flow (the differentiator, in pixels)
 6 UGC frame: customer photo + quote "finally stopped drowning my grounds"

$44.99   In stock
Free shipping over $50 · ships in 1–2 business days, arrives in 3–5
[ ADD TO CART ]              (sticky bar on mobile scroll)
30-day returns · 12-month guarantee · secure checkout   (icon row)

WHY THIS KETTLE
- POUR AT DRIP SPEED, NOT SPLASH SPEED: the 4 mm spout tip holds a thin,
  steady stream — the single biggest fix for bitter, uneven pour-over.
- SIZED FOR TWO CUPS: 1.0 L brews two large pour-overs per boil; 5.9" tall,
  fits under a low faucet to refill.
- EVERY STOVE, INCLUDING INDUCTION: tri-ply base works on gas, electric,
  and induction; handle stays cool on all three.
- BUILT FOR DAILY BOILS: 304 stainless body, one-piece spout weld — no
  coatings to flake, dishwasher safe.
- IN THE BOX + GUARANTEE: kettle, lid with thumb-rest, brew-ratio card.
  12 months: it fails, we replace it — one email.

COMMON QUESTIONS
Q: Does it work on induction?         A: Yes — tri-ply magnetic base, tested on 1800W hobs.
Q: Is 1.0 L enough for guests?        A: Two large mugs per boil; it reboils in ~3 minutes.
Q: Does the handle get hot on gas?    A: No — offset mount keeps it out of the heat path.
Q: Why a gooseneck at all?            A: Flow control. Even extraction needs a slow spiral
                                         pour a standard kettle can't do.

REVIEWS (23) — photo reviews pinned first
[review widget placed here]

GUARANTEE
12-month replacement, 30-day no-questions returns. {{FILL: link to real policy page}}

[Newsletter popup: exit-intent only, "Brew guides + first-order perk", no "!!!"]
```

## The checklist applied, item by item

1. **Five-second test.** Before: a model number. After: brand + product type + size in the H1, and the subhead states the outcome ("café-taste pour-over") — what, who, why-this in two lines. A stranger can now describe the product. This is the same tile principle as marketplaces: clarity before cleverness.
2. **Price + CTA above the fold.** The vendor paragraph moved below the buy block. Nothing a buyer must scroll for decides whether they buy; the fold order is: identity → proof → price → CTA.
3. **One primary CTA.** Wishlist/compare removed (they were exits dressed as features on a single-product decision). One verb, one color reserved for it site-wide.
4. **Shipping near CTA.** The threshold line ("free over $50") does double duty: kills the #1 abandonment surprise AND nudges a second item into the cart (PLAYBOOK §4: threshold set ~1.3× AOV).
5. **Reviews surfaced.** Stars at the top anchor-link to the widget; the 23 reviews existed all along — placement, not acquisition, was the gap. Photo reviews pinned first because they carry the most trust per pixel.
6. **Size answered before CTA.** "1.0 L" became "two large pour-overs per boil" in image 4 AND bullet 2 — units buyers think in. Capacity questions were 4 of the last 20 support tickets; each unanswered one is a silent exit.
7. **Gallery ≥5 with scale + lifestyle.** Two renders became the 7-shot structure from PLAYBOOK §1 (6 used here); every bullet claim now has a matching image. Compressed <200KB each — speed is a CRO input, not an IT chore.
8. **Benefit first line.** "Utilizes advanced thermal engineering" → "The slow, steady pour that makes home pour-over taste like the café's." Specs demote to bullet 2+; mechanisms stay ("4 mm spout tip") because specific beats superlative (RUBRIC D4).
9. **Objections section.** The 4 Q&As are the top support-ticket questions verbatim — induction being #1. Answering them on-page converts the silent majority who never write in.
10. **Returns/guarantee on page.** Icon row under the CTA + a guarantee block with actual terms. An unstated return policy reads as "no returns" to a first-time visitor.
11. **Sticky add-to-cart.** On mobile the CTA follows the scroll; the reader who got convinced at the Q&A section doesn't have to scroll back up to act.
12. **Popup tamed.** Load-time popup → exit-intent, one per session, no shouting. The 15% blanket bribe became "brew guides + first-order perk" — value-add framing per PLAYBOOK §4 discount psychology.

What we did NOT do: touch the price. Diagnosis said conversion problem; discounting to
fix a page problem is junior mistake #2 and just spends margin on the same leak.

## Measurement

Log the change (date, page, "full CRO pass", before-CVR 0.8%) in {{FILL: change-log location}}.
Re-read at 14 days or 100 sessions, whichever is later (PLAYBOOK §2 step 6). This was a
bundled fix — acceptable here because the page failed 12/12 (a rebuild, not a test).
Once CVR stabilizes, future changes go back to one-lever-at-a-time.

## Why this works

- The rewrite adds almost no new information — the reviews, the induction answer, the
  capacity all existed. CRO here = moving proof to where the decision happens. Most weak
  PDPs are placement problems, not copy problems.
- Every fix maps to a named check, so the work is reviewable by a junior or an agent
  without taste: 0/12 → 12/12 is a fact, not an opinion.
- The bullets reuse the marketplace bullet-job order (PLAYBOOK §1) — one skill, two channels.
- Support tickets and reviews supplied the objections (principle 7); nothing was invented.

## Adapt this

- {{FILL: your product + real support-ticket questions}} — the Q&A block must come from
  YOUR tickets/reviews, minimum 90 days of them.
- {{FILL: shipping promise}} — the exact threshold, days, and regions we can actually honor
  (BUSINESS-CONTEXT.md); never copy this exemplar's numbers.
- {{FILL: guarantee terms + policy links}} — legal text per our real policies.
- {{FILL: shop CVR baseline}} — "0.8% vs 2.1%" is the shape of the diagnosis; use our
  channel baselines from PLAYBOOK §2.
- Keep: the fold order (identity → proof → price → CTA), the 12-check pass structure,
  the rule that a 12/12-fail page gets rebuilt in one move but healthy pages get
  one-lever tests.
