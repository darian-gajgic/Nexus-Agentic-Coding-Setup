---
description: Lean spec-driven loop — interview, write SPEC.md, implement, review against the spec.
---

Run a lightweight spec-driven development loop for: $ARGUMENTS

1. **Interview** — Use AskUserQuestion to resolve the essential unknowns: goal, users,
   constraints, success criteria, and what is explicitly out of scope. Ask only what
   materially changes the design; don't over-ask.

2. **Write `SPEC.md`** at the repo root with these sections:
   - **Context & goal** — the problem, why now, the intended outcome.
   - **Requirements** — numbered and testable.
   - **Files / interfaces** — the specific files/APIs to create or change.
   - **Out of scope** — what this deliberately does not do.
   - **Verification** — the exact end-to-end check (commands + expected result) that proves it works.

   Keep it tight. Get my confirmation before implementing.

3. **Implement** — work through the requirements. Use the `implementer` subagent per subtask,
   or `scripts/parallel-agents.sh` to fan out independent subtasks. Commit in logical steps.

4. **Review** — launch the `reviewer` subagent to check the diff against `SPEC.md`; fix gaps.

5. **Verify** — run the verification step from `SPEC.md` and report the result plainly. Do not
   call it done unless that check passes.
