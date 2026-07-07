# SaaS Strategy Work — Quality Rubric

Apply to any SaaS strategy deliverable (positioning, pricing proposal, MVP scope, launch plan, metrics review) BEFORE it leaves the AI or a junior's hands.
Every check below is answerable yes/no or with a count — no taste required.
Companion: `PLAYBOOK.md` (how to produce the work this rubric scores).

## How to apply (agent procedure)

1. Run the kill list first — scan for the phrases; fix every hit before scoring.
2. Check all 9 gates in order. First FAIL → stop scoring, return the draft with the failed gate named.
3. Score D1–D7, one line of justification each (quote the sentence in the draft that earned the score).
4. Apply the scoring rule at the bottom of the dimensions section.
5. If the deliverable matches any trigger in `PLAYBOOK.md` → "Escalate to frontier review", route through `cjudge` even on a passing score.
6. Attach the filled score sheet (template at bottom) to the deliverable.

---

## Must-pass gates — do not deliver if ANY fails

- [ ] **G1 — Specific ICP.** Document names role + company size/type + observable situation. "Small businesses" or "startups" alone = FAIL.
- [ ] **G2 — Real alternatives named.** At least 2 alternatives the customer uses today, and one of them is non-software ("spreadsheet", "email", "do nothing"). Zero named alternatives = FAIL.
- [ ] **G3 — Next action stated.** Ends with concrete next step(s): who does what by when. "Consider exploring…" endings = FAIL.
- [ ] **G4 — Numbers are honest.** Every number is (a) from a cited source, (b) derived with the math shown, or (c) explicitly flagged "(verify current numbers)" or "illustrative". Any naked benchmark/market figure = FAIL.
- [ ] **G5 — A trade-off is stated.** At least one explicit "we choose X, which costs us Y" sentence. A plan with only upsides = FAIL.
- [ ] **G6 — Cuts have revisit triggers.** Everything deprioritized/cut carries an observable earn-it-back criterion. "Maybe later" = FAIL.
- [ ] **G7 — Fits a 2-person team.** No step requires headcount, budget, or channels we don't have per `~/knowledge/BUSINESS-CONTEXT.md`. "Hire a sales rep" / "run paid ads at scale" without budget line = FAIL.
- [ ] **G8 — No fabricated reality.** No invented customer quotes, names, or metrics presented as real. Illustrative examples are labeled illustrative. Any unlabeled invention = FAIL.
- [ ] **G9 — Format matches the ask.** One-pager fits on one page (~500 words); checklist is a checklist; requested sections all present. Wrong artifact shape = FAIL.

---

## Scored dimensions — 0–4 each

Score every dimension. 4 = exemplary, 2 = mediocre-but-usable, 0 = absent/harmful.

**D1. ICP & problem specificity**
- 2: ICP has a role and segment, problem described in general terms ("agencies struggle with client communication").
- 4: ICP has role + size + situation + named trigger event, problem stated in customers' own words with at least one verbatim quote or logged observation.

**D2. Falsifiability**
- 2: Claims are directional and untestable ("this will improve retention").
- 4: Each major claim has a metric, a threshold, and a timeframe ("activation +10pp within 2 cohorts, else revert").

**D3. Prioritization discipline**
- 2: Everything ranked, nothing removed; "P3" is where ideas hide instead of dying.
- 4: More items explicitly killed than kept, each kill with a one-line rationale and an earn-it-back trigger.

**D4. Evidence over opinion**
- 2: Reasoning from first principles and personal intuition only.
- 4: At least 3 pieces of observed evidence (interview quotes, support-ticket counts, funnel numbers, competitor pricing screenshots) doing load-bearing work in the argument.

**D5. Economic reasoning**
- 2: Price/effort mentioned but disconnected from value ("$29 feels right").
- 4: Value metric identified, value anchor computed (what the problem costs the ICP), price tied to anchor at a stated ratio; costs/effort compared against expected MRR impact.

**D6. Actionability**
- 2: Recommendations are themes ("improve onboarding").
- 4: Numbered steps with owner, effort estimate, and a measurable done-condition per step; a GLM-5.2 agent or a junior could start executing step 1 immediately without a clarifying question.

**D7. Differentiation logic**
- 2: Lists our features; superiority asserted ("more intuitive").
- 4: Names the specific alternative for the specific ICP, states the capability gap only we fill, and says who should NOT buy from us.

**Scoring rule:**
- Average ≥3.0 AND no dimension ≤1 → deliver.
- Average 2.5–2.9 → one revision pass targeting the two lowest dimensions, then re-score.
- Average <2.5 OR any dimension ≤1 → redo with `PLAYBOOK.md` open; do not polish, restart from the relevant playbook's step 1.

---

## Kill list — instant amateur markers

Presence of any item = revise before delivery. Replace as instructed.

1. "revolutionary / game-changing / cutting-edge / next-generation" → replace with the specific capability and who it helps.
2. "seamless / intuitive / user-friendly / delightful" (unverifiable adjectives) → replace with a measurable ("median 4 clicks to first invoice").
3. "all-in-one solution / one-stop shop" → replace with the ONE job we do better than anyone.
4. "for everyone / any business / all teams" → replace with the ICP from G1; name who it is NOT for.
5. "like [BigCo] but cheaper" → forbidden frame; reposition on niche or capability (PLAYBOOK hard rule).
6. "we only need 1% of the market" / "$X billion TAM" as justification → replace with a path to the first 100 customers, named channel by channel.
7. "users will love / customers want" without a source → attach the quote, ticket count, or funnel number — or delete the claim.
8. "studies show / research says / experts agree" with no citation → cite it or cut it.
9. "would you pay for this?"-style validation evidence ("8/10 said they'd use it") → replace with behavioral evidence (pre-orders, activation, retention).
10. "if we build it, they will come" plans — marketing section that is only "launch on Product Hunt" → replace with 3–5 named ICP channels + owner + cadence.
11. Feature lists as positioning ("we offer A, B, C, and D") → lead with the job outcome; features become proof points.
12. "freemium will drive viral growth" at our scale → replace with a paid trial or a concrete referral mechanic with the incentive math shown.
13. Roadmap dates promised >1 quarter out → replace with "now / next / triggers" framing.
14. Hedge stacking ("might potentially help to consider…") → one clear recommendation + the condition under which it's wrong.
15. Percentages with no base ("conversion up 50%") → always report base and n ("4% → 6%, n=210").

---

## Score sheet template (copy into the deliverable)

```
RUBRIC SCORE — <deliverable name> — <date>
Kill list: clean? Y/N (items fixed: …)
Gates: G1 _ G2 _ G3 _ G4 _ G5 _ G6 _ G7 _ G8 _ G9 _   (P/F each)
D1 ICP specificity:      _/4 — <quoted evidence>
D2 Falsifiability:       _/4 — <quoted evidence>
D3 Prioritization:       _/4 — <quoted evidence>
D4 Evidence use:         _/4 — <quoted evidence>
D5 Economic reasoning:   _/4 — <quoted evidence>
D6 Actionability:        _/4 — <quoted evidence>
D7 Differentiation:      _/4 — <quoted evidence>
Average: _._  → verdict: DELIVER / REVISE (D_, D_) / REDO
Escalation trigger matched? Y/N → cjudge run: link/none
```
