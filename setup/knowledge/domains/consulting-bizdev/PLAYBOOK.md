# Consulting & Business Development Playbook

Operating manual for selling and delivering client services (dev, marketing, strategy)
as a 2-person junior team. Read by AI agents drafting bizdev artifacts and by the humans
reviewing them.

- Specifics (services, rates, niche, capacity) live in `~/knowledge/BUSINESS-CONTEXT.md` — pull real numbers from there; every `€` figure below is an illustrative default.
- Tone rules live in `~/knowledge/STYLE-VOICE.md`.
- Nothing leaves the building without passing `~/knowledge/domains/consulting-bizdev/RUBRIC.md`.
- Worked artifacts: `examples/cold-outreach-sequence.md`, `examples/proposal.md`, `examples/discovery-call-guide.md`.

Agent pre-flight — run before drafting ANY bizdev artifact:

1. Identify the task type; open the matching playbook section below.
2. Pull real offer/rate/capacity data from `~/knowledge/BUSINESS-CONTEXT.md`. Data missing → ask the humans; never invent rates, claims, or client facts.
3. Draft against the matching exemplar in `examples/`.
4. Self-score against RUBRIC.md; fix every gate fail before showing a human.
5. Check the escalation list at the bottom; any match → route through `cjudge` before send.

## Operating principles

1. **Sell the diagnosis, not the service.** Prospects hire whoever describes their problem most precisely — precision of insight is the only credibility that needs no track record.
2. **Productize by default: fixed scope, fixed price, fixed deadline.** Hourly puts juniors in a rate-comparison contest they lose; a packaged outcome can't be rate-shopped.
3. **Do the homework before the hello.** Every outreach and proposal contains at least one verifiable, specific fact about THEIR business — personalization is proof of work, and proof of work substitutes for logos.
4. **Anchor price out loud on a call before it appears in writing.** A proposal that reveals price for the first time is a coin flip you don't get to watch.
5. **Never cut price without cutting scope.** An unexplained discount announces that the original price was fiction and invites the next demand.
6. **Speed is the junior's unfair advantage.** Reply within 4 business hours, ship visible value within 5 working days of kickoff — agencies can't match it, and responsiveness reads as competence.
7. **Qualify hard, walk away fast.** A bad-fit client costs roughly 3x their fee in rework, morale, and opportunity cost; willingness to lose a deal is a small team's only leverage.
8. **Silence kills projects, not mistakes.** Clients fire vendors for going dark, almost never for reporting a slip early with a new date.
9. **Money starts the clock, not the signature.** A client who won't pay a deposit was never a client; the deposit filters non-payers before they can cost anything.
10. **Every project must produce a showable artifact.** Case-study rights are negotiated at signing and baselines captured at kickoff — a junior portfolio is built deliberately, never accidentally.

## Task playbooks

### 1. Offer design — productizing a service

Why productized beats hourly for juniors: an hourly rate invites comparison to seniors
("why pay you €X/h?"); a fixed package is judged only against its outcome. It also caps
the client's risk, which is the biggest objection a junior has to overcome.

1. Pick ONE problem you have already solved at least once. Own SaaS / e-commerce / music work counts as evidence. A problem, not a skill.
2. Name the buyer precisely: role + company type + size band. Test: could you build a 50-person list of them in one afternoon? If no, go narrower.
3. Write the outcome in one sentence containing a number: "[measurable thing] in [Y weeks]."
4. Fix the scope: an included list AND a not-included list of at least 3 items. The exclusion list is what makes the price defensible.
5. Fix the timeline: 3 weeks or less for a first offer. Sales friction and delivery risk both scale with duration.
6. Fix the price (see playbook 5). One number, not a range.
7. Design the artifact the client physically receives: report, working code, dashboard, launched campaign. If you can't screenshot it, redesign it.
8. Add exactly one risk-reversal: phased kill-switch, paid pilot, or a scoped guarantee on things you ship.
9. Write the 1-line pitch: "[Outcome] for [buyer] in [timeline], fixed price." If it needs a second sentence, the offer isn't sharp yet.
10. Sell it 5 times before changing it. Iterate on evidence, not nerves.

Kill the offer draft if any is true:
- You can't name where 50 target buyers can be found (list source).
- Delivery depends on a skill neither of you has demonstrated at least once.
- The client can't verify the outcome without taking your word for it.

### 2. Prospecting + cold outreach

Worked sequence with reply-handling: `examples/cold-outreach-sequence.md`.

1. Derive the list filter from the offer: role, company type, size band, plus one OBSERVABLE symptom (slow site, no reviews, dormant blog, broken flow). Symptom-first lists convert; firmographic-only lists don't.
2. Build lists in batches of max 25 per person per week. Beyond 25, personalization quality collapses — at junior scale, depth beats volume.
3. Per prospect, do the 3-minute homework: find ONE specific, verifiable fact, with a number if possible (their LCP, review count, last post date, broken step). This artifact IS the personalization.
4. Log every prospect in {{FILL: CRM / tracker location}} before sending: name, company, fact found, date, sequence stage.
5. Send the 3-touch sequence: Touch 1 (day 0), bump (day 3–4), breakup (day 8–10). Then STOP — replies past touch 3 run under 1% and the reputation risk keeps climbing.
6. Send Tue–Thu, 08:00–10:30 recipient-local time. Never Monday morning, never Friday afternoon.
7. Run every email — including bumps — through RUBRIC.md gates before sending.
8. Answer every reply within 4 business hours. Branch per the reply table in the exemplar.
9. Friday review, 30 min: replies per 25 sent. Change ONE variable per week.

Thresholds:
- Target reply rate ≥ 8% by batch 3. Below 4% after 75 sends → offer/list mismatch; go back to playbook 1, don't polish copy.
- Fewer than 2 replies per batch → fix the specific-fact step (step 3), not the template.
- 5+ replies but no calls booked → CTA problem; lower the friction of saying yes.
- Batch > 50, or any target company > 1,000 employees → escalate first (see Escalation).
- Never send the same template to two people at the same company.

### 3. Discovery call

Goal: qualify or disqualify in 30 minutes and leave with a scheduled next step.
Full script, question bank, and scorecard: `examples/discovery-call-guide.md`.

1. Before the call (10 min): research; write 1 hypothesis about their problem and 1 question you genuinely can't answer from the outside.
2. Open with a frame (60 sec): agenda, timebox, "at the end we'll both decide if a next step makes sense — and it's fine if it doesn't."
3. Situation (5 min): current state, and "what made you take this call now?" — "why now" is the highest-signal question available.
4. Problem + impact (10 min): make them quantify. "What is this costing per month, roughly?" and "What happens if you do nothing for 6 months?" — no-decision is your real competitor, not other vendors.
5. Money + authority + timeline (5 min): ask directly. "Have you set aside a budget for this?" "Who besides you needs to say yes?"
6. Fit + price bracket (5 min): describe your approach in 2 sentences, then bracket: "Work like this usually lands between €X and €Y — is that the world you were imagining?" Watch the reaction. This is the anchor (principle 4).
7. Close to next step (5 min): schedule the concrete next event ON the call. "I'll send something over" is not a next step.
8. Same day: 5-line recap email — their words for the problem, their numbers, agreed next step with date.

Qualification: score every call 0–2 on six criteria (pain named, impact quantified, budget exists,
authority present, timeline real, we can deliver). Proceed at ≥ 8/12 with no zero on pain or budget.
5–7 → nurture. ≤ 4 → decline within 24h.

Walk away immediately if 2+ of these appear:
- Badmouths two or more previous vendors with zero self-reflection.
- Haggles on price before scope is defined.
- "Should be simple / shouldn't take long" — from their side.
- Asks for free spec work to "prove yourselves."
- Urgent deadline + vague goal.
- Real decision-maker will never join a call.

### 4. Proposal writing

Rule zero: the proposal is a receipt, not a pitch. Nothing in it — the price included —
should be new to the reader. No verbal price bracket on a call = not ready to write.
Full worked artifact: `examples/proposal.md`.

1. Write within 48h of the discovery call, while their words are fresh.
2. Structure, in order: situation (their words) → goals (their numbers) → approach → deliverables → timeline → investment (2 options) → success criteria → terms → next step with a date.
3. Situation section quotes their own phrases from the call. Target reaction: "they listened," not "nice template."
4. Offer exactly 2 options: the thing they asked for, and the thing plus a logical extension at 1.5–1.8x. Two options turns "yes or no?" into "which?"; a third option adds a week of dithering.
5. Present the larger option first (anchor).
6. Success criteria: measurable, dated, honest about control. Guarantee leading indicators (things you ship), never lagging ones (their revenue).
7. Include exactly one risk-reversal: phased kill-switch with a price ("stop after Phase 1, pay only €X"), paid pilot, or scoped guarantee.
8. Standard terms — the protective set, all present, every proposal:
   - 50% deposit to schedule; the deposit starts the clock.
   - Remainder net 7 on delivery.
   - Late client input shifts dates 1:1, stated in writing.
   - Exclusion list of ≥ 3 items.
   - Changes via swap-or-add (see playbook 6, step 5).
   - IP transfers on final payment, not before.
   - Case-study rights, anonymized by default.
   - Proposal expires in 14 days.
9. Deliver on a 15-min walkthrough call, screen-shared — never as a naked attachment. Watch their face at the price.
10. No answer by expiry minus 3 days → one nudge referencing the expiry. After expiry: close it in the CRM and tell them it's closed. Scarcity only works if it's real.

### 5. Pricing services

Heuristics, in order of preference:

1. Value-based, when impact was quantified on the call: fee ≈ 10–20% of the 12-month value the client themselves named. If their expected value is under 3x your fee, don't pitch that price — you'll defend it forever.
2. Day-rate math as a FLOOR, never a quote: target annual income ÷ 100 = day-rate floor. Estimate days honestly, multiply by 1.5 (junior estimates run ~40% under, reliably), price the package at or above that. Never say the day rate out loud.
3. Fixed price only with fixed scope. Quote a range only when scope is a range, and bind each end of the range to a named scope.

Junior-specific rules:
- Never justify price with your costs or hours — justify with their outcome. The moment you explain hourly math, the deal converts to hourly in the client's head.
- Underselling is not humility; it's a positioning claim ("cheap because unsure"). To win early deals, discount only with a NAMED, EXPIRING reason: "founding-client rate, first 3 clients, in exchange for case study + testimonial." The named reason preserves the real price.
- Asked "what's your hourly rate?" → "We price by project so you know the total before we start. Work like this typically runs €X–€Y."
- Raise prices 20–25% when 3 of the last 4 proposals closed with zero price pushback. No pushback = underpriced.
- Any price change to an existing client, or any discount > 10% → escalate (see below).

### 6. Client delivery & communication cadence

1. Kickoff within 5 working days of the deposit landing. Fixed agenda: restate goals, confirm success criteria, CAPTURE AND SAVE baseline metrics (you cannot reconstruct baselines later — this is the case study's raw material), name one point of contact per side, agree the update slot, hand over the access checklist.
2. Access checklist gets a deadline: "items 1–6 by {{date}}; each late day shifts delivery a day." Enforce kindly, in writing, every time.
3. Weekly update, same day and hour every week, written, max 10 lines: Done / Next / Blocked / Decisions needed from you / status green-amber-red. Send when everything is fine. Send ESPECIALLY when behind — report a slip the day you know it, with a new date and the countermeasure.
4. First visible value inside week 1: a finding, a prototype, a quick win. Trust is set in the first 20% of a project and only defended afterwards.
5. Scope change — the swap-or-add script, verbatim: "Happy to. That's outside the current scope, so two options: we swap it for [comparable item], or we add it for €X and Y extra days. Which works better?" Never a bare yes, never a bare no.
6. The FIRST out-of-scope ask gets the script. Absorb three silently and you've trained the client; the fourth becomes a fight.
7. Closeout call on delivery: walk success criteria one by one, capture after-metrics, get their reaction in writing, then — same call — run the case-study and referral asks (playbook 7). Final invoice goes out the same day.
8. Overdue invoice procedure — start the day it goes late, no embarrassment, no delay:
   - Day 1: friendly one-liner, invoice reattached. Assume oversight.
   - Day 7: phone call, not email. Get a payment date out loud.
   - Day 14: pause work, in writing: "we'll resume on receipt." Pausing is the leverage; tone warm, terms firm.
   - Day 30: escalate via `cjudge` before any formal step (collections letter, legal).
   - Never hand over final IP or publish deliverables while an invoice is > 14 days overdue (the terms say IP transfers on final payment — use that clause).

### 7. Case study creation + referral asks

Case studies are the junior team's compounding asset. Every project must attempt one.

1. Groundwork at SIGNING: case-study clause in the terms (anonymized allowed by default; named requires their approval).
2. At kickoff: save baseline metrics to {{FILL: project records location}}.
3. Ask at the PEAK moment — the day a win lands, or the closeout call. Not weeks later; gratitude has a half-life measured in days.
4. Testimonial ask, verbatim: "Would you be open to a 3-line testimonial? To make it painless, I'll draft something from your own words on our calls — edit anything, veto everything." Drafting it yourself moves completion from roughly 20% to 80%.
5. Case study structure, 1 page max: client context (1 paragraph) → problem with baseline numbers → what we did (3–5 bullets) → results with after-numbers and dates → client quote. No adjective doing a number's job.
6. Weak results → publish an honest process write-up or nothing. Never inflate: a junior gets exactly one credibility bankruptcy.
7. Referral ask, on the closeout call, AFTER the testimonial yes: "Who's one person you know wrestling with something like this? I'll write a 3-line intro you can just forward." One name, never "anyone you know." Write the forwardable email the same day.
8. Referred prospects skip the cold sequence — straight to the discovery playbook. Report the outcome back to the referrer either way; it's their reputation on loan.
9. Publish approved case studies to {{FILL: portfolio / site location}} and promote the strongest number into the outreach templates.

## Junior mistakes

1. Answering "what do you charge?" with an hourly rate → give a project range tied to scope: "Work like this runs €X–€Y depending on [scope driver]."
2. Sending the proposal with the price unseen → bracket the price verbally on the call first; the proposal only confirms it.
3. Discounting at the first flinch → hold price, adjust scope: "We can hit that budget by removing [item]."
4. Silently over-delivering "to keep them happy" → run the swap-or-add script on the FIRST out-of-scope ask.
5. Apologizing for following up ("sorry to chase…") → a follow-up is a service to a busy person: context + question, zero apology.
6. Giving up after one email → most replies arrive on touches 2–3. Finish the sequence, then genuinely stop.
7. Talking tools and features ("we use React / HubSpot") → talk outcomes: which of THEIR numbers moves, and why.
8. Starting work on a verbal yes → the deposit starts the clock. No exceptions, including "friendly" clients.
9. Treating "no budget" as dead → ask: "No budget ever, or not this quarter? What number would it need to fit inside?"
10. Hiding that you're a 2-person team → sell it: "You get the two people doing the actual work. No account managers, 4-hour response times."
11. Taking every deal because the pipeline is thin → score it; a bad client costs ~3x the fee. Thin pipeline is fixed by playbook 2, not by bad clients.
12. "Just checking in" follow-ups → every follow-up adds one new thing (a finding, a relevant result, a real deadline). No new thing = no email.
13. Writing 400-word outreach to look thorough → under 120 words. Length signals your time is cheap.
14. Promising results you don't control ("we'll double your revenue") → guarantee what you ship; measure and report what they get.
15. Naming yourselves "junior" as an apology ("we're just starting out, so it's cheap…") → name the founding-client rate and what it buys (case study rights), or say nothing.
16. Leaving verbal agreements verbal → confirm every decision from every call in writing the same day. The recap email is the project's contract memory.
17. Cutting price before anyone asked ("I know it's a lot, we could also do less…") → name the price, then stop talking. The first one to speak after a price names the discount.

## Escalate to frontier review when…

High-stakes = expensive to reverse, legally binding, or reputation-risking. Route these
through `cjudge` for a second review BEFORE sending. Attach the artifact, the RUBRIC.md
self-score, and one line of context per item.

- Any proposal over €2,500 {{FILL: confirm threshold against real rates}} or over 1.5x the largest deal closed to date.
- Any deviation from the standard terms set (playbook 4, step 8) — above all liability, IP, payment terms, or signing the client's own contract paper.
- Any discount > 10%, any price change to an existing client, any change to public rates.
- Outreach batches > 50 recipients, any company > 1,000 employees, or any automation that sends without a human look.
- Firing a client, chasing seriously late payment, or anything touching a legal threat — draft, review, then send.
- Case studies naming a client, before publication.
- Any deal where the honest internal note reads "not sure we can deliver this" — review the deal, not just the document.

If in doubt whether something is high-stakes: it is. The review costs minutes; the mistakes above cost clients.
