> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# Cold Outreach Sequence — 3 touches, productized offer

Worked example for a fixed-price offer: **"Store Speed Sprint"** — audit + fix the
mobile speed of a Shopify store in 2 weeks, fixed price. Target buyer: founder of a
DTC e-commerce brand, roughly 5–30k orders/year, founder still reachable by email.
Observable symptom used for list building: bestseller product page loads > 4s on mobile.

Fictional prospect used throughout: Jonas Brandt, founder of Kestrel Supply Co.
(kestrelsupply.com), outdoor gear on Shopify.

## The 3-minute homework (do this per prospect, before writing anything)

1. Open their bestseller product page. Run it through PageSpeed Insights (mobile).
2. Write down: the LCP number, the single heaviest asset, one thing they clearly care about (new launch, review count, seasonal line).
3. Log prospect + findings in the tracker. No findings worth writing down → skip the prospect entirely.

The findings ARE the personalization. Everything else in the emails is fixed template.

---

## Touch 1 — day 0 (Tue–Thu, 08:00–10:30 their time)

Subject: `kestrelsupply.com — 5.8 seconds`

Hi Jonas,

I ran your Alpine 40 pack page through Google's speed test this morning: 5.8s to
load on a phone. Most shoppers give up around 3.

Two-thirds of store traffic is mobile now, so that's buyers bouncing before they
ever see the pack — happy to send you the raw report.

We fix exactly this for Shopify stores: fixed price, two weeks, before/after
numbers. I've already written up the five biggest issues on kestrelsupply.com.

Want the list? I'll just send it over — no call needed.

Darian
{{FILL: signature — name, one-line credential, site}}

Per-prospect slots in touch 1:
- Subject: their domain + their measured number.
- Line 1: named page + the LCP number (from homework step 2).
- "the pack": reference their actual product noun.
- Everything else stays fixed.

---

## Touch 2 — bump, day 3–4 (reply in the same thread)

No subject change.

Hi Jonas — one more from my notes, because this kind hides well:

Your hero image on the Alpine 40 page ships at 4,200px wide and about 1.9MB.
Phones download all of it, then shrink it. That single file is roughly a third
of your load time — and a 20-minute fix.

The other four issues are in a doc, ready to go. Send it over?

Darian

Per-prospect slots: the one new finding (heaviest asset from homework). If the homework
produced only one finding, do NOT invent a second — use the fallback bump: one relevant
before/after number from our own work ({{FILL: strongest case-study number}}) plus the
same one-line ask.

---

## Touch 3 — breakup, day 8–10 (same thread)

No subject change.

Hi Jonas,

Closing the loop — I'll assume store speed isn't a priority this quarter, which
is a perfectly sane answer.

So the notes aren't wasted, here are the top three of the five:

1. Hero images uncompressed (~1.9MB each) — resize + compress; biggest single win.
2. Four review/upsell apps load before the product does — defer or drop two.
3. Fonts pulled from three different services — consolidate to one.

If mobile speed makes the list later, this thread will still be here. Good luck
with the autumn line.

Darian

Per-prospect slots: the three findings; the sign-off detail (their launch/season —
from homework step 2). After this email: mark closed in the tracker. No touch 4.

---

## Reply branches

| Reply | Action (within 4 business hours) |
|---|---|
| "Yes, send the list" | Send the full 5-item doc, no pitch attached. Two days later, one line: "Which of the five surprised you? If you want them fixed rather than listed, that's the sprint — happy to walk you through it on a 15-min call." |
| "How much is it?" | Answer, never dodge: "Fixed €2,400, two weeks, everything on the list. Before I'd take your money I'd want 15 minutes to check the fixes will actually move your numbers — Thursday or Friday?" Price + qualification in one move. |
| "We have an agency / a dev" | "Makes sense — keep them. This is a one-off narrow job most agencies don't touch: we fix the speed, hand your team the report, and leave. If your dev would rather do it themselves, the list alone will save them a week." Position as specialist, not replacement. |
| "Not now / after Q3" | "Understood — I'll come back in {{month}}. Meanwhile here's the list anyway, no strings." Set a dated tracker task at +90 days. Re-approach ONLY with a fresh finding. |
| "Talk to [other person]" | Start a NEW thread to that person: "Jonas suggested I send you this" + the finding. Thank Jonas either way and tell him what happened — referrer gets a report-back. |
| Hostile / "remove me" | One line: "Done — you won't hear from me again." Suppress in tracker. Never argue, never explain. |
| No reply after touch 3 | Mark closed. List hygiene beats hope. |

---

## Deliverability guardrails (a junior domain has no reputation to spare)

- Send from {{FILL: sending domain}}. If the domain is new: ramp 5/day in week 1, 10/day in week 2, then normal volume. Never spike.
- SPF, DKIM, and DMARC verified before batch 1. Check once, log the result in the tracker.
- Plain text, max 1 link, no images, no open-tracking pixels — pixels cost deliverability, and cost trust if the prospect notices.
- Bounce rate must stay < 3%: verify addresses before sending; max one guessed address per company.
- One thread per prospect: bumps and breakups are replies in-thread, never new emails.

## Weekly metrics review (Friday, 30 min — Playbook playbook 2, step 9)

Track per batch of 25: delivered, replies (any), positive replies, calls or list-sends.

- Replies < 2/25 → the finding is weak. Sharpen homework step 2 (better symptom, better number) — do not polish the copy.
- Replies ≥ 2 but nothing booked/sent → the ask is too heavy. Shrink the CTA one notch.
- Positive replies but no-shows → scheduling friction: offer two concrete time slots in your reply instead of a bare calendar link (a link outsources effort; two slots is a courtesy).
- Change exactly ONE variable per week and note it in the tracker, or the numbers teach nothing.

---

## Why this works

- **Subject is the finding itself.** A real number about THEIR site out-specifics every "quick question" in the inbox, with zero clickbait — passes RUBRIC O3, expresses Playbook principle 3 (homework before hello).
- **First line is about them; we introduce ourselves in line 3, in half a sentence.** Attention is earned before it's spent. Juniors especially can't afford a "My name is…" opener (kill list).
- **The measured number does the credibility work.** No logos, no "proven track record" — the proof is that we already did unpaid, verifiable work on their store. This is the core junior credibility move: proof of work substitutes for portfolio.
- **The claim is checkable.** "Happy to send you the raw report" makes the number falsifiable, which is what makes it believable (RUBRIC dimension 7).
- **CTA gives instead of takes.** "Want the list? No call needed" is a sub-10-second yes (RUBRIC dimension 4). Asking a stranger for 30 minutes is asking them to price your unknown value; asking permission to hand over value prices it for them.
- **The bump adds a NEW finding, never "just following up."** Playbook mistake 12: no new thing, no email. The bump is often the highest-reply touch precisely because it proves there was more behind email 1.
- **The breakup gives the findings away.** Reciprocity plus a costly signal ("they clearly aren't desperate"). It also converts a dead thread into goodwill — several of these come back months later, and the giveaway costs nothing since the tracker keeps the full list.
- **Hard stop at 3 touches.** Reply odds past touch 3 collapse below 1% while spam-flag odds rise; a junior domain's sending reputation is an asset with no backup (Playbook playbook 2, step 5).
- **Fixed price named in-thread when asked.** Dodging "how much" reads as senior-agency games; a junior wins by being the only vendor who answers the question. The qualifying call is positioned as protecting THEM ("before I'd take your money").
- **Every branch ends in a tracker state.** Sequences die from untracked replies, not bad copy. GLM agents: never send touch N without checking the logged stage first (RUBRIC O6).

## Adapt this

- {{FILL: offer name + scope + fixed price — from BUSINESS-CONTEXT.md}} — replaces "Store Speed Sprint", €2,400, 2 weeks.
- {{FILL: target buyer + size band + where the list comes from}} — replaces DTC founders / 5–30k orders.
- {{FILL: the 3-minute homework recipe for YOUR offer}} — must yield one specific fact + one number per prospect in ≤ 3 minutes, or the offer needs a different observable symptom. Examples: marketing offer → their abandoned-cart email never arrived / last campaign date; dev offer → broken flow, console errors, LCP; strategy offer → pricing page contradiction, unreviewed competitor move.
- {{FILL: fallback bump proof point — strongest real before/after number, from case studies}}.
- {{FILL: signature — one-line credential that is TRUE (own SaaS/e-com numbers count: "we run our own store; this is what we fixed for ourselves first")}}.
- {{FILL: sending calendar — batch size per week (default 25/person), tracker location}}.
- Keep fixed: 3-touch structure and day spacing, word limits (RUBRIC O2), one question per email, plain text, give-first CTA, reply-branch table, hard stop after touch 3.
