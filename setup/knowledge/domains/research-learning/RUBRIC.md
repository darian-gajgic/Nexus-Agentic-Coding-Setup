# Research & Learning Rubric

> Frontier-judge scoping (2026-07-13): for the text-only frontier judge, a gate whose evidence cannot appear on the page and is not contradicted by the task's artifacts is UNVERIFIABLE-HERE (a note), not FAIL — the cjudge verdict contract governs: only binding in-scope gate FAILs and critical/high findings block a SHIP.

Score any research report or learning plan using this file alone — no taste required.
Procedure: run the gates (any FAIL → revise before scoring), score the dimensions 0–4,
scan the kill list. Definitions of tiers, rungs, and labels are in `PLAYBOOK.md`.

## Must-pass gates — binary

Research reports:

- **G1 SOURCED** — every load-bearing claim has an inline source + data date + access date. One orphan claim = FAIL.
- **G2 LABELED** — every load-bearing claim carries exactly one of `[confirmed]` / `[likely]` / `[uncertain]`. Any other confidence vocabulary = FAIL.
- **G3 DECISION-ANCHORED** — the decision the research serves is stated in the first 5 lines, with a date or trigger.
- **G4 NO OVERREACH** — no recommendation rests on an `[uncertain]` load-bearing claim unless the recommendation itself names that uncertainty and hedges the action accordingly.
- **G5 FACT/OPINION FENCE** — interpretation appears only in "Our read" blocks; no sentence mixes a cited fact with an opinion.
- **G6 FALSIFIABLE** — a "What would change our mind" section exists with ≥1 observable trigger per major conclusion.
- **G7 LIVE-VERIFIED** — no checkable fact sourced from model memory; every one traces to a fetched source (URL or document) with an access date.
- **G8 STAMPED** — the report carries its own date, time spent, stakes tier, and recorded prior.

Learning plans (additionally):

- **G9 OBSERVABLE GOAL** — the skill is defined as 3–5 "can do X to standard Y" capabilities, each scoreable with a named domain rubric. Any "understand/learn/get familiar" phrasing = FAIL.
- **G10 SHIPS WEEKLY** — every week names one real deliverable that leaves the building (business, client, prospect, or client-zero use). A consume-only week = FAIL.
- **G11 SELF-TESTED** — day-1 baseline plus ≥3 scheduled solo, timed self-tests with the scoring instrument named.
- **G12 KILLABLE** — the plan states the binary condition under which it gets stopped and rebuilt.

## Scored dimensions — 0–4

0 = absent · 2 = present but flawed (as described) · 4 = professional (as described).
1 and 3 = between the anchors.

1. **Decomposition & decision focus**
   - 2: decision named, but sub-questions overlap, exceed 5, or include ones whose answer wouldn't change the action.
   - 4: ≤5 atomic sub-questions; each classified FACT/EMPIRICAL/JUDGMENT; kill-shot question researched first; every sub-question passes the "would a different answer change the action?" test.
2. **Source quality**
   - 2: claims are sourced, but load-bearing ones sit at rung 3, with primaries uncited when they exist.
   - 4: every load-bearing claim at rung 1–2, or a stated reason why no higher rung exists; internal data used where it is the true primary.
3. **Verification rigor**
   - 2: multiple sources cited but independence never checked; vendor incentives unmentioned.
   - 4: every `[confirmed]` EMPIRICAL claim shows 3 sources passing the 3-part independence check; every rung-1/2 source carries an incentive note; negation queries were run and reported.
4. **Calibration**
   - 2: labels present but uniform (everything `[likely]`) or contradicting the definitions (single source marked `[confirmed]`).
   - 4: labels spot-check correctly against their definitions; prior recorded and explicitly compared with findings; conflicting sources reported as a finding, not averaged.
5. **Synthesis & clarity**
   - 2: the answer exists but sits after background; executive answer >5 sentences; sections in nonstandard order.
   - 4: ≤5-sentence executive answer first; findings scannable in under 2 minutes; length within the tier budget; zero filler sections.
6. **Actionability**
   - 2: recommendation is directional ("consider X") with no owner, number, or date.
   - 4: action + owner + numeric or dated trigger + revisit condition; falsifiers map one-to-one onto major conclusions.
7. **Reusability & honesty**
   - 2: gaps mentioned vaguely ("couldn't find much").
   - 4: dead ends listed with exact queries and as-of dates; source list carries rung labels; a stranger could resume the research without repeating work.

Learning plans: score dimensions 1 (capability focus), 5, 6, and 7 only; gates G9–G12 carry the rest.

Scoring bands (research reports, /28):
- **24–28** — ship (T3 still requires `cjudge`).
- **17–23** — revise the weakest dimension, re-score once.
- **≤16** — redo from decomposition; do not patch.
- Any gate FAIL overrides any score.

## Kill list — amateur markers

Any hit = fix before the artifact is used, and log it as a lesson.

1. A conclusion resting on one source and not labeled `[uncertain]`.
2. Citing Wikipedia, a listicle, an aggregator, or "the model said" for a checkable fact instead of the primary underneath it.
3. "Studies show / experts agree / research suggests" with no named study, year, or sample.
4. A price, version number, or legal claim with no date attached.
5. Triangulation theater: three citations sharing one origin (same press release, same dataset, or citing each other).
6. Prose confidence — "clearly", "definitely", "it is well known" — doing the work of a label.
7. The executive answer more certain than the findings underneath it.
8. A vendor's own benchmark or case study cited as neutral evidence without an incentive note.
9. A round number with no origin or method ("the market is $10B").
10. Zero gaps or dead ends reported — real research always has some.
11. "It depends" with no table of what it depends on.
12. A review sign-off with no listed differences and no rubric score ("LGTM").
13. A learning goal phrased as knowledge ("understand", "get familiar with") instead of a tested capability.
14. A plan week whose deliverable is a course, book, or "research" with nothing shipped.
15. A lessons-log entry with no transferable principle — a diary line, not a lesson.
16. A self-test done with AI assistance and reported as a solo score.
