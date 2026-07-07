---
name: win-lesson-logging
description: Log real-world WINS and LESSONS to ~/knowledge/feedback/ so future agents learn what actually works vs what flops. Trigger when an outcome is confirmed with real numbers (a win) or when something failed/regretted and a correction is identified (a lesson). Also trigger on the explicit instruction "log this win" / "log this lesson".
version: 1.0.0
author: sinep
metadata:
  hermes:
    category: meta-cognition
    tags: [feedback-loop, learning, continuous-improvement, business-brain]
---

# Win / Lesson Logging

Two append-only ledgers capture the gap between what looked good and what actually
worked. They are the curriculum for future work — templates are generic until real
results replace them.

- `~/knowledge/feedback/WINS.md` — things that WORKED, with numbers.
- `~/knowledge/feedback/LESSONS.md` — things that FLOPPED or were regretted, with corrections.

## When to log (load this skill when ANY is true)

Log a **WIN** when:
- A shipped artifact produced a measurable real-world result (sales, opens, CTR, signups,
  attendance, conversion, engagement). The result is confirmed, not predicted.
- The user says "log this win" / "this worked, save it."

Log a **LESSON** when:
- An output that scored well / looked good actually flopped or was regretted.
- AI work was shipped and the user pushed back, corrected, or flagged regret.
- A rubric gap surfaced: something scored fine by the rubric but was actually bad → the
  rubric itself needs fixing.
- A judgment gap surfaced: your self-score differed materially from the frontier judge's
  verdict — that delta is the lesson.
- The user says "log this lesson" / "note this mistake."

## The two hard rules

1. **A WIN is not logged without NUMBERS.** "The email did great" is not a win — "42% open
   rate, 6.1% CTR, 38 signups" is. If no numbers exist yet, do NOT log prematurely; set a
   reminder to log once results land.
2. **A LESSON is not logged without a CORRECTION.** Naming the mistake alone is a complaint,
   not a lesson. The correction is the part future agents can act on. If you cannot name the
   concrete change (to a playbook, rubric, review process, or prompt), the lesson is not
   ready — keep digging until you can.

Both rules are blockers: a draft entry that violates them is deleted, not shipped.

## How to log

1. Read the current file to match the existing entry style (newest at top, below the
   `<!-- newest first -->` marker).
2. Write the new entry immediately above the most recent one, following the template in that
   file. Use today's date (YYYY-MM-DD). One entry per event — do not batch multiple wins or
   lessons into a single block.
3. Use `patch` (or equivalent find-and-insert) — never rewrite the whole file. These are
   append-only ledgers; an agent rewriting the body can silently drop prior entries.

### WIN template (numbers required)

```
### YYYY-MM-DD — <one-line what>
- Domain: <marketing / ecommerce / ...>
- Artifact: <link or path to the actual deliverable>
- Result: <the numbers: CTR, sales, opens, attendance...>
- Why we think it worked: <1-3 bullets>
- Promote to examples/? <yes/no — if yes, do it>
```

### LESSON template (correction required)

```
### YYYY-MM-DD — <one-line what happened>
- Domain: <...>
- What we expected vs what happened:
- Root cause (be honest):
- Correction: <what changes — in a playbook? rubric? our review process?>
- Applied where: <file/line updated, or "process">
```

## After logging

- **WINS**: if the entry says `Promote to examples/? yes`, actually do it — copy the artifact
  into `~/knowledge/domains/<domain>/examples/`, replacing a generic template with the proven
  winner. A logged-but-not-promoted win is half-work.
- **LESSONS**: if the correction names a concrete file (a playbook, rubric, or review
  process), update that file in the same turn — "Applied where" must point at a real change,
  not a promise. Rubric gaps in particular: fix the rubric so the same miss fails the gate
  next time, not just the log.
- Tell the user in one line what was logged and where the downstream change landed.

## Do NOT log

- Predicted or hoped-for results. Numbers must be measured.
- Praise without outcomes ("the client loved it" with no metric → not a win).
- Routine mistakes already covered by an existing skill/pitfall — extend that skill instead
  of duplicating into LESSONS.
- Task progress, completed work, or session notes — those belong in session history, not
  these ledgers. These capture outcome signal, not effort.

## Verification

A logged WIN is correct when a future agent could reconstruct *what* was built and *how well*
it performed from the entry alone. A logged LESSON is correct when a future agent reading it
would do something differently. If either reads as narrative with no actionable signal, it
failed the rule — rewrite it or remove it.
