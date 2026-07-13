# Marketing Quality Rubric

> Frontier-judge scoping (2026-07-13): for the text-only frontier judge, a gate whose evidence cannot appear on the page and is not contradicted by the task's artifacts is UNVERIFIABLE-HERE (a note), not FAIL — the cjudge verdict contract governs: only binding in-scope gate FAILs and critical/high findings block a SHIP.

> Gate every marketing deliverable through this file before delivery. Companion to `PLAYBOOK.md`.
> Order of use: (1) must-pass gates — any FAIL means do not deliver, fix and re-run; (2) kill-list sweep; (3) score the dimensions; (4) apply the decision rule.
> For each gate, record PASS/FAIL plus one line of evidence (a count, a quote, a screenshot ref). Every check here works without taste.

**Required output format for the reviewing agent (paste with the deliverable):**

```
GATES: 1 PASS (objective: "trials 40→60 by Sep 30") · 2 PASS · 3 FAIL (4 claims, 2 proofs) · … · 11 PASS
KILL LIST: clean | hits: "seamless" x2 (hero, FAQ), we>you (14 vs 9)
SCORES: specificity 3 · clarity 4 · proof 2 · VoC 3 · offer 3 · structure 4 · objections 2 · measurement 3 → 24/32
VERDICT: deliver | revise (fix list: …) | restart | + escalate to cjudge because …
```

## Must-pass gates (binary — do not deliver if ANY fails)

1. **Measurable objective stated.** The brief/asset names metric + target + date ("trial signups 40 → 60/mo by Sep 30"). "Raise awareness" = FAIL.
2. **One primary CTA.** Exactly one conversion action per asset. The same action repeated = PASS. Two different prominent actions ("book a demo" AND "start trial") = FAIL.
3. **Every claim has adjacent proof.** Count quantitative/superiority claims; count proofs (number, named testimonial, screenshot, cited source, guarantee) within one screen/paragraph of each. Claims > proofs = FAIL.
4. **Audience named specifically.** Segment + situation appears in the asset or brief ("freelance PPC consultants juggling 5+ client reports"). "Businesses of all sizes" = FAIL.
5. **Tracking ready.** All outbound links carry UTMs per PLAYBOOK §6 schema; the conversion event is named; for paid: a test conversion has fired.
6. **Nothing fabricated.** No invented testimonials, quotes, stats, or customer counts. Every statistic carries source + year. Price/terms match the live pricing page. One fabricated element = FAIL and restart.
7. **Reading level.** Grade ≤ 7 (B2C) or ≤ 9 (B2B) on Hemingway or equivalent.
8. **Skim test.** Reading ONLY headline + subheads + bolded lines + CTA reconstructs the full argument. Paste those lines alone and check they make the pitch.
9. **Mobile pass.** Email subject ≤ 45 chars; email renders single-column; landing hero (headline + CTA) fits one phone screen; title tag ≤ 60 chars.
10. **No placeholders.** Search the draft for `{{`, `[TODO`, `lorem`, `XXX`, and the wrong product/company name. Any hit = FAIL.
11. **Voice matches `~/knowledge/STYLE-VOICE.md`.** Spot-check 3 random sentences against its do/don't list; any direct violation = FAIL.

**Gate applicability:** every asset: gates 2, 3, 4, 6, 7, 8, 10, 11 · campaign briefs/plans: add 1 and 5 · email: add 9 (subject length, single-column) · landing/SEO pages: add 9 (hero on one screen, title ≤ 60). A gate that doesn't apply is marked N/A with a reason — never silently skipped.

## Scored dimensions (0–4 each, 8 dimensions, max 32)

**Decision rule: deliver at total ≥ 24 AND no dimension < 2. Total 18–23: one revision loop, rescore. Total < 18: restart from the playbook steps.**

1. **Specificity.**
   2 = some concrete details, but generic sentences remain ("saves you time").
   4 = numbers, names, and timeframes throughout; no sentence could sit in a competitor's copy unchanged.
2. **Single-message clarity.**
   2 = the core promise is findable but diluted by side-points.
   4 = one core promise appears in the first 10 seconds of reading, and every section visibly supports it.
3. **Proof density & quality.**
   2 = proof exists but is generic ("customers love us") or clustered in one section.
   4 = every major claim is paired with the strongest available proof type (number > named customer outcome > screenshot > logo wall).
4. **Voice-of-customer.**
   2 = plausible pains phrased in marketer language ("streamline your workflow").
   4 = pains in the customer's own words and situations, traceable to real quotes ("I rebuild the same report every Friday night").
5. **Offer & CTA strength.**
   2 = clear ask, but no risk reversal and no reason to act now.
   4 = ask + risk reversal (guarantee / free step / no card) + honest urgency or a named next step with effort stated ("2 minutes, no card").
6. **Structure & scannability.**
   2 = readable top-to-bottom, but walls of text; skimming gives a partial story.
   4 = passes the skim test; paragraphs ≤ 3 lines; one idea per section; visual hierarchy mirrors argument hierarchy.
7. **Objection coverage.**
   2 = one or two objections handled implicitly.
   4 = the top 3–5 researched objections each answered explicitly — price, effort/time, "will it work for MY case", trust, switching cost.
8. **Measurement readiness.**
   2 = a KPI is named.
   4 = baseline, target, kill/scale criteria, verified tracking links, owner and review date all present.

## Kill list (automatic flags — any hit = revise before scoring)

**Banned words/phrases — case-insensitive literal search, one term per line (usable as a grep pattern file):**

```
revolutioniz
revolutionary
game-chang
unleash
unlock your potential
supercharge
next-level
next level
cutting-edge
state-of-the-art
best-in-class
world-class
seamless
effortless
robust
synergy
delve
elevate your
look no further
fast-paced world
ever-evolving
digital landscape
we're passionate about
take your .* to the next level
```

**Banned only when self-applied or unproven (judge by the sentence, then decide):**

- "powerful", "innovative"/"innovation" describing our own product
- "solutions" as a naked noun for the product
- "leverage" as a verb; "empower" unless literally granting a permission
- "at [Company], we believe" framings
- "AI-powered" as the headline benefit (AI is a how, never the why-buy)
- "10x", "#1", "the best" — unless a source or mechanism sits in the same block

**Banned patterns — check by read-through:**

- **Feature-dump:** ≥ 3 features listed with no benefit attached to them.
- **We-heavy copy:** count "we/our/us" vs "you/your"; if we-count is higher, rewrite (exception: about page).
- **Exclamation marks:** more than one per asset; any at all in B2B copy.
- **Stacked rhetorical questions:** "Tired of X? Frustrated by Y? What if…?" — maximum one question in the first 100 words.
- **Fake urgency:** countdowns that reset; "only today" that repeats weekly; invented scarcity on digital goods.
- **Weak primary CTA labels:** "Submit", "Click here", "Learn more".
- **ALL-CAPS words** (legit acronyms excluded); **emoji in B2B subject lines**; Title Case On Every Headline Word (sentence case per STYLE-VOICE.md unless it says otherwise).
- **Unverifiable superlatives:** easiest, fastest, most trusted — allowed only with a cited source in the same block.
- **Passive-voice hero lines:** "Reports are generated automatically" → "Generate reports automatically".
- **Curiosity the body can't cash:** subject/headline promises something the content never delivers.
