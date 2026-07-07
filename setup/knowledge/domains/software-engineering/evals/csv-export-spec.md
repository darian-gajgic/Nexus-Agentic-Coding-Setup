---
title: Spec — CSV export for a transactions table
specialist: tech-lead-orchestrator
notes: ported from the manual eval set (evals/cases/03) — spec falsifiability for a weaker implementer
---
Write a SPEC.md for adding CSV export to a web app's transactions table. FIXED evaluation
brief — constraints:

- The export must respect the table's active filters (date range, account, category,
  free-text search).
- Up to 100.000 rows; anything above 10.000 rows generates asynchronously and emails a
  download link; below that, direct download.
- Stack context: FastAPI + PostgreSQL backend, React table frontend, existing background-job
  runner (arq) available, S3-compatible object storage available, transactional email
  service available.
- Character encoding, delimiter and Excel compatibility must be decided IN the spec, not
  left open.

Format: Context & goal · Requirements (numbered, each independently testable and
falsifiable) · Files/interfaces (exact paths for the stack above — invent a plausible
existing layout and mark it as assumed) · Out of scope · Verification (exact commands +
expected results) · ordered plan with per-item acceptance criteria and edge cases named
explicitly. The implementer is a WEAKER model — requirements must be mechanically checkable.
Unfalsifiable wording ("fast", "robust", "handles gracefully") is a defect.
