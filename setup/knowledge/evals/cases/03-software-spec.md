# Eval 03 — Spec quality (the highest-leverage artifact in the coding pipeline)

Domain: `software-engineering` · Judge: `cjudge <output> software-engineering`

## Task (give verbatim)

> Write a SPEC.md for adding CSV export to a web app's transactions table (filters must be
> respected in the export, up to 100k rows, async generation with email link when big).
> Format: Context & goal · Requirements (numbered, testable) · Files/interfaces ·
> Out of scope · Verification (exact commands + expected results). The implementer is a weaker
> model — requirements must be mechanically checkable with edge cases named explicitly.

## Run

- glm: `glm -p "<task>"` — tests whether GLM specs well alone.
- Compare against: `cspec "add CSV export …"` (the frontier path) — the diff between the two
  IS the lesson about why specs route to the frontier model.

## What good looks like

- Every requirement independently verifiable; failure/empty/limit cases explicit (0 rows,
  100k rows, filter + export race, unicode in cells, injection via `=SUM(...)` cells).
- Verification section has actual commands, not "test thoroughly".

## Baseline runs

<!-- paste: date · output file · cjudge verdict + scores -->
