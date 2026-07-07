# E-commerce Playbook

Senior operating procedure for marketplace listings and the own shop.
Before any task: read `~/knowledge/BUSINESS-CONTEXT.md` (what we sell, margins, channels) and
`~/knowledge/STYLE-VOICE.md` (how we sound). After any task: self-score against
`~/knowledge/domains/ecommerce/RUBRIC.md`, fix every must-pass failure, end with a `Learn:` section (max 3 bullets).
Platform-agnostic first; Amazon/Etsy/eBay/Shopify notes only where mechanics genuinely differ.

## Operating principles

1. **Diagnose before you touch: traffic and conversion problems have opposite fixes.** A title rewrite to fix a conversion problem burns months of earned ranking for zero gain.
2. **The tile sells the click; the page sells the unit.** Main image + first 80 title chars + price + stars decide whether anything else you wrote is ever seen — budget effort in that order.
3. **Velocity is the algorithm's love language.** Rank follows recent conversion velocity, so never edit a listing that is climbing, and never let a bestseller stock out.
4. **Margin is made at sourcing and pricing; a promo can only spend it.** Know contribution margin per unit after ALL fees before touching any price.
5. **One lever, 14 days, written down.** Overlapping changes mean zero attribution, which means permanent guessing.
6. **Reviews compound; ads decay.** The first 15 reviews move conversion more than any campaign, and they keep working after you stop paying.
7. **Customers write your best copy in their reviews.** Buyers convert on their own words — mine your and competitors' reviews for exact phrases before writing anything.
8. **Every element answers an objection or it goes.** Buyers don't read, they interrogate; a feature that removes no doubt is noise.
9. **Account health outranks any single sale.** Marketplace suspension is existential — no tactic that bends policy is ever worth it.
10. **Out of stock = out of rank.** Stockouts reset velocity and recovery takes weeks; reorder at {{FILL: weeks-of-cover threshold, default 6}} weeks cover, don't celebrate selling out.

## Task playbooks

### 1. Product listing creation

**Keyword harvest (do this before writing a word):**
1. Type the seed term into the marketplace search bar; record autocomplete suggestions (also try seed + " a", " b", ... for depth). Cap: 15 minutes.
2. Copy the titles of the top 10 organic results for the main term into a sheet.
3. Read 20+ reviews across 3 competitors; capture exact buyer phrases: what they call it, what they use it for, what they complain about.
4. Add search-term report data if we run ads on this category.
5. Output a keyword sheet: term / source / role. Roles: **primary** (exactly 1 — the highest-volume term that PRECISELY describes the product; precision beats volume, because ranking on a mismatched head term brings clicks that don't convert and tanks rank), **secondary** (3–5), **long-tail** (rest).

**Title — formula:**
```
[Brand] [Primary Keyword Phrase] [Size/Count] – [Attribute 1], [Attribute 2] – [Use case or audience]
```
1. First 80 characters must describe the product completely on their own (mobile truncation).
2. Primary keyword phrase within the first 5–7 words.
3. Banned in titles: promo words (sale, free, hot, #1), ALL-CAPS words, emojis, subjective claims ("best"), symbols beyond `- , | ( )`.
4. Read-aloud test: a human must be able to say it without stumbling.
- Amazon: category style guide governs; cap ~150–200 chars by category (verify current). Title Case.
- Etsy: 140-char cap; the first ~40 carry most search and display weight; write buyer-language phrases (occasion, recipient, style), not spec strings.
- eBay: 80-char cap; every word is a search term — no filler; item specifics do the filtering work.
- Shopify: the title becomes the Google title tag — product type + differentiator in ~60 chars; human-readable beats keyword lists.

**Bullets — 5 bullets, each with an assigned job (in this order):**
1. Primary benefit + differentiator: why this one over page-1 rivals. Include a number.
2. Fit: size / dimensions / compatibility / quantity. This bullet prevents wrong-buyer returns.
3. Quality proof: material, construction, certification, test result — mechanisms, not adjectives.
4. Use cases: 2–3 concrete scenarios so the buyer can picture ownership.
5. Risk reversal: what's in the box, care instructions, guarantee.
Format each: 2–4 word capitalized hook, colon, then 1–2 sentences. Target ≤200 chars (Amazon caps ~250 — verify).

**Description — 4 blocks, no paragraph over 3 lines:**
1. Hook: the buyer's situation or frustration (use review language).
2. How the product resolves it — the one big differentiator, expanded.
3. Specifics: specs list or table (dimensions, materials, counts).
4. What's in the box + guarantee + care.
- Amazon: if brand-registered, A+ content replaces this (banner, icon trio, comparison table); keep a plain-text fallback. HTML support is deprecated (verify current).
- Shopify: use headed sections and collapsible specs; this page also serves Google — write real sentences.

**Backend / search keywords:**
1. Take keyword-sheet terms NOT already used in title or bullets (indexed once is enough; duplicates waste the budget).
2. Add: synonyms, regional and foreign-language terms, common misspellings, adjacent uses.
3. Exclude: competitor brand names (policy violation), subjective words, temporary words ("new", "2026").
4. Amazon: fill toward the byte cap (~250 bytes — verify), space-separated, no commas needed, singular OR plural not both.
5. Etsy: use all 13 tags, multi-word phrases, no tag repeating an exact title phrase; cover what-it-is / material / style / occasion / recipient.

**Attributes / item specifics:** fill EVERY category field. Empty fields = invisible to filtered search (this is most of eBay and Etsy browse traffic).

**Image shot list (order matters — 1 and 2 do the selling):**
1. Main: plain/white background, product ≥85% of frame, no text or props (platform rules — verify).
2. Scale: in-hand or next to a familiar object.
3. Lifestyle: in use, in the buyer's context.
4. Infographic: dimensions and key specs on the image (mobile buyers don't read bullets).
5. Close-up: the quality/differentiator detail.
6. In-the-box / variants group.
7. UGC-style or social-proof frame (review quote over photo — own claims only, keep it honest).

**Pre-publish gate:** RUBRIC.md must-pass all green → voice check vs STYLE-VOICE.md → `Learn:` section → if this is a new-product launch, escalate (see last section).

### 2. Listing optimization loop

1. Pull last 30 days per listing: sessions/views, CTR (if the platform shows impressions), conversion rate, price changes, stock events, review delta. Screenshot before touching anything.
2. Classify the problem:
   - **Traffic problem:** sessions low or declining. On ads dashboards, CTR < ~0.3% = tile problem.
   - **Conversion problem:** Amazon unit-session % < 8% (typical 10–15%, category-dependent — verify); Etsy/own shop CVR < 1% (typical 1–3%). Set our real baselines: {{FILL: per-channel CVR baselines from 90-day account median}}.
   - Both low → fix conversion FIRST (more traffic into a leaky page also trains the algorithm that the listing is bad).
3. Traffic fixes, in order of impact: main image, first 80 title chars, price vs page-1 median, missing attributes/wrong category, then ads.
4. Conversion fixes, in order: images 2–7, bullet 1 vs the top objection found in reviews/Q&A, review count (<10 reviews → run playbook 7 before anything else), price/shipping cost shown, unanswered Q&A.
5. Change ONE lever. Log it: date, listing, lever, before-metric, hypothesis — in {{FILL: change-log location}}.
6. Wait 14 days or 100 sessions, whichever comes LAST.
7. Decide: metric improved >10% relative → keep. Worse by >10% → revert same day. Flat → next lever on the list.
8. Guardrails: never rewrite a title while sales trend up; never test during a promo window or holiday spike; never change two listings' shared element (e.g. brand name) mid-test.

### 3. PDP copy + CRO checklist (own shop)

Write the page in this order: H1 (what it is) → benefit subhead (why it matters) → gallery → price block with shipping line → bullets (same 5 jobs as playbook 1) → objections section → reviews → guarantee. Then run the 12 checks. All 12 are binary — fix every fail before publish.

1. Five-second test: what it is, who it's for, why this one — answerable from above the fold alone.
2. Price AND primary CTA visible without scrolling on a 390px-wide mobile screen.
3. One primary CTA, contrasting color, verb label ("Add to Cart" — never "Submit").
4. Shipping cost + delivery window stated next to the CTA, before cart. (Surprise shipping is the #1 abandonment cause.)
5. Review stars + count next to the title; full reviews with photos lower on the page.
6. Size / compatibility / quantity answered BEFORE the CTA (chart, diagram, or one clear line).
7. Gallery has ≥5 images including scale + lifestyle, zoomable, each <200KB after compression.
8. First line under the H1 is a benefit, not a spec.
9. Objections section present: 3–5 real questions answered (mine them from reviews and support tickets).
10. Returns/guarantee visible on the page itself, not only in the footer.
11. Sticky add-to-cart bar appears on mobile scroll.
12. Max one popup, delayed ≥10s or exit-intent, never covering the CTA.

Worked before/after: `examples/pdp-cro-pass.md`.

### 4. Pricing & promotions

**Unit economics — compute this before any price or promo decision (illustrative numbers):**
```
Sell price                       $29.99
Landed COGS (unit+freight+duty)  -$7.50
Referral fee 15% (verify)        -$4.50
Fulfillment/shipping             -$5.20
Returns allowance 3% of price    -$0.90
Contribution margin (CM)         $11.89  = 39.6%
```
Own shop: replace referral fee with payment processing (~2.9% + $0.30 — verify) and real pick/pack/ship.
- Price floor: CM% never below {{FILL: floor, default 25%}}. Breakeven ad spend: breakeven ACOS = CM% (here ~40%); target ACOS ≤ 25%.

**Promo math — the required-lift rule:**
1. Compute promo-price CM. Example, 20% off: $23.99 price → referral drops to $3.60, returns $0.72 → CM = 23.99 − 7.50 − 3.60 − 5.20 − 0.72 = **$6.97**.
2. Required unit lift = old CM ÷ promo CM = 11.89 ÷ 6.97 = **1.7×**.
3. Run the promo ONLY if (a) past similar promos hit that lift, or (b) you can name a strategic goal worth the margin: rank push, clearance, review velocity, list growth. Write the goal down first.

**Promo calendar logic:**
1. Anchor promos to demand peaks: Q4, marketplace events (Prime Day etc. — verify dates annually), and our category's seasonal peaks {{FILL: category peak months}}. Never promo out of boredom.
2. Own shop: max 1 sitewide event per quarter. Between events, only targeted offers (email segments, bundles, clearance) — invisible to the general public, so the public price stays credible.
3. Strike-through prices require a genuine recent reference price — hold the regular price ≥30 days before showing "was $X" (legal requirement in many markets — verify locally).
4. Check inventory cover 6–8 weeks before a peak; a promo that stocks you out converts rank into a cliff (principle 10).

**Discount psychology without brand damage:**
1. Discount a REASON, not a product: launch week, bundle, newsletter welcome, seasonal event. Reasons expire; naked discounts linger in memory and reset the reference price.
2. Prefer value-add over %-off for premium positioning: free gift, free-shipping threshold (set at ~1.3× current AOV to lift basket size), bundle pricing.
3. Never exceed the discount floor {{FILL: max discount %, default 30%}} without escalation.
4. Never run a predictable rhythm (e.g. monthly sale) — it trains customers to wait.
5. End dates are real: enforce them, no silent extensions. Credibility is a compounding asset.

### 5. Product feed hygiene + shopping ads basics

**Feed hygiene — weekly, 20 minutes:**
1. Merchant Center (or channel equivalent) disapprovals = 0. Fix any within 48h.
2. Price and availability in feed EXACTLY match the PDP (mismatch = disapproval, repeated = suspension).
3. Every SKU: GTIN/MPN where one exists, brand, condition, correct `google_product_category`.
4. Feed titles ≠ marketplace titles: Google matches query to title, so front-load `[Product type] [Brand] [Key attribute] [Size/Color]`. No promo text.
5. Images: no watermarks, no overlay text (disapproval).
6. Custom labels filled: margin band (high/mid/low), bestseller flag, season, clearance — you will segment campaigns by these.

**Shopping ads — starting sequence:**
1. One campaign, all approved SKUs, low daily budget {{FILL: starting budget}}, run 14 days untouched.
2. Then split by custom label: bestsellers/high-margin get their own budget; low-margin gets a low bid or excluded.
3. Cut rule: pause any SKU with clicks > 3× breakeven clicks and 0 orders. Breakeven clicks = CM$ ÷ CPC (e.g. $11.89 CM ÷ $0.80 CPC ≈ 15 clicks → pause at 45).
4. Target ROAS: breakeven ROAS = 1 ÷ CM% (CM 40% → 2.5). Set target ≥ 1.5× breakeven (→ ~4). Below breakeven for 30 days = restructure, don't nudge.

### 6. Lifecycle email

Structure for every email: one job, one CTA, subject line states the concrete reason for the email. Voice per STYLE-VOICE.md.

**Abandoned cart — 3 touches:**
1. +1–4h: "You left this" — product image, one-click back to cart, answer the top objection in one line. NO discount (most carts recover free; instant coupons train discount-waiting).
2. +24h: objection handling — 2 review quotes, shipping/returns reassurance, guarantee.
3. +48–72h: scarcity if TRUE (stock level), or a small incentive ({{FILL: cart-recovery discount, default ≤10%}}) — only if margin allows, capped at 1 incentive per customer per quarter (enforce via segment).

**Post-purchase:**
1. Order confirmation (instant): reassure, set the delivery expectation, no selling.
2. Shipped/delivered notices: tracking + what to expect on arrival.
3. Delivery +3–7d: usage and care tips. This email cuts returns and quietly primes a good review.
4. Delivery +10–21d (after real use): review ask — see playbook 7 for rules.
5. Replenishment/cross-sell at the product's real consumption interval {{FILL: days per product}}.

**Winback:**
1. Trigger: no purchase for 2.5× the median repurchase gap {{FILL: computed from order data}}.
2. Touch 1: "still here" + what's new/bestsellers, no discount. Touch 2 (+7d): incentive. Touch 3 (+14d): last chance, incentive expires.
3. Sunset rule: ignored the full series and 90 days of campaigns → suppress from marketing sends (deliverability is a shared resource across the whole list).

### 7. Reviews & UGC operations

**Getting them (legitimately — the only way):**
1. Automate the ask on every order. Amazon: "Request a Review" button/automation inside the 30-day window; Etsy: follow-up message after delivery; own shop: email at delivery +7d {{FILL: adjust to time-to-first-use}} with a deep link to the review form.
2. Time the ask AFTER first real use, not at delivery.
3. Package insert rules: a neutral "how did we do + support contact" card is fine. BANNED everywhere: incentives for reviews, asking only happy customers (review gating), asking anyone to change a review. These get accounts suspended (verify current policy per platform).
4. Photo/UGC: ask for photos explicitly in the own-shop ask; on our own channels we may run a UGC contest with disclosure — never on marketplace listings.

**Responding:**
1. Reply to every review ≤3 stars within 48h: (a) thank, (b) own the issue without excuses, (c) state the concrete fix/replacement, (d) move to support channel. Never argue — the audience is future buyers, not the reviewer.
2. Amazon restricts public replies to reviews (verify current mechanism); there, the "response" is fixing the root cause and updating the listing.
3. Tag every 1–2 star review with a root cause: defect / expectation-mismatch / shipping / wrong-buyer. Three same-tag reviews in 30 days = fix the product or the listing (usually bullet 2 or images), not customer service.

**Using them in copy:**
1. Review mining: collect 30–50 reviews (ours + competitors'), tag recurring phrases by theme.
2. Top 3 objections → bullets 2–4 and the PDP objections section. Top praise phrase → bullet 1 / headline candidate.
3. Quote verbatim with permission on own shop; never fabricate or "polish" quotes — edited praise reads fake and is policy-risky.

## Junior mistakes

1. **Keyword-stuffed title** → unreadable tile, lower CTR, lower rank. Correction: primary phrase once, natural attributes, read-aloud test.
2. **Discounting to fix low conversion** → price is rarely the blocker. Correction: run the playbook-2 diagnosis; fix images/social proof first.
3. **Changing three things at once** → no attribution. Correction: one lever, 14 days, change log.
4. **Copying a competitor's listing** → inherits their blind spots plus IP risk. Correction: mine their REVIEWS, not their copy.
5. **Pricing off COGS only** → "profitable" products that lose money. Correction: full unit-economics table (playbook 4) before setting any price.
6. **Judging a listing on revenue alone** → misses that traffic and conversion moved opposite ways. Correction: always look at sessions and CVR separately.
7. **Defensive replies to bad reviews** → future buyers read your reply, not the review. Correction: 4-step response, playbook 7.
8. **Publishing with 1–2 photos** → conversion ceiling locked low. Correction: 7-shot list is the minimum for a launch.
9. **Same title/copy pasted across platforms** → each platform truncates and indexes differently. Correction: per-platform title pass (playbook 1 notes).
10. **Deep spike promos** → margin burned, customers trained, stockout then rank loss. Correction: required-lift rule + calendar logic (playbook 4).

## Escalate to frontier review when…

High-stakes = wrong version costs real money, account health, or brand trust. Run `cjudge <file> ecommerce` BEFORE shipping when any of these is true:

1. New product launch listing (first published version).
2. Price change >15% on a top-3 revenue product, or any repricing touching >20% of catalog.
3. Any promo with discount > {{FILL: max discount %, default 30%}}, or sitewide events (BFCM plan, clearance).
4. Copy making health, safety, regulated-category, or comparative ("better than [brand]") claims.
5. Marketplace account-health actions: policy warnings, suspension appeals, counterfeit claims.
6. Legally binding text: warranty terms, guarantee wording, shipping/returns policy changes.
7. Bulk operations: feed-wide edits, mass listing updates, catalog migrations.
8. Anything the RUBRIC scores below publish threshold twice after revision — stop iterating, get the second opinion.
