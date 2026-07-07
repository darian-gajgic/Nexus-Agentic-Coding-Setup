> TEMPLATE EXEMPLAR — illustrative names/numbers; adapt via BUSINESS-CONTEXT.md

# Research report: Should we move our SaaS billing to a merchant of record?

| | |
|---|---|
| **Question** | Move InvoiceRadar billing from Stripe to a merchant of record (Paddle / Lemon Squeezy) to offload VAT & sales-tax compliance? |
| **Decision served** | We will decide the billing/compliance setup for the next 12 months by 2026-07-15 (before the Q3 pricing-page rework). |
| **Date / author / time** | 2026-07-05 · research agent + human review (A.) · 3.5 h |
| **Stakes tier** | T3 (tax/regulatory-adjacent → `cjudge` mandatory regardless of € size) |

## Answer first

Stay on Stripe for now — the compliance burden we feared does not exist yet, and switching
today would cost real money and subscribers to solve a problem we don't have. Our EU
cross-border B2C revenue (~€7,560/yr run-rate) is still under the €10,000 EU micro-business
threshold, so we may charge home-country VAT with zero extra filings [confirmed]. A merchant
of record would cost ~7.4% effective on our €19 price point vs ~3.0% today [confirmed], plus
a forced re-entry of payment details for all 95 subscribers [likely]. Overall confidence:
high on the legal/cost facts, low on migration-churn size — which is exactly why we
shouldn't pay that cost before we must. Two numeric triggers below reopen the decision.

## Prior vs. found

Prior (recorded 2026-07-02, before searching): "MoR is probably the obvious win for a
2-person team — expect to recommend switching" (confidence: medium).
Found: the opposite, twice over — we're under a threshold we didn't know existed, and the
switch has a hidden churn cost. Logged as calibration lesson: check thresholds before
pricing the cure.

## Findings

### SQ1 — What are our VAT/sales-tax obligations today, and when do they change? (FACT)

**Today: home-country VAT only. That changes when EU cross-border B2C passes €10,000/yr.**

- EU B2C digital services are taxed in the customer's country, BUT a union-wide
  €10,000/yr threshold lets micro-businesses charge home VAT instead; above it, one OSS
  registration replaces per-country registrations (European Commission — VAT rules for
  e-commerce & OSS portal, rules in force since 2021-07-01, acc. 2026-07-01). [confirmed]
- Our EU cross-border B2C run-rate: €7,560/yr — 35% of €21,600 ARR (own Stripe dashboard
  export, Jun 2026, acc. 2026-07-03). At current ~8%/mo growth it crosses €10,000 around
  Nov 2026 (own forecast — see Our read). [confirmed for the current number]
- EU B2B with a valid VAT ID reverse-charges to the buyer — not our liability (same EC
  source, acc. 2026-07-01). [confirmed]
- UK: B2C digital sales by non-established sellers require UK VAT registration from the
  first sale — no threshold (HMRC — VAT on digital services to UK consumers, acc.
  2026-07-01). UK is ~4% of revenue (€860/yr, own dashboard). [confirmed]
- US: SaaS is taxable in roughly 20+ states, but economic-nexus thresholds (commonly
  $100k or 200 transactions per state per year) sit far above our US volume (state DOR
  pages for our top-3 US states, spot-checked, acc. 2026-07-02; survey via Stripe Tax
  docs — vendor, incentive noted). [likely]

### SQ2 — All-in annual cost of staying on Stripe? (FACT + EMPIRICAL)

**Today ≈ €648/yr. After crossing the €10k threshold ≈ €1,540–1,840/yr plus ~12 h/yr.**

- Blended processing fee, observed: 3.0% of revenue = €648/yr — the fixed €0.25 hurts at
  a €19 price (own Stripe dashboard, Jun 2026, acc. 2026-07-03). [confirmed]
- Stripe Tax, if/when activated: 0.5% per transaction ≈ €108/yr (Stripe pricing page,
  acc. 2026-07-01). [confirmed]
- Accountant for quarterly OSS filings: quotes of €90/q and €150/q → €360–600/yr
  (2 written quotes, Jun 2026 — small sample). [likely]
- UK handling once relevant: agent-filed UK VAT ≈ €300/yr, vs dropping UK sales
  (−€860/yr revenue). Decision deferred to trigger date. [likely]
- Founder time for filings/invoicing hygiene: ~3 h/quarter (own estimate). [uncertain]

### SQ3 — All-in annual cost of a merchant of record? (FACT)

**≈ €1,607/yr at today's volume — 7.4% effective on a €19 sub — with compliance included.**

- Paddle: 5% + $0.50 per checkout (Paddle pricing page, acc. 2026-07-02). On €19 that is
  €0.95 + ~€0.46 = €1.41 ≈ 7.4%; ×1,140 charges/yr ≈ €1,607. [confirmed]
- Lemon Squeezy: same 5% + $0.50 headline (LS pricing page, acc. 2026-07-02); note: owned
  by Stripe since 2024 — roadmap/positioning risk worth watching (LS announcement,
  2024-07, acc. 2026-07-02). [confirmed]
- Both assume merchant-of-record status: EU OSS, UK VAT, US sales tax become their
  liability, not ours (Paddle & LS docs — vendors describing their own product; incentive
  noted, but this is the contractual core of the offering). [confirmed]

### SQ4 — Non-cost risks of switching? (EMPIRICAL)

**The real switching cost is subscriber re-authorization, not engineering.**

- Saved cards do not transfer from Stripe to a MoR (different legal merchant/acquirer):
  existing subscribers must re-enter payment details. Anecdotal migration reports put the
  loss at 3–10% of subscribers; at 95 subs that is €57–190 MRR gone (3 independent
  founder write-ups, 2023–2025, acc. 2026-07-03 — passes independence check: different
  companies, different migrations, no shared origin). [likely]
- Account holds / payout freezes at MoRs: 9 recent complaint posts traced back to only
  2 underlying incidents — amplification, not 9 data points (Reddit r/SaaS + X threads,
  2025–2026, acc. 2026-07-03; rung 4 → leads only). Base rate unknowable from UGC.
  Mitigation if we ever switch: keep the Stripe account alive, export billing data
  monthly. [uncertain]
- Checkout conversion impact of MoR overlays: vendor claims only, in both directions.
  No neutral data found — see Gaps. [uncertain]
- Engineering effort: 1–2 dev-days against our current billing abstraction (own codebase
  inspection, 2026-07-03). [likely]

## Our read

Interpretation, not sourced fact: the MoR pitch is aimed at teams already drowning in
multi-jurisdiction filings. We are pre-threshold: switching now pays ~€950/yr extra AND
risks a churn spike to insure against paperwork that legally does not apply to us yet.
The forecast that we cross the €10k threshold around Nov 2026 assumes growth holds at
8%/mo — treat the trigger number as the fact, the date as a guess.

## What would change our mind

1. EU cross-border B2C run-rate crosses **€8,500/yr** (buffer under the €10k line) —
   checked monthly from the Stripe dashboard.
2. US B2C revenue approaches any state's economic-nexus threshold, or UK B2C grows enough
   that registration is worth it — MoR then wins on multi-jurisdiction liability.
3. Stripe ships a true merchant-of-record product (watch Stripe changelog quarterly).
4. Paddle/LS drop the $0.50 fixed fee or add a low-ticket tier — re-run SQ3 math.
5. Credible data that forced-migration churn is <2% — removes the main switching cost.
6. Our accountant or a tax letter contradicts the €10k threshold reading — this report's
   legal reads are researcher-grade, not professional tax advice.

## Gaps & dead ends

- No neutral (non-vendor) data on MoR checkout conversion. Queries tried: "paddle
  checkout conversion study", "merchant of record conversion A/B", "stripe vs paddle
  conversion data" — vendor content and affiliate posts only, as of 2026-07-03.
- Accountant cost based on 2 quotes; range is wide. Get a third before the trigger fires.
- US state-by-state SaaS taxability not fully mapped — deliberately skipped, irrelevant
  below nexus thresholds.

## Recommendation

- **Action**: stay on Stripe; do not activate Stripe Tax yet; keep charging home VAT.
- **Owner**: A. — adds a monthly 5-minute check of EU cross-border B2C run-rate to the
  weekly-review sheet.
- **Trigger**: at €8,500/yr cross-border run-rate → register OSS + activate Stripe Tax,
  and re-run this decision with fresh MoR pricing (half-day, reuse this decomposition).
- **Revisit**: 2026-11-01 regardless, or on any "change our mind" item.

`cjudge` review: requested 2026-07-04 (T3, tax-adjacent). Passed with one amendment —
added falsifier #6 (professional-advice caveat) and the monthly threshold check.

## Sources (rung labels per PLAYBOOK hierarchy)

| Source | Rung | Incentive note | Accessed |
|---|---|---|---|
| European Commission — OSS / e-commerce VAT pages | 1 | none relevant | 2026-07-01 |
| HMRC — digital services VAT guidance | 1 | none relevant | 2026-07-01 |
| Own Stripe dashboard export (Jun 2026) | 1 | none — our own data | 2026-07-03 |
| Stripe pricing + Stripe Tax pages | 2 | vendor selling Stripe Tax | 2026-07-01 |
| Paddle pricing page / docs | 2 | vendor selling MoR | 2026-07-02 |
| Lemon Squeezy pricing page / acquisition post | 2 | vendor selling MoR | 2026-07-02 |
| 3 founder migration write-ups (2023–2025) | 3 | independent of each other — check passed | 2026-07-03 |
| State DOR pages (top-3 US states), spot-check | 1 | none relevant | 2026-07-02 |
| Reddit r/SaaS + X complaint threads | 4 | leads only, never load-bearing | 2026-07-03 |
| 2 accountant quotes (email) | 1 | selling their service | 2026-06-28 |

## Why this works

- **Answer first, ≤5-ish sentences, with the caveat that matters** — the reader can act
  from the first block; everything below is verification (Playbook 3.2; Rubric dim 5).
- **The recorded prior stayed in** — and it was wrong. That's the point: the calibration
  record is how juniors learn their own bias direction (Principle 2; Gate G8).
- **Kill-shot ordering** — SQ1 (the threshold) could have ended the research in 30
  minutes, so it went first. Note how SQ2–SQ4 all inherit context from it (Playbook 1.6).
- **Own dashboard cited as rung 1** — internal data is a primary source; juniors
  habitually search the web for numbers they already own (Rubric dim 2).
- **Independence handled both ways** — 3 founder write-ups counted as 3 because they
  passed the check; 9 complaint posts counted as 2 because they didn't (Principle 4;
  Rubric dim 3, kill-list 5).
- **Every number carries source + data date + access date** — including the boring ones.
  Prices and thresholds are volatile facts; the dates make the report refreshable
  (Principle 5; Gate G1).
- **Labels do real work** — the recommendation leans only on [confirmed] claims; the
  [uncertain] churn estimate is used to argue for *delay*, not for action (Gate G4).
- **Fact/opinion fence** — the growth forecast lives in "Our read", not in Findings, so
  a reader can't mistake a guess for a sourced claim (Gate G5).
- **Falsifiers are observable and owned** — each names who checks what, where, how often;
  "revisit date regardless" prevents the trigger from being forgotten (Rubric dim 6).
- **Dead ends listed with exact queries** — the next agent won't re-burn an hour on MoR
  conversion data that doesn't exist (Principle 7; Rubric dim 7).
- **Escalated despite small € size** — tax-adjacent = automatic T3. The cjudge amendment
  is shown, normalizing that frontier review adds things (Playbook: Escalation rule 2).

## Adapt this

- {{FILL: product name, price point, MRR, subscriber count — from BUSINESS-CONTEXT.md}}
- {{FILL: home member state and actual sales mix % (home / EU B2C / EU B2B / non-EU) — pull from the real payment dashboard, never estimate}}
- {{FILL: real current blended fee % from your dashboard export}}
- {{FILL: current-year threshold values and fee schedules — every price and threshold in this exemplar is illustrative and WILL be stale; re-fetch each from its rung-1/2 source and restamp access dates}}
- {{FILL: your accountant quotes (get ≥2) and your dev-effort estimate against your codebase}}
- {{FILL: trigger values — set the buffer at ~85% of whatever threshold applies to you}}
- {{FILL: owner initials and the recurring check location (weekly-review sheet, dashboard alert)}}
- Reuse the skeleton for any either/or infrastructure decision (hosting, email provider,
  fulfillment partner): SQ1 = what rules/thresholds actually bind us, SQ2/SQ3 = true
  all-in cost of each path, SQ4 = non-cost risks and switching costs.
