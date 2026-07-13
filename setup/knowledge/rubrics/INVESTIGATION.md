# Investigation Rubric (deliverable type: analysis / research)

> Frontier-judge scoping (2026-07-13): for the text-only frontier judge, a gate whose evidence cannot appear on the page and is not contradicted by the task's artifacts is UNVERIFIABLE-HERE (a note), not FAIL — the cjudge verdict contract governs: only binding in-scope gate FAILs and critical/high findings block a SHIP.

Score any investigation — audit, root-cause analysis, assessment, reconciliation,
verification report — using this file alone. This is a TYPE rubric: it applies on
top of the domain rubric (both must pass). It exists because the most dangerous
investigation failure is *confidently wrong conclusions built on unverified
inference* — well-formatted reports that scored high on plausibility while the
root cause sat unexamined.

Procedure: run the gates (any FAIL → REVISE before scoring), then score the
dimensions 0–4.

## Must-pass gates — binary

- **A1 VERIFIED-NOT-INFERRED** — every load-bearing claim traces to primary
  evidence with an exact location: file:line, command + its real output, or
  source URL with access date. Inference is allowed only when explicitly labeled
  as inference ("inferred from X; not directly verified"). A proxy inference
  presented as fact — "tests pass, therefore the code is healthy", "no error in
  the logs, therefore no failure" — is an unlabeled inference. **Any unlabeled
  inference presented as fact = FAIL.** An inline `[UNSURE: reason]` tag COUNTS as
  an explicit inference label — a marked claim that turns out wrong is a scored
  deduction, not an A1 gate FAIL; an UNMARKED claim presented as fact and found
  false is the A1 violation this gate exists to catch.
- **A2 ALTERNATIVES-RULED-OUT** — competing explanations for the central
  conclusion are enumerated, and each is excluded with evidence, not with
  plausibility ("unlikely because…" without a check = FAIL). If only one
  explanation was ever considered, the report must say so explicitly.
- **A3 COVERAGE** — the investigated surface is enumerated (which files,
  systems, time ranges, configurations were examined); the sampling strategy is
  stated when the surface was sampled rather than exhausted; an honest
  **"What I did NOT check"** section exists. A report with no stated
  boundaries = FAIL.
- **A4 RE-VERIFY-BORROWED-CLAIMS** — claims imported from sibling reports,
  previous versions of this report, or cited sources are independently
  re-checked against primary evidence before being reused. A borrowed claim
  carried forward on the sibling's authority alone = FAIL.

## Scored dimensions — 0–4

0 = absent · 2 = present but flawed (as described) · 4 = professional (as described).
1 and 3 = between the anchors.

1. **Evidence density**
   - 2: conclusions cite evidence, but whole sections rest on one observation,
     or locations are vague ("in the logs", "in the config").
   - 4: every section's conclusions rest on multiple, exactly-located pieces of
     evidence; quotes/outputs are reproduced verbatim; the reader could re-run
     every check from the report alone.
2. **Falsifiability of statements**
   - 2: findings are stated, but hedged or absolute in ways that cannot be
     tested ("robust", "should be fine", "likely misconfigured").
   - 4: every finding is stated so a specific observation could prove it wrong,
     and the report names what that observation would be.
3. **Contradiction handling**
   - 2: conflicts between sources/versions/siblings are mentioned but left
     open, or silently averaged.
   - 4: every contradiction is surfaced, resolved with evidence, and the losing
     side's error is explained; unresolved conflicts are carried as explicit
     open questions with a next check.
4. **Actionability of conclusions**
   - 2: conclusions are directional ("improve X", "consider Y") without an
     owner-executable next step.
   - 4: each conclusion ends in a concrete action — what to change, where,
     verified how — ordered by impact, with effort/risk noted.

Scoring bands (/16):
- **14–16** — ship.
- **10–13** — revise the weakest dimension, re-score once.
- **≤9** — re-investigate; do not patch the prose.
- Any gate FAIL overrides any score.
