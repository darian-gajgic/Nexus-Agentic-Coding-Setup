# Marketing Playbook

> **Who reads this:** AI agents drafting marketing work, and the two humans reviewing it.
> **Before any task:** read `~/knowledge/BUSINESS-CONTEXT.md` (what we sell, to whom, current numbers) and `~/knowledge/STYLE-VOICE.md` (how we sound).
> **Before any delivery:** gate through `~/knowledge/domains/marketing/RUBRIC.md`.
> **Worked references:** `examples/landing-page.md`, `examples/email-launch-sequence.md`, `examples/seo-content-brief.md`.
> Follow numbered steps in order. Do not skip or reorder steps. Numbers marked "(verify current numbers)" drift — check before relying on them.

## Operating principles

1. **One campaign, one objective, one metric.**
   Why: a campaign chasing two goals can't be diagnosed when it fails — you won't know which half broke.
2. **Fix the offer and page before buying traffic.**
   Why: paid traffic multiplies what exists; multiplying a page that converts at 0.5% just burns cash faster.
3. **Copy is assembled from research, not written from imagination.**
   Why: the best headlines are near-verbatim customer quotes — mine reviews, tickets, and calls before drafting a word.
4. **Owned channels first (email, SEO); rented channels second (paid, social platforms).**
   Why: rented reach gets repriced or deleted overnight; the list and the rankings compound and belong to us.
5. **Specificity is the cheapest proof.**
   Why: "from 3 hours to 20 minutes" is believed; "save time" is skimmed. Concrete beats superlative every time.
6. **At small budgets, frequency beats reach.**
   Why: 7 touches on 2,000 right people converts; 1 touch on 50,000 vaguely-right people evaporates.
7. **Below ~30 conversions, differences are noise.**
   Why: dashboards wiggle daily; decide on pre-set thresholds, never on this morning's number.
8. **Native beats polished.**
   Why: audiences are ad-blind to things that look like ads; creative that mimics the platform's organic content gets processed as content.
9. **Ship at 80% and let the market judge.**
   Why: your taste is a hypothesis; two extra days of polish never fixed a weak offer, and live data settles arguments drafts can't.
10. **Measure weekly, change monthly.**
    Why: constant tinkering resets algorithm learning and destroys your own ability to attribute cause — most "failed" campaigns were killed before they had data.

**Terms used below:** BOFU = bottom-of-funnel (searches/pages closest to purchase) · CPA = cost per acquisition · CAC = customer acquisition cost · ROAS = return on ad spend · MPP = Apple Mail Privacy Protection · DR = domain rating (authority proxy) · PAA = People Also Ask.

## Task playbooks

Route the request first: "should we run/launch X?" → §1 · "write/fix a page" → §2 · "write emails / launch to the list" → §3 · "set up/fix ads" → §4 · "what content should we make / why no Google traffic?" → §5 · "how are we doing / build the report" → §6. A request touching several (e.g. a launch) runs §1 first, always.

### 1. Campaign strategy (any channel)

Order is mandatory: objective → audience → channel → message → measurement. Picking the channel first is the classic failure mode.

1. **Objective.** Write one sentence: "Move [metric] from [baseline] to [target] by [date]."
   - No baseline available → STOP. Get the number (analytics, CRM, or run one measurement week) before continuing.
   - Objective must be a business metric (signups, leads, orders, revenue). Impressions/followers/traffic alone = FAIL.
2. **Audience.** Pick ONE primary segment. Define by problem + trigger moment, not demographics:
   - Write down: who they are, what event made them start looking, what they tried before, what they would type into Google.
   - Attach ≥ 3 verbatim quotes from real sources (reviews, support tickets, sales calls, Reddit/forums). None available → spend 30 minutes mining competitor reviews first.
3. **Channel.** Pick ONE primary channel using this table:

   | Situation | Primary channel |
   |---|---|
   | Budget < $500/mo, B2B | Email + BOFU SEO + manual outreach/partnerships |
   | Budget < $500/mo, B2C/e-com | Organic short-form + email; paid only as retargeting |
   | Budget $500–2,000/mo | One paid channel: retargeting first, prospecting second |
   | Engaged list > 1,000 | Email is the launch channel; everything else feeds it |
   | Results needed < 30 days | Paid or direct outreach — SEO and organic social cannot deliver that fast |

4. **Message.** One core promise + strongest available proof, in the format: "For [audience], [product] [specific outcome] — proven by [proof]." Every ad, subject line, and headline must trace back to this sentence.
5. **Measurement.** Define BEFORE launch: primary KPI, guardrail metric (the thing you refuse to make worse, e.g. unsubscribe rate), weekly check-in day, and kill criteria ("stop if < X conversions by [date]").
6. Compress steps 1–5 into a one-page brief. Score it against RUBRIC.md. If high-stakes (see Escalation section), run `cjudge` before launch.
7. **One-page brief skeleton (the §1 deliverable):**
   - Objective: metric, baseline → target, date
   - Audience: segment + trigger moment + 3 verbatim pains
   - Channel: primary channel + the table row that justifies it
   - Message: the "For [audience]…" sentence from step 4
   - Offer: what they get, price/terms, risk reversal, honest urgency (if any)
   - Measurement: KPI, guardrail, kill criteria, weekly review day
   - Budget, owner, launch date

### 2. Landing page copy

1. **Collect inputs before writing:** the ONE conversion action; offer details (price, guarantee, terms); ≥ 10 verbatim customer quotes; top 5 objections (from support/sales, or competitor 1–3 star reviews).
2. **One page, one job.** One conversion action, repeated down the page. Two different CTAs = two half-pages. Remove main-site navigation on campaign pages.
3. **Hero (above the fold):**
   - Headline ≤ 12 words: named outcome + specificity. Working formulas:
     - "[Outcome] without [top pain]"
     - "[Outcome] in [timeframe]"
     - "[Do hard thing], [surprisingly easy mechanism]"
     - A customer quote, verbatim, in quotation marks.
   - Subhead ≤ 25 words: how it works + who it's for.
   - CTA button: verb + what they get ("Start my free trial"). Never "Submit" / "Learn more".
   - 5-second test: a stranger must answer "what is it, who's it for, what do I do next" from the fold alone.
4. **Section order (message hierarchy):** hero → social-proof strip (logos/count/rating) → problem agitation (their words) → solution + 3–5 features-as-benefits → how it works (3 steps) → deep testimonials (names + numbers) → objection handling + risk reversal → FAQ (5–7) → final CTA. See `examples/landing-page.md` for a full build.
5. **Benefits chain.** For each feature run: feature → "so what?" → benefit → "prove it". Publish the benefit and the proof; the feature is a supporting detail.
6. **Proof placement.** Every claim gets proof within one screen: a number, a named testimonial, a screenshot, or a guarantee. Claim without adjacent proof → cut the claim, not the proof-hunt.
7. **CTA rhythm.** Repeat the CTA every 1.5–2 screens. Same action; wording may vary.
8. **Cut 30%.** Read the draft aloud; delete every sentence that doesn't advance the one job. Reading level ≤ grade 7 (B2B: ≤ 9).
9. **Diagnostic benchmarks once live** (verify current numbers): cold-traffic pages converting < 1% → message/offer problem, rewrite before driving more traffic; 2–5% is normal cold; warm/email traffic should hit 10%+. Diagnose with segments (§6), not the average.
10. Gate through RUBRIC.md (all must-pass gates + kill list).

### 3. Email campaigns & sequences

**Types — pick one job per email:** broadcast (launch, content, news) or automated (welcome, launch sequence, cart-abandon, onboarding, win-back). Minimum viable stack for any list: a 3–5 email welcome sequence + a regular value cadence.

1. **One email, one job.** One goal, one CTA (the same link repeated is fine). Two topics = two emails.
2. **Structure:** subject (30–45 chars, mobile-safe) → preview text (40–90 chars that extends the subject — never "View in browser") → first line earns the second line → body 150–300 words for broadcasts → single CTA → PS (restate offer or deadline; the PS is the second-most-read line after the subject).
3. **Subject lines:** draft 5+, then pick. Specific beats clever. Curiosity must be cashable by the body — clickbait you can't pay off costs future opens.
4. **Send heuristics:**
   - Frequency floor: ≥ 1 value email every 2 weeks, or the list goes cold and your next send draws complaints.
   - Welcome email: within 5 minutes of signup — it earns 3–5× the engagement of any later send (verify current numbers).
   - Sequence spacing: 1–3 days between emails; launch sequences compress near the deadline (see `examples/email-launch-sequence.md`).
   - Send-time optimization is a rounding error next to list quality and subject relevance. Cap effort at "avoid Monday morning pileup".
   - Resend-to-non-openers: allowed once per important broadcast, ≥ 24h later, new subject line — and only while complaint rate is comfortably under 0.1%. Never on the same day.
5. **Deliverability — binary checks before any large send:**
   - SPF + DKIM + DMARC all pass (use any DMARC checker).
   - One-click unsubscribe present and working.
   - Spam-complaint rate < 0.1%; hard fail at 0.3% — the Gmail/Yahoo bulk-sender line (verify current numbers).
   - List is 100% opt-in. A purchased or scraped list is never used, ever.
   - Sunset policy: no click in 120 days → one win-back email → suppress.
6. **Metrics:** judge by clicks and replies. Opens are inflated by Apple Mail privacy proxies — directional only. Healthy broadcast click rate: 2–4% (verify current numbers).
7. **Welcome sequence blueprint (build once per list, highest-ROI automation we own):**
   - E1, instant: deliver the promised thing + set expectations (what we send, how often) + one-line "reply and tell me [qualifying question]".
   - E2, +1 day: our single best resource, ungated.
   - E3, +3 days: founder story — why this exists (people buy from people at our size).
   - E4, +5 days: soft pitch: one problem, one proof, one CTA.
   - E5, +8 days: clear offer; add a deadline only if a real one exists.
8. **Launch sequences:** use the 5-email arc (tease → value → launch → objections/proof → last call) — full worked copy in `examples/email-launch-sequence.md`. Suppress purchasers from remaining sends: binary check before every send.

### 4. Paid ads (tiny-budget doctrine)

**Gate — no spend until all three pass:** pixel/conversion API installed; one test conversion fired and visible in the platform; UTMs per playbook §6 on every ad.

1. **Consolidate structure.** One campaign per objective, 1–3 ad sets, 3–5 creatives each. Fragmentation starves the algorithm: exiting learning takes ~50 conversions/week per ad set on Meta and ~30 conversions/30 days per campaign for Google smart bidding (verify current numbers).
2. **Minimum viable budget:** daily budget ≥ 1–2× expected CPA, or data arrives too slowly to act on. Can't afford that → run retargeting-only, or skip ads entirely (email/SEO instead). Never split < $500/mo across two platforms.
3. **Targeting on Meta-type platforms:** go broad and let the creative select the audience — post-2023, algorithmic delivery beats manual interest stacks; the hook is the targeting (verify current platform guidance).
4. **Google Search:** start phrase/exact on 10–20 BOFU keyword themes. Review the search-terms report weekly and add negatives — in the first month this is the highest-ROI 20 minutes of the week.
5. **Creative testing:** change one variable per test (hook OR visual OR offer). Kill rule: spend ≥ 2–3× target CPA with 0 conversions → pause it. Winner rule: no verdict before ~20 conversions per variant.
6. **Hands off during learning:** no edits for 3–7 days after launch or after any significant change. Every edit resets learning.
7. **Budget moves:** ±20–30% per day maximum; bigger jumps reset learning (verify current numbers).
8. **Creative anatomy (every ad):** hook (first line / first 1.5s — this is 80% of performance), body (one proof or one demo, not a feature list), CTA (what happens next, effort stated). Write 5 hooks per concept; the hook is the variable you're testing.
9. **Retargeting audiences to build from day one, even before spending:** site visitors 30/90/180 days, 50%+ video viewers, email-list upload, past purchasers (as exclusion). They accumulate free and are the cheapest conversions we will ever buy.
10. **Weekly review only** (same day, 30 minutes): CPA vs target, pacing, search terms/placements, maximum one decision per campaign.

### 5. SEO strategy + on-page basics

1. **Classify intent before writing — the SERP is the answer key.** Google the keyword: product/category pages ranking → transactional; listicles/comparisons → commercial; guides → informational. Produce the format the SERP already rewards; don't pitch a product page at a listicle SERP.
2. **BOFU first (year one), in this order:** "[competitor] alternative" → "[X] vs [Y]" → "best [category] for [niche]" → "[category] pricing" → integration/use-case pages → only then informational content. Low volume + high intent beats head terms you won't rank for.
3. **Difficulty check without paid tools:** top 10 all household brands or DR-70+ domains → skip the keyword. A Reddit thread, forum post, or thin page ranking → genuine opportunity.
4. **Content vs technical:** under ~500 pages, technical SEO is a one-time checklist — indexable, sitemap submitted, one H1 per page, mobile fine, no redirect chains, Core Web Vitals not failing. After that, 95% of effort goes to content + internal links. Re-auditing your own small site monthly is procrastination.
5. **On-page checklist (binary):** primary keyword in title tag (front-loaded, ≤ 60 chars), in the single H1, in the URL slug, in the first 100 words. H2s cover the subquestions (source them from People-Also-Ask + top-10 headings). Include the named entities the top results share. Title/meta written as click copy, not keyword strings.
6. **One keyword cluster, one page.** Before writing, search `site:ourdomain.com "keyword"` — if a page already targets the cluster, refresh/expand it instead of publishing a sibling. Two of our pages competing for one query means both rank worse (cannibalization).
7. **Internal linking:** every new post links out to 2–3 money pages with descriptive anchors; same day, edit 1–2 older relevant posts to link back in. Zero orphan pages. Organize hub-and-spoke per topic cluster.
8. **Cadence and patience:** 3–6 months to rank meaningfully is normal. Sustained ≥ 4 quality pieces/month beats bursts. After ~30 published pieces, refreshing decayed winners usually out-ROIs net-new content.
9. **Refresh procedure (quarterly):**
   - Pull pages ranking positions 5–15 with flat/declining clicks (Search Console, compare 3-month windows).
   - Update facts, prices, screenshots, year references; add sections for new People-Also-Ask questions.
   - Change the visible "updated" date only when the update is material — fake freshness is detectable and penalized in trust if not rankings.
   - Request re-indexing. A refresh costs ~half a new post and usually returns more traffic delta.
10. **AI-search era (2026):** put a 40–60 word direct answer under the H1, add FAQ blocks, include citable stats — these raise inclusion in AI overviews/answers. Expect declining CTR on purely informational terms; weight BOFU accordingly (verify current best practice — this is moving fast).

### 6. Measurement

1. **UTM schema — never deviate.** All lowercase, hyphens (no spaces or underscores):
   - `utm_source` = platform: `google`, `meta`, `newsletter`, `partner-<name>`
   - `utm_medium` = class, one of: `cpc`, `email`, `social`, `referral`, `partner`
   - `utm_campaign` = `yyyymm-name`, e.g. `202607-launch`
   - `utm_content` = creative/variant id, only when testing
   - NEVER tag internal links with UTMs (it resets the session and corrupts attribution).
   - Every UTM link is minted into the shared UTM sheet; a link not in the sheet doesn't exist.
2. **Weekly scorecard** — ≤ 10 numbers, same day every week, 30 minutes: sessions by source, leads/signups, activation or first-purchase count, revenue/MRR, email list net growth, email click rate, blended CAC (total marketing spend ÷ new customers), top converting page. Record week-over-week AND the 4-week average — react to the average, not the week. {{FILL: the exact 8–10 numbers for our funnel(s), per business line}}
3. **Attribution realism for a 2-person team:** blended CAC is the true north. Platform-reported ROAS overcounts (it claims credit for conversions that would have happened anyway). Add a mandatory free-text "How did you hear about us?" at signup/checkout — self-reported attribution is the best signal a small team can afford. Do not buy multi-touch attribution tooling below ~$50k/mo spend.
4. **A/B testing threshold:** under ~350 conversions per variant you cannot detect a realistic 10–20% lift (verify with a sample-size calculator). Below that: sequential big-swing changes, pre/post comparison, and honest labeling of the uncertainty in the report.
5. **Monthly review (60 minutes, first week of the month):**
   - Rank channels by blended CAC and payback period; apply the kill/scale criteria written in each brief.
   - Reconcile platform-reported conversions vs analytics vs self-reported source — expect platforms to over-claim by 20–50% (verify against our own data).
   - Pick ONE experiment for the coming month. One. The backlog holds the rest.
6. **Kill/scale criteria are written in the brief, before launch.** Choosing thresholds after seeing the data is how sunk-cost keeps dead campaigns alive.

## Junior mistakes

| Mistake | Correction |
|---|---|
| Launching before tracking exists (pixel/UTM/baseline) | Tracking is step 0; fire one test conversion before any spend |
| "Our audience is small businesses / everyone" | Segment by problem + trigger moment; produce 3 verbatim pains or go do research first |
| Feature-dumping ("we have X, Y, Z") | Run each feature through "so what?" until it's an outcome; lead with the outcome |
| Judging ads at 48 hours; tinkering daily | No edits during learning (3–7 days); decide only at pre-set spend/conversion thresholds |
| Testing five things at once on 200 visitors | One variable per test — or one big-swing redesign judged pre/post (§6.4) |
| Chasing head keywords ("crm", "marketing") | BOFU first (§5.2); run the difficulty proxy check (§5.3) |
| Emailing only when "we have news" | Fixed value cadence (§3.4); the list is a garden, not a megaphone |
| Reporting averages ("conversion is 2.1%") | Segment by device, source, new/returning — the average hides the lever |
| Imitating big-brand marketing (clever, vague, brand-first) | Small teams run direct response: offer, proof, CTA. Brand is a byproduct of consistency |
| Vanity metrics in reports (impressions, likes, followers) | Report the pipeline: clicks → leads → customers → revenue |
| New channel every month | 90-day minimum commitment per channel before a verdict; one channel done well beats three half-done |
| Reflexive discounting when sales dip | Add value first (bonus, extended trial, payment plan); discounts train the audience to wait |
| Shipping placeholders ({{FILL}}, lorem, wrong product name) | RUBRIC gate 10: search the draft for `{{`, `lorem`, `TODO` before delivery |
| Trusting platform ROAS as truth | Reconcile against blended CAC and self-reported attribution monthly (§6.3) |
| Writing to impress peers (jargon, cleverness) | Write to the least-informed qualified buyer; clarity converts, cleverness decorates |
| Saving the best offer for strangers | The warmest audience (list, past customers) gets the first and best offer, always |

## Escalate to frontier review when…

Run the deliverable through `cjudge` (frontier second review) BEFORE launch/delivery if ANY of these is true. When unsure, escalate — a cjudge pass costs minutes; a bad send to the full list costs a year of list-building.

- **Money:** one-shot spend > $200; any daily-budget change > $50/day; anything touching the pricing page.
- **Reach:** email to > 500 recipients; homepage changes; posts to the company's main public accounts.
- **Claims:** competitor comparisons naming names; health/financial/income claims; statistics we didn't source ourselves; legal-adjacent copy (consent text, promotion terms, testimonial usage rights).
- **Irreversibles:** domain or sending-domain changes; first send from a new domain; deleting historical campaigns/data; public statements on sensitive topics (these also go to a human, not just cjudge).
- **Brand:** any deliberate departure from `~/knowledge/STYLE-VOICE.md`; all crisis or apology communications (human review mandatory).
- **Client work:** anything a client will show THEIR audience; any deliverable on a contract > $1,000. {{FILL: adjust money/reach thresholds to current risk tolerance and typical contract size}}
- **Quality signal:** RUBRIC score lands in the revise band (18–23), or two revision loops still haven't cleared the must-pass gates.
