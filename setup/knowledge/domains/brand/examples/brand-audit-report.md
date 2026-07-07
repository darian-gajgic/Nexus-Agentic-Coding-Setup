> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# Brand Audit — Bergamot & Pine

> Small-batch home fragrance, e-commerce. · Audit date: 2026-06-02 · Auditor: Human A (AI first pass, human verification) · Timebox: 60 min · Evidence: `audits/2026-06-bp/` (screenshots + copy exports)
> Audited against: B&P one-pager v1.2 (2025-11-20). Never audit from memory — rules extract below is pasted from that file.

## Rules audited against (extract from the one-pager)

- **Positioning:** For scent-sensitive apartment dwellers who find candle-store scents overwhelming, B&P is the home fragrance brand for small spaces — precise, low-throw blends for rooms under 25 m² — because every blend is tested in a real 18 m² flat. Unlike mass candle brands, we publish a throw rating on every product.
- **Promise:** every product page shows an honest 1–5 throw rating, tested in a real room.
- **Personality:** Precise but not clinical · Quiet but not shy · Honest but not blunt.
- **Voice rules (extract):** no exclamation marks outside launch posts; scents described by place-memory, not perfume jargon; numbers stated plainly; banned words include "luxury," "indulgence," "treat yourself."
- **Visual rules (extract):** cream base + ink green + one terracotta accent; serif display + humanist sans; photography in daylight, real rooms; never marble-and-gold flatlays.

## Scope — touchpoints inventoried

| # | Touchpoint | Location | Evidence captured |
|---|---|---|---|
| 1 | Homepage + 12 product pages | shop (Shopify) | 14 screenshots |
| 2 | Instagram grid + bio | @bergamotandpine | last 12 posts + bio |
| 3 | TikTok | @bergamotpine | last 8 videos + captions |
| 4 | Etsy shop | 4 listings + banner | 6 screenshots |
| 5 | Email flows (Klaviyo) | welcome ×3, abandoned-cart ×2 | HTML exports |
| 6 | Transactional emails | Shopify defaults ×3 | samples |
| 7 | Packaging | outer box, label, insert card | photos |

## Method (per PLAYBOOK task 5)

1. Touchpoint list pulled from BUSINESS-CONTEXT.md; manual sweep added Etsy + transactional emails (both missing from the list — now added there).
2. Evidence captured for all 7 touchpoints before any judging.
3. AI first pass: each touchpoint checked against the 7 axes (logo, color, type, voice, positioning, promise, CTA), quoting the failing line or element for every fail.
4. Human verification: every AI-flagged fail confirmed or dismissed against the evidence; 2 false positives dismissed (seasonal launch post legitimately used "!"— allowed by the launch-post exception).
5. Severity graded with the S1/S2/S3 definitions; fixes written as system changes where possible, not instance patches.
- Time spent: 55 min (AI pass 20 min unattended, human verification + write-up 35 min).

## Findings summary

Severity: **S1** contradicts positioning/promise · **S2** breaks a written voice/visual rule · **S3** cosmetic drift. Effort: quick (< 30 min) or project.

| ID | Touchpoint | Finding | Severity | Effort |
|----|-----------|---------|----------|--------|
| F1 | Etsy | Permanent "20% OFF" banner + listing titles keyworded "LUXURY CANDLE" | S1 | quick |
| F2 | Product pages | Throw rating missing on 4 of 12 pages | S1 | quick |
| F3 | TikTok | Different persona: hype captions, "treat yourself" ×3, chains of "!!!" | S1 | project |
| F4 | Homepage | Hero reads "Hand-poured with passion" — kill-list phrase, says nothing about small spaces | S1 | quick |
| F5 | Welcome email 1 | Opens with founder story, no positioning; CTA "Shop luxury scents" | S2 | quick |
| F6 | Instagram | 4 of last 12 posts are marble-and-gold flatlays (banned imagery) | S2 | project |
| F7 | Insert card | Perfume jargon ("top notes of bergamot, heart of vetiver") vs place-memory rule | S2 | project |
| F8 | Transactional emails | Shopify default voice ("Your order is on its way!") — zero brand | S2 | quick |
| F9 | Abandoned-cart 2 | "Don't miss out!!" + countdown timer vs Quiet-but-not-shy | S2 | quick |
| F10 | Instagram bio | Category line reads "Luxury candles & home fragrance" (banned word, wrong claim) | S2 | quick |
| F11 | Product pages | Second, unapproved coral accent in use alongside terracotta | S3 | quick |
| F12 | Etsy banner | Pre-2025 logo lockup still live | S3 | quick |

Axis pass rate across 7 touchpoints (name/logo, color, type, voice, positioning, promise, CTA): 31 of 49 checks pass. Weakest axes: positioning message (3/7) and voice (3/7).

## Detailed findings and fixes

### S1 — contradicts positioning or promise. Fix first, regardless of effort.

**F1 — Etsy discount posture.** A permanent 20% banner reprices the brand as a bargain and trains buyers to wait for sales; "LUXURY" keywords court exactly the buyer the positioning excludes.
Fix: end the permanent discount today; one sale window per quarter max. Rewrite listing titles around "small space / low throw / apartment" terms. Accept the short-term Etsy traffic dip — position over impressions.

**F2 — Missing throw ratings.** The rating is the promise — the one thing customers were told to hold us to. Four pages without it is a breach, not a gap.
Fix: add the four ratings this week (test data exists in the product sheet). Add a launch checklist line: "no product page goes live without a throw rating." This makes the fix structural, not cosmetic.

**F3 — TikTok persona.** Captions run on hype grammar ("obsessed!!", "treat yourself") — a second personality, not tone flex. Tone flexes; voice doesn't (PLAYBOOK junior mistakes).
Fix: keep the video formats (formats may flex freely); rewrite the caption templates in brand voice. Retest for 30 days. If engagement drops > 20%, do NOT silently revert — escalate to `cjudge` for a deliberate, documented sub-voice decision written into the one-pager.

**F4 — Homepage hero.** "Hand-poured with passion" is kill-list filler occupying the most valuable sentence the brand owns, and it positions nothing.
Fix: replace with the positioning compressed — headline "Scents sized for small spaces." + sub "Every blend tested in a real 18 m² flat. Throw-rated 1–5, honestly."

### S2 — breaks a written rule. Quick fixes this week; projects scheduled.

**F5 — Welcome email 1.** Positioning-first, story-second: lead with "why low-throw for small rooms," move the founder story to email 2. CTA → "Find your room's scent."
**F8 — Transactional emails.** Write 5 override templates in brand voice (order, shipping, delivery, refund, back-in-stock); zero exclamation marks; store them in the brand asset folder as approved templates.
**F9 — Abandoned-cart 2.** Delete the countdown. Urgency only via honest facts: "18 of 120 left from this batch." Quiet but not shy means stating facts plainly — not manufacturing panic.
**F10 — Instagram bio.** → "Low-throw scents for small spaces. Tested in a real flat, throw-rated 1–5."
**F6 — Instagram imagery (project).** Brief the next shoot directly from the one-pager's always/never list; until then, post from the compliant photo pool only.
**F7 — Insert card (project).** Rewrite in place-memory language ("the first cold morning of the year, pine outside an open window"). Reprint with the next stock order — do not scrap current stock; S2 severity does not justify write-offs.

### S3 — batch into the next natural redesign or adjacent task

**F11 — Coral accent.** Consolidate to the approved terracotta hex during the next theme edit.
**F12 — Old Etsy banner.** Swap the asset while inside Etsy fixing F1 (5 minutes).

## Deferred observations (out of brand scope — routed, not fixed here)

- Pricing page structure confuses bundle vs single purchase — routed to marketing domain backlog. Not a brand finding; the copy is on-voice.
- Etsy search ranking dropped after last title edit — routed to ecommerce domain. Interacts with F1: coordinate the title rewrite with whoever owns Etsy SEO.
- Klaviyo flows lack a post-purchase review ask — routed to marketing. Brand constraint attached: the ask must follow the "quiet, no pressure" voice rules when built.

An audit that fixes everything it notices becomes a rewrite of the whole company. Log, route, stay in lane.

## What's working — protect these

- Product-page copy on the 8 compliant pages is fully on-voice (place-memory descriptions). Use the "Juniper Room" page as the reference exemplar for all new pages.
- The packaging outer box (cream + ink green, serif) is the strongest brand asset in the lineup test. Do not touch it during the insert-card reprint.
- The Instagram carousel format "1 scent · 1 room · 1 rating" is the distinctive asset working exactly as designed — increase its frequency; it should anchor the grid.

## Top 5 fixes

| # | Fix | Owner | Due |
|---|-----|-------|-----|
| 1 | F2 — throw ratings on 4 product pages + launch checklist line | Human A | Jun 04 |
| 2 | F4 — homepage hero rewrite (AI drafts, rubric-check, human approves) | Human B | Jun 05 |
| 3 | F1 — Etsy de-discounting + title rewrite (+F12 banner while in there) | Human A | Jun 06 |
| 4 | F8 + F9 — transactional and cart email overrides | Human B | Jun 09 |
| 5 | F3 — TikTok caption templates v2 | Human B | Jun 12 |

## Re-audit

- Next quarterly audit: 2026-09-01, same touchpoint list, same 60-minute timebox.
- F3 engagement retest checkpoint: 2026-07-12 (30 days after template swap).
- Weekly 10-minute cross-checks continue per PLAYBOOK governance rule 6.

## Rubric check (gate G10)

- All 12 findings carry severity + effort + a concrete fix + captured evidence: PASS.
- No kill-list phrases introduced by the proposed fixes (F4 and F10 rewrites checked against RUBRIC G9): PASS.
- Escalation triggers reviewed: none apply (no rename, no public claims, no client deadline). `cjudge` not required; teammate spot-check scheduled.

---

## Why this works

- **Evidence-first, memory never.** Every finding cites a captured artifact, so severity discussions become "look at the screenshot," not a taste debate (PLAYBOOK audit step 2). The rules extract is pasted in, so the report is self-contained and checkable by someone who has never seen the one-pager.
- **The severity scale is doing real strategic work.** F1–F4 outrank prettier problems because they touch positioning and the promise. An audit ordered by visual annoyance would have led with the coral accent (F11) — the least consequential finding on the list.
- **F2 shows why promises must be falsifiable** (RUBRIC G6). Because the one-pager promised something checkable — a rating on every page — the breach was caught mechanically by a mid-tier model doing a first pass. "We're honest about our scents" could never have failed an audit.
- **F3 is graded S1, not excused as "social is just different."** The playbook line "tone flexes, voice doesn't" makes the call for you. Note the fix still leaves a legitimate exit: a deliberate, documented sub-voice via escalation — the crime is silent drift, not the flex itself.
- **Fixes change systems, not just instances.** F2 adds a launch-checklist line; F8 creates approved templates (PLAYBOOK governance rule 4: never start from blank again). Instance-only fixes guarantee the same audit next quarter.
- **"What's working" is a first-class section.** Audits that only list sins teach a team to associate brand work with punishment — and working assets end up "refreshed" by accident. Naming the Juniper Room page as the exemplar gives every future page a concrete target (principle 6: consistency compounds).
- **Fixes are sized with money in mind.** The insert reprint waits for the next stock order; the Etsy discount ends today. Two-person governance means sequencing by leverage, not by irritation.
- **Owners and dates, or it's a mood.** The top-5 table is the actual deliverable; the findings are its justification. Every date is within 10 days — an audit fix due "next month" is a fix that won't happen.
- **The method section makes the audit repeatable and cheap.** AI does the mechanical axis checks unattended; the human spends their 35 minutes on judgment calls (the dismissed false positives, the S1/S2 boundary on F3). That division is what makes the quarterly 60-minute timebox realistic for two people.
- **Deferred observations keep the audit in its lane.** Routing the pricing-page issue to marketing — with a brand constraint attached — beats either ignoring it or scope-creeping the audit into a company rewrite.

## Adapt this

- {{FILL: brand + one-pager version audited against — paste the actual rules extract; if no one-pager exists, run PLAYBOOK task 1 first, audit second}}
- {{FILL: touchpoint inventory from BUSINESS-CONTEXT.md — include the unglamorous ones: invoices, proposals, DJ press kit/EPK, marketplace listings, link-in-bio, booking confirmation emails}}
- {{FILL: evidence folder path — screenshots/exports captured before judging anything}}
- {{FILL: findings table — one line each, graded with the S1/S2/S3 definitions verbatim from PLAYBOOK task 5}}
- {{FILL: axis pass-rate counts — 7 axes × your touchpoint count; weakest two axes get named}}
- {{FILL: what's working — minimum 2 items, each with a "protect it" instruction and one named reference exemplar}}
- {{FILL: top-5 table with real owner names and dates ≤ 10 days out}}
- {{FILL: retest metric + date for any fix that could cost engagement or revenue}}
- {{FILL: deferred observations — anything noticed outside brand scope, routed to its owning domain with a brand constraint attached}}
- {{FILL: false positives dismissed during human verification — keep them; they tune the AI's next first pass}}
- Keep as-is: the severity definitions and their ordering rule (S1 first regardless of effort), the 60-minute timebox, the "systems not instances" fix style, and the escalation path for fixes that underperform.
