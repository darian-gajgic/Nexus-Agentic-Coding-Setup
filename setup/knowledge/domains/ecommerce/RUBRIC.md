# E-commerce Rubric

Quality gate for listings, PDPs, promos, and lifecycle emails. Score BEFORE delivering.
Rule: **all must-pass gates green AND total score ≥ {{FILL: publish threshold, default 22}}/28 AND no dimension ≤ 1** — otherwise revise, don't publish.
Every check below is verifiable without taste: count, measure, or find the pattern.

## How to score — procedure (agents: follow exactly)

1. Identify the artifact type: marketplace listing (L), own-shop PDP (P), promo plan (PR), lifecycle email (E).
2. Run the must-pass gates that apply to the type (table below). A non-applicable gate counts as pass.
3. If any applicable gate fails: stop scoring, fix, restart from step 2. Gates are binary — no partial credit.
4. Sweep the kill list top to bottom; fix every hit before scoring dimensions.
5. Score D1–D7 against the 2/4 anchors. A 3 = clearly past the 2 anchor but missing part of the 4. A 1 = attempted but below the 2 anchor.
6. Emit the scoring block (format at the bottom) and apply the publish rule above.

Gate applicability by artifact type:

| Gate | L | P | PR | E |
|---|---|---|---|---|
| G1 front-load | title | H1 + title tag | hero headline | subject: concrete reason, first 40 chars carry it |
| G2 clean title | yes | yes | yes | yes (subject) |
| G3 claims | yes | yes | yes | yes |
| G4 fit info | yes | yes | n/a | n/a |
| G5 margin floor | yes | yes | yes + attach PLAYBOOK §4 math | only if it contains a discount |
| G6 main image | yes | gallery image 1 | hero asset | n/a |
| G7 required fields | yes | n/a | n/a | n/a |
| G8 backend keywords | yes | n/a | n/a | n/a |
| G9 shipping/returns | n/a | yes | landing page | n/a |
| G10–G12 | yes | yes | yes | yes |

## Must-pass gates — do not publish if ANY fails

- [ ] **G1 Title front-loads product, not fluff:** the primary search keyword appears within the first 80 characters, and those 80 characters alone accurately describe the product.
- [ ] **G2 Title is clean:** no promo words (sale, free, hot, deal, #1, best seller), no ALL-CAPS words (brand acronyms exempt), no emojis, no symbols beyond `- , | ( )`.
- [ ] **G3 No policy-violating or unverifiable claims:** no medical/cure claims, no certifications we don't hold, no "FDA approved"/"eco-friendly"/"non-toxic" without documentation, no competitor names in copy or backend keywords. Every factual claim traceable to the spec sheet or BUSINESS-CONTEXT.md.
- [ ] **G4 Fit info present where the category needs it:** apparel, cases/parts/accessories, furniture/wall items, consumables → exact dimensions / size chart / compatibility list / count appears in the bullets or above the CTA, not only buried in the description.
- [ ] **G5 Margin floor holds:** contribution margin after ALL fees ≥ {{FILL: CM floor, default 25%}} at the listed price; any promo price stays above breakeven. (Unit-economics table from PLAYBOOK §4 attached to the deliverable.)
- [ ] **G6 Main image compliant:** plain/white background, no overlay text or watermark, product ≥85% of frame (marketplace spec — verify current).
- [ ] **G7 Zero empty required fields:** all category attributes / item specifics filled; Etsy = 13/13 tags.
- [ ] **G8 Backend keywords:** no competitor brands, no word repeated from title/bullets, within the byte/tag limit.
- [ ] **G9 Own-shop PDP only:** shipping cost + delivery window AND returns/guarantee visible on the page itself.
- [ ] **G10 Zero spelling/grammar errors** in title and bullets (run a checker; don't eyeball).
- [ ] **G11 No placeholders left:** no `{{FILL`, "lorem", "TBD", "[brand]", "XX" anywhere in the artifact.
- [ ] **G12 Voice compliance:** contains none of the banned words/phrases listed in STYLE-VOICE.md.

## Scored dimensions — 0–4 each (0 absent, 2 competent, 4 excellent)

**D1. Search coverage**
- 2 = primary keyword placed correctly; a few secondary terms present; backend/tags partially used.
- 4 = primary + 3–5 secondary terms integrated readably; backend/tags filled to the limit with zero duplication of title/bullet words; synonyms, misspellings, and adjacent-use terms covered.

**D2. Objection coverage**
- 2 = features listed and accurate, but objections only implicitly addressed.
- 4 = the top 3 objections found in review mining are each explicitly answered in a bullet, image, or Q&A block — traceable back to the mined phrases.

**D3. Skimmability**
- 2 = readable, but at least one paragraph >3 lines or bullets without lead hooks.
- 4 = every element parses in a 5-second skim: 2–4 word capitalized bullet hooks, no paragraph >3 lines, specs in a list/table, key facts also present on images.

**D4. Specificity and proof**
- 2 = some numbers and materials named; some claims still bare ("durable", "premium").
- 4 = every quality claim carries a number, material, mechanism, or test ("holds 40 lb", "304 stainless", "keeps 140°F for 60 min") — zero bare adjectives.

**D5. Image/media plan**
- 2 = main image compliant plus 2–4 supporting shots.
- 4 = full 7-shot plan (main, scale, lifestyle, spec infographic, close-up, in-box, social proof) and every major copy claim is visualized in at least one image.

**D6. Channel mechanics** (per artifact type: L = category/variations/A+ plan correct; P = PLAYBOOK §3's 12 CRO checks; PR = goal + unit economics + required-lift math + enforced end date; E = one job, one CTA, send trigger + suppression segment defined)
- 2 = at least two-thirds of the type's checklist items pass.
- 4 = every item on the type's checklist passes, verifiably.

**D7. Voice and differentiation**
- 2 = clean and generic — could be any brand's listing; no STYLE-VOICE.md violations.
- 4 = matches STYLE-VOICE.md patterns; contains at least one differentiator claim no page-1 competitor makes; zero sentences that appear verbatim in competitor listings (spot-check 2 sentences via search).

## Kill list — automatic amateur markers (each found = fix before scoring)

- Keyword-stuffed title (same root word 3+ times, or comma-chained keyword list as title).
- "High quality", "premium", "best", "amazing" without an attached number/material/mechanism.
- Wall-of-text description: any block over 5 lines with no break, list, or header.
- ALL-CAPS sentences or multiple exclamation marks anywhere.
- "Perfect gift for..." as bullet 1 (gift angle belongs in tags/late bullets unless the product IS a gift product).
- Bullet that restates the title instead of doing its assigned job (PLAYBOOK §1 bullet jobs).
- Feature named with no benefit translation anywhere on the page ("double-wall" but never "stays hot").
- Claims of guarantee/warranty with no defined terms behind them.
- Stock/render image as the main photo when a real product photo exists.
- Discount shown without a real 30-day reference price behind it.
- Fake urgency: countdowns that reset, "only 3 left" not tied to real inventory.
- Unexplained jargon in the first bullet or above the fold.
- Emojis in marketplace titles/bullets; emoji-decorated bullet hooks.
- Price ending inconsistent with our catalog convention {{FILL: e.g. .99 or .00}}.

Scoring output format (agents: append this to your deliverable):
`RUBRIC self-score: G1–G12 pass/fail list · D1..D7 scores · total /28 · verdict publish/revise`
