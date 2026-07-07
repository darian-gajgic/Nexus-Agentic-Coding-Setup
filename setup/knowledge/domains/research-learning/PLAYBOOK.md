# Research & Learning Playbook

Who this serves: the AI agents doing research for the business, and the two humans
learning to operate at professional level by reviewing that work. Same playbook for
both — the agent executes it, the humans internalize it.
Business specifics: `~/knowledge/BUSINESS-CONTEXT.md`. Report voice: `~/knowledge/STYLE-VOICE.md`.
Quality gate for outputs of this domain: `RUBRIC.md` (same folder).

## Operating principles

1. **Find the decision behind the question.**
   Why: research that can't change an action is entertainment; the decision defines when you're done.
2. **Write your prior before you search.**
   Why: surprise is the only reliable signal that you learned something — or are being fooled; without a recorded prior you can't feel it.
3. **A model's memory is a rumor from a smart friend.**
   Why: great for where to look, never for what is true — every fact that matters gets verified against a live source.
4. **Two sources that copy one press release are one source.**
   Why: independence means different origin of the data, not different URL; page-1 consensus is often one announcement refracted.
5. **Undated facts are decaying facts.**
   Why: prices, versions, laws, and rankings rot silently; the date tells the next reader whether to trust or refresh.
6. **Research until the decision is safe, not until you're comfortable.**
   Why: comfort has no stopping point; stakes tiers and time-boxes do.
7. **Absence of evidence is a deliverable.**
   Why: "searched X, Y, Z; nothing newer than 2024" saves the next person the same three hours and marks the real frontier.
8. **If two good sources disagree, the disagreement is the finding.**
   Why: averaging conflicting numbers hides the risk the reader most needs to see.
9. **You learn from AI output only if you predict before you look.**
   Why: reading polished work produces nodding, not skill — the diff between your guess and the output is the lesson.
10. **Ship weekly or the learning is fake.**
    Why: real artifacts with real consequences are the only feedback loop that can't be gamed; courses defer feedback forever.

## Task playbooks

### 1. Decomposing a research question

Use when: any ask that can't be answered from one authoritative page in under 10 minutes.

1. Name the decision. Rewrite the ask as: "We will decide ___ by ___ (date)."
   Can't? Ask the requester: "What will you do differently depending on the answer?"
   Still no decision → park it in a curiosity queue; do not research.
2. Set the stakes tier — it drives every downstream budget:
   - **T1** — reversible or <€100 impact → 30 min budget, lighter sourcing, no escalation.
   - **T2** — costs a person-week or €100–1,000 if wrong → half-day budget, full verification protocol.
   - **T3** — >€1,000, contractual, legal/tax/regulatory, or public claims → full protocol + `cjudge` (see Escalation). {{FILL: rescale € thresholds when revenue changes; keep them written in BUSINESS-CONTEXT.md}}
3. Write your prior: expected answer + confidence (low/med/high), one sentence. Keep it in the report — never delete it after; it is the calibration record.
4. Split into sub-questions. Each must pass all three checks:
   - [ ] Answerable with a fact, number, or named source (a stranger could tell it's been answered).
   - [ ] Changes the decision (if every possible answer leads to the same action → cut it).
   - [ ] Atomic (contains no "and"; can't be half-answered).
5. Classify each sub-question — the class picks the method:
   - **FACT** — has a system of record (a price page, a law text, our own dashboard) → find that record; done at 1 primary source + date.
   - **EMPIRICAL** — contested or measured in the world (market size, conversion rates, "is X reliable") → triangulate ≥3 independent sources.
   - **JUDGMENT** — depends on our values/risk appetite → build a criteria table; more searching cannot answer it.
6. Order by kill-shot: research first the sub-question most likely to end the whole investigation (hard blockers, threshold checks).
7. Cap at 5 sub-questions. Need more → it is really several decisions; split the brief.
8. Write the decomposition at the top of the working doc before the first search.

### 2. Source finding + verification

Source hierarchy — always cite the highest rung you can reach:

| Rung | Class | Examples | Allowed use |
|---|---|---|---|
| 1 | Primary | official price page, law text, filing, changelog, the study itself, raw data, our own dashboards | load-bearing facts |
| 2 | Official | vendor docs, government statistics, standards bodies | load-bearing, note the incentive |
| 3 | Reputable secondary | established trade press, peer-reviewed reviews, named expert with methodology | supporting evidence |
| 4 | Blogs / UGC / forums | Reddit, YouTube, Medium, tweets | leads and failure anecdotes only — never load-bearing |

LLM output (any model, including this one) has **no rung**: it is a search suggestion, not a source.

1. Per sub-question, decide the target rung before searching (FACT → rung 1; EMPIRICAL → plan ≥3 independent at rung ≤3).
2. Search wide: 3–5 query variants — synonyms, competitor names, year-qualified. Always run the negation query too: "<thing> problems", "migrating away from <thing>", "switched from <thing>". Failure evidence is under-indexed; docs show happy paths, forums show what breaks.
3. Trace UP: for every secondary claim you want to use, find what it cites and cite that. Cites nothing → treat as rung 4.
4. Independence check before counting toward triangulation — all three must hold:
   - [ ] Different author/organization.
   - [ ] Different underlying data or event.
   - [ ] Does not cite the other candidates or share their common origin.
   Any check fails → the sources count as one.
5. AI-era hygiene:
   - Never ship a fact that matters from model memory — prices, dates, versions, laws, statistics, names, quotes. Fetch a live source for each one.
   - Sludge screen before trusting a page: named human author? publication date? cites anything? contains data not found elsewhere? If ≥2 answers are "no" → discard as probable SEO/AI filler.
   - Quotes and statistics get exact-match verification: find the sentence or number in the source itself, not in a page about the source.
6. Date-stamp everything — two dates per claim: when the fact was true (data date) and when you checked (access date). Inline format: `(Source, data date, acc. YYYY-MM-DD)`.
7. Note incentives: for each load-bearing rung-1/2 source, one clause on who benefits if it's believed. Vendor benchmark, sponsored study, affiliate review → downgrade one rung.
8. Log dead ends as you go: exact queries tried, what wasn't found, as-of date. They go in the report.

Stop criteria — stop at the first that fires:
- FACT confirmed at rung 1 with a fresh date.
- 3 independent sources agree within tolerance → label [confirmed].
- Two search rounds yield only rung-4 material → label [uncertain], report the gap. More searching will not upgrade the rung.
- Time-box hit → ship what you have with honest labels. Never silently extend the box.

### 3. Synthesis + written report

Structure, in this order, no exceptions (worked example: `examples/research-report.md`):

1. Header: question, the decision it serves, date, author (model or human), time spent, stakes tier.
2. **Answer first**: ≤5 sentences — recommendation + overall confidence + the one caveat that matters most.
3. Prior vs. found: the pre-search prior, one line, and where reality diverged.
4. Findings: one block per sub-question — finding in bold, evidence with inline citations, confidence label.
5. **Our read**: interpretation fenced in its own labeled block. Never interleave opinion and cited fact in one sentence.
6. **What would change our mind**: ≥1 concrete, observable falsifier per major conclusion.
7. Gaps & dead ends.
8. Recommendation: action + owner + trigger (a number or date) + revisit condition.

Rules:
- Confidence labels — fixed vocabulary, on every load-bearing claim:
  - `[confirmed]` — rung-1 system of record, or ≥3 independent sources agreeing.
  - `[likely]` — 2 independent sources, or 1 strong source plus consistent circumstantial evidence.
  - `[uncertain]` — single source, conflicting sources, or inference. Not shameful — mandatory honesty.
- No naked numbers: every figure carries source + data date inline.
- Recommendation strength ≤ evidence strength: "do it now" cannot rest on an [uncertain] load-bearing claim (RUBRIC gate G4).
- "It depends" is banned unless followed by the table of what it depends on.
- Length: T1 = half a page. T2 = 1–2 pages. T3 = what the decision needs; the executive answer stays ≤5 sentences.
- Voice per `~/knowledge/STYLE-VOICE.md`: plain, direct, zero hedging fog.

### 4. Designing a learning plan

Goal: take one junior to working-professional in ONE skill in 90 days by shipping real
work with AI as the senior partner. Worked example: `examples/learning-plan-90d.md`.

1. Define "working professional" as 3–5 observable capabilities: "can DO X to standard Y", each scoreable by a stranger using the domain's RUBRIC. "Understands X" is banned phrasing.
2. One skill per person per quarter. Two parallel skills = two half-skills.
3. Day-1 baseline: attempt a representative deliverable solo (no AI), timed, score it against the domain rubric, file it. It is the before-photo for week 13.
4. Build backwards from the capabilities → 12 weekly deliverables, every one a real business artifact (shipped to the business, a client, or a real prospect; your own business counts as client zero). No tutorial weeks. Consuming (courses, books, videos) is capped at 20% of weekly skill time and must attach to that week's deliverable.
5. Weekly engine, fixed: Monday 30-min brief (deliverable + one technique to practice + predicted rubric score) → build midweek with AI in its assigned role → Friday review using playbook 5 → log lessons.
6. AI-role ratchet across the quarter — one axis at a time, never two:
   - Phase 1: junior directs, AI drafts, junior does final pass and full predict-then-compare (learn by reviewing the best).
   - Phase 2: junior drafts, AI critiques against the rubric.
   - Phase 3: junior works solo, AI reviews only the finished artifact.
   Advance a phase when 2 consecutive deliverables score ≥3 average on the domain rubric.
7. Self-tests weeks 4, 8, 13: solo, timed re-do of a representative deliverable; plot the rubric score. This is the spaced-review backbone — old material returns as new tests.
8. Kill/rebuild criteria (binary): 2 consecutive weeks without a shipped deliverable, or self-test score flat from week 4 to week 8 → stop, diagnose (deliverables too big? projects fake? missing prerequisite?), rebuild the remaining weeks. A sunk plan is not an argument for continuing it.

### 5. The review-and-learn loop for AI output

The single highest-leverage habit in this file. Run it on any artifact worth learning
from: client-facing, novel (first of its kind here), or inside your quarter skill.

1. **PREDICT** (5–15 min, before opening the AI's version): write your own skeleton — structure, key points, the numbers you expect, the call you would make. No peeking.
2. **COMPARE**: read the AI's version. List ≥3 concrete differences (structure, content, emphasis, numbers). Zero differences listed = no review happened (RUBRIC kill-list item).
3. **CLASSIFY** each difference:
   - AI better → name the principle that makes it better; lesson candidate.
   - Yours better → fix the artifact AND check whether PLAYBOOK/RUBRIC would have caught it; if not, propose the missing rule.
   - Unclear → step 4.
4. **ASK-WHY** protocol: ask the AI "why X and not Y?" — then verify the answer. Does it cite a playbook principle, a rubric line, or a checkable source? A fluent justification with no checkable anchor is confabulation: treat the point as open; escalate if load-bearing.
5. **SCORE** the artifact against the domain RUBRIC yourself before seeing any AI self-score. Then have the AI score it. A gap ≥2 points on any dimension is the week's lesson; on a T3 artifact, resolve via `cjudge`.
6. **LOG** 1–3 lessons per review in `~/knowledge/feedback/<name>-lessons.md`, one line each:
   `date | situation | what I'd have done | what won | transferable principle`
7. **PROMOTE**: weekly, any lesson that has appeared twice graduates into the relevant domain PLAYBOOK or RUBRIC as a rule. The Business Brain compounds only when lessons become checklist lines.
8. **Never approve what you can't defend.** If you couldn't explain to a client why the artifact is right, the review isn't finished: either learn the missing check now or escalate. Silent approval is the amateur move.

Depth by stakes: T1 → rubric scan only (predict-compare everything and you'll burn out). T2 → full loop. T3 → full loop + `cjudge`.

### 6. Personal development cadence

Minimum viable system: 2 files + a calendar hold. Over 45 min/week total = theater; cut it.

1. **Quarterly** (90 min, both people): each picks 1 skill and writes the observable
   professional definition (playbook 4, step 1) into `~/knowledge/feedback/goals-<quarter>.md`.
   Renew or kill last quarter's skill based on the week-13 self-test score, not on vibes.
2. **Weekly** (Friday, 25 min, timeboxed, calendar-held): answer 5 questions in writing, 1–2 lines each:
   - What shipped this week? (link it)
   - Rubric score vs. my predicted score?
   - Top lesson? (goes to the lessons log)
   - Next week's deliverable? (named, sized to one week)
   - Anything blocked >1 week? (blocked 2 weeks → hand it to the other person or redesign it)
3. **Monthly retro** (60 min, both people):
   - Re-read the month's lessons. Any lesson logged twice and violated again → the fix is a checklist or rubric change, never "try harder".
   - Re-score yourselves against the quarter definitions.
   - Make exactly ONE system change. More than one per retro = churn you can't attribute.
4. Anti-theater rules (binary):
   - No metric that doesn't change a decision.
   - No new tools mid-quarter.
   - Weekly review runs >30 min two weeks running → delete a question.
   - Skipped a review → do a 5-minute version the same day; never "double up next week".
   - Friday close: teach your top lesson to the other person in 2 minutes. Can't → you don't own it yet; it stays on next week's list.

## Junior mistakes

1. Reporting effort instead of answers ("I read 20 sources…") → Lead with the answer and confidence; effort is invisible in a good report.
2. Trusting fluency: a confident, well-written paragraph feels true → Check citations, not prose; fluency is free for LLMs, facts are not.
3. Citing the aggregator — Wikipedia, a listicle, an LLM answer → Trace to the primary and cite that; aggregators are maps, not territory.
4. Triangulating with echoes: three articles rewriting one press release → Run the 3-part independence check before counting anything as a second source.
5. Researching to comfort → Set tier and time-box first; ship with honest [uncertain] labels when the box ends.
6. "Studies show…" → Name the study, year, and sample, or delete the sentence.
7. Treating recency as truth → The date is a weight, not a verdict: stable facts age fine, volatile facts (prices, versions, policies) expire in months — classify which kind you're holding.
8. Learning by consuming (courses, videos, "getting an overview") → Input counts only when attached to a deliverable that ships this week.
9. Reviewing AI work by reading and nodding → Predict first, then diff; no listed differences = no review.
10. Letting the AI grade its own homework as the only QA → Human scores against the rubric first, compares after.
11. Goals phrased as knowledge ("understand SEO") → Phrase as capability with a test ("publish a page scoring ≥3 on the marketing rubric, solo, in 2 h").
12. Polishing the productivity system instead of the work → One system change per monthly retro, maximum.
13. Hiding gaps to look thorough → Dead ends go in the report; a hidden gap becomes the next person's landmine.

## Escalate to frontier review when…

"High-stakes" here = the research feeds a decision that is expensive to reverse.
Mechanism: run `cjudge` on the finished artifact + this domain's `RUBRIC.md` + the one-line
decision, before anyone acts on it. Escalate when ANY of:

1. **Money**: the decision commits >€1,000 or >1 person-week (T3). {{FILL: rescale with revenue}}
2. **Contracts & compliance**: anything legal, tax, regulatory, platform-policy, or safety-adjacent — always, no money threshold.
3. **Public claims**: research-backed statements going into client deliverables, sales pages, or published content.
4. **Surprise**: the conclusion contradicts the recorded prior, the field consensus, or one of our earlier reports — surprising results carry the highest error rate.
5. **Weak legs**: a load-bearing claim is still [uncertain] after the full protocol and feeds a T2+ decision.
6. **Score disagreement**: human and AI rubric scores differ by ≥2 on any dimension.
7. **Quarter commitments**: every 90-day learning plan, before day 1.

Rule for the humans: read the frontier critique in predict-then-compare mode — guess its
top finding before opening it. Escalation is also a learning rep, not just a safety net.
