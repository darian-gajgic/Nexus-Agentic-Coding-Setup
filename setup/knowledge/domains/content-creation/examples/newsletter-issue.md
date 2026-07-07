# Exemplar: newsletter issue

> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

Demonstrates PLAYBOOK playbook 3 (newsletter production). One core idea, personal open,
single CTA, deliberate PS. Illustrative newsletter: "The Two-Person Company," a weekly
operator letter from a 2-person SaaS/consulting team. Issue length: ~600 words (band: 400–800).

---

## Subject line candidates (write 5, send 1)

1. `We almost wasted 6 weeks building this` ← **chosen**
2. `The 2-week test that killed our best feature idea`
3. `Sell it before you build it`
4. `9 people clicked. That saved us 6 weeks.`
5. `Our roadmap was wrong (here's how we found out for $0)`

Why #1: names a loss (6 weeks), creates an open loop ("this"), 34 characters — safe against
mobile truncation, and it's true to the body. #3 is the thesis, but a thesis is a lecture;
#1 is a story. #4 is the strongest curiosity play but risks reading as bait if the body
doesn't pay it off in the first lines — usable as the A/B variant.

How the five score against playbook 3 step 2 criteria (this is the selection method, shown):

| # | Chars ≤45 | True to body | Specific (number/name) | Open loop | Verdict |
|---|---|---|---|---|---|
| 1 | 38 ✓ | ✓ | ✓ (6 weeks) | ✓ ("this") | send |
| 2 | 45 ✓ | ✓ | ✓ (2-week) | partial — reveals the mechanism | bank |
| 3 | 27 ✓ | ✓ | ✗ | ✗ — thesis, no tension | reject |
| 4 | 40 ✓ | ✓ | ✓ (9, 6 weeks) | ✓ strongest | A/B variant |
| 5 | 47 ✗ | ✓ | ✓ ($0) | ✓ | trim or reject |

## Preview text candidates (write deliberately — it's the second subject line)

1. `The two-week test we now run before building anything.` ← **chosen** (54 chars)
2. `A landing page, 40 emails, and an awkward lesson.` (49 chars)
3. `How to let customers vote with their calendars, not their words.` (64 chars)

Never let this default to "View in browser" or the first body line.

---

## Issue body

**Subject:** We almost wasted 6 weeks building this
**Preview:** The two-week test we now run before building anything.

---

Hey — Dario here.

Three Mondays ago, Mika and I had a roadmap meeting that nearly cost us six weeks. Four different customers had asked for a client portal — a white-labeled login where *their* clients could view live dashboards. Four requests felt like a mandate. We'd sketched the data model by lunch.

Then we did the thing this issue is about, and the portal is now dead. Here's the test.

**The two-week test: sell it before you build it.**

Before anything gets more than a day of build time, it has to survive two weeks of being sold as if it already existed:

1. **Day 1:** One landing page describing the feature as real, with a "Get early access" button. Two hours of work, no code behind it.
2. **Day 2:** Email the people who asked for it — plus 40 more customers in the same segment. Not "would you use this?" but "this is coming — want in?" Asking for a click costs the reader something; asking for an opinion costs nothing, which is exactly what opinions are worth.
3. **Days 3–14:** Everyone who clicks gets one follow-up: a 15-minute call invite to shape the feature, and one question — "what would this replace for you?"

Then count three numbers: clicks, booked calls, and the replacement answers.

Our portal scored: 9 clicks out of 44 emails, 1 booked call, and the replacement answers were all versions of "nothing, it'd just be nice." That's not a feature. That's a compliment.

The kicker: two of the four customers who originally *asked* for the portal didn't even click. What people request in a friendly call and what they'll interrupt their Tuesday for are two different products. Calendars don't flatter you; conversations do.

Kill thresholds we now use — steal them: under 20% click-through from people who *personally asked*, or zero booked calls, and the feature goes to the graveyard doc. The six weeks went into report scheduling instead — which, funny enough, 11 people clicked on from a single test email we almost didn't send.

Total cost of learning all this: one landing page, 44 emails, $0.

**→ [Get the two-week test kit]** — the landing-page skeleton, both email scripts, and the scoring sheet, as a copy-paste doc. *(single CTA — everything else in this issue is a link-free read)*

See you next Thursday,
Dario & Mika

**PS —** What's on your roadmap right now *only* because someone asked nicely? Hit reply and tell me — I read every one, and next issue features the best graveyard story (anonymized if you want).

---

## Pre-send checklist, as run for this issue (playbook 3, step 6)

- [x] Test-send to self, read top to bottom on a phone before anything else.
- [x] Every link clicked from the test send (1 body CTA — the only link in the issue).
- [x] Personalization fallback set (no first name on file → "Hey —" not "Hey ,").
- [x] Preview text set manually — confirmed it doesn't default to "View in browser."
- [x] Unsubscribe link present and working.
- [x] Kill-list grep run against RUBRIC.md — zero matches.
- [x] RUBRIC gates + score logged: 26/32, verdict PUBLISH.
- [ ] `cjudge` review — **required here** (full-list send = PLAYBOOK escalation trigger 5) before scheduling.

## Why this works

- **One core idea, survivable in 3 lines.** If the reader stops after "sell it before you build it," they still got the issue's value — PLAYBOOK playbook 3 step 1. Everything after is proof and mechanics, not a second idea.
- **Subject line names a stake, not a topic.** "We almost wasted 6 weeks" (loss, story) beats "How to validate features" (category, lecture). Written 5, sent 1 — the sprint is the method, per playbook 3 step 2; the runner-up is banked as the A/B variant.
- **Personal open is a real dated event, 3 sentences, already inside the story.** No "hope you're well" (kill list), no weather. The open *is* the setup — by sentence two the reader knows the tension. Principle 3: lead with the claim.
- **The idea is operational, not aspirational.** Numbered days, a click threshold (20%), a kill rule, and the exact ask-wording. RUBRIC actionability = 4: a reader could run this test tomorrow without asking us anything.
- **The twist carries the shareability:** "two of the four who asked didn't click." That line is the retellable unit (principle 2) — it's what a reader quotes to their cofounder. Every issue needs one line that works out of context.
- **Numbers are small and honest** (9 clicks, 44 emails, $0). Small true numbers outperform big vague ones for trust — principle 4. A 2-person team claiming enterprise-scale data would fail the sniff test.
- **Single CTA, temperature-matched.** Newsletter readers are warm (principle 9), so the ask is a free artifact that extends the issue — not a product pitch. The body contains no other links, which makes the one link legible as *the* next step.
- **PS does the second job without breaking the single-CTA rule.** The PS is the second-most-read line (playbook 3 step 5): here it's a reply prompt engineered for deliverability and for content supply — replies become next issue's material. The "featured next issue" promise gives replying a selfish payoff.
- **Sign-off is two named humans.** A 2-person company's structural advantage is that a reader can reply and reach the actual operator — the format spends that advantage on purpose.
- **Subject and preview are a two-line unit, not two attempts at one line.** The subject opens the loop ("this"); the preview names the payoff category ("the two-week test") without closing the loop. Pairing them is why the preview is written after the subject is chosen — playbook 3 step 3.
- **The scoring table above the fold of this file is deliberate.** Juniors (and GLM) copy what they see first: showing the selection *method* — not just the winning line — is what makes this file a template rather than a sample. Reuse the table columns verbatim for every issue.
- **Thresholds inside the story do double duty.** "Under 20% click-through → graveyard" teaches the reader a rule *and* proves we run one — a single line scoring both actionability and proof density on the RUBRIC.

## Adapt this

- {{FILL: newsletter name + sender names}} — "The Two-Person Company," Dario & Mika are placeholders; use real names per BUSINESS-CONTEXT.md. Send from a human name, not the brand.
- {{FILL: the real event}} — the open must be a true, recent, dated moment. If nothing happened this week, pull from the graveyard/decision log — never invent a scenario (kill list: fake personas).
- {{FILL: the core idea}} — swap the two-week test for this week's single lesson. Test before writing: can you state it in ≤20 words and does it survive a 3-line summary?
- {{FILL: your numbers}} — replace 44/9/20% with real counts. If you lack numbers, the issue isn't ready — bank it and run the experiment first.
- {{FILL: CTA artifact}} — kit/template/checklist that packages the issue's idea; destination per current funnel priority in BUSINESS-CONTEXT.md.
- {{FILL: PS prompt}} — a reply question the reader can answer in one sentence. Rotate: question → teaser → soft product mention, at most one product-PS per month.
- {{FILL: cadence + day}} — "next Thursday" assumes weekly; state your real cadence and honor it (principle 8).
- Voice pass per STYLE-VOICE.md — this exemplar runs casual-operator; tighten or loosen contractions, slang, and emoji policy to the documented voice.

**Reusable issue skeleton (any week, any pillar):**

```
SUBJECT   5 candidates → score table (chars / true / specific / open loop) → send 1, bank 1 as A/B
PREVIEW   3 candidates, 40–90 chars, written last so it complements the chosen subject

OPEN      2–3 sentences. A real dated event from our week that sets up the tension.
          Test: does sentence 2 already contain a stake (time, money, mistake)?

TURN      "Here's the test/rule/lesson." One bolded sentence — the ≤20-word takeaway.

MECHANISM Numbered steps or a short story beat-by-beat. Include: exact wording we used,
          one threshold ("under 20% → kill it"), and the cost ("2 hours, $0").

TWIST     The one retellable line — the fact that surprised US. If the issue has no
          twist, it's a tip, not a story; bank it and pick another idea.

CTA       One link, warm-temperature ask (artifact > pitch). No other links in the body.

SIGN-OFF  Real names, real cadence promise.

PS        Secondary job only: reply prompt (default) / teaser / soft product line.
          Rotate; max one product-PS per month.
```

Weekly time budget for this skeleton: 90 minutes door-to-door (playbook 1 calendar, Thursday). Overrun means the idea wasn't banked with proof attached — fix that on Friday, not on Thursday.

**Scoreboard per issue (log Friday, per playbook 3 step 7):**

- Replies — count and quote the best one into the idea bank.
- CTA clicks — unique clicks on the single link.
- Unsubscribes — a spike over 2× baseline means the subject over-promised or the list imported wrong segment.
- Ignore open rate except as a week-over-week trend (privacy proxies inflate it — verify current specifics).
