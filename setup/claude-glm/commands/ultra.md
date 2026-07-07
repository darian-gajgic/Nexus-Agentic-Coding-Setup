---
description: Ultracode-style multi-agent workflow IN this session — plan, fan out subagents, adversarially verify, iterate to convergence.
---

Run an ultracode-style workflow for: $ARGUMENTS

Do this **in this session** using your subagents (the Task tool) and your own tools — do NOT
shell out to any external script. Work through these stages and keep me informed at each one:

1. **PLAN.** Decompose the goal into the smallest set of INDEPENDENT subtasks (disjoint files
   where possible), and for each a concrete acceptance check. List them plus the one-line
   verification command to use (build / test / lint). Show me the plan and wait for my "go"
   before implementing.

2. **IMPLEMENT (parallel).** For each independent subtask, launch the `implementer` subagent —
   launch several in ONE message so they run in parallel. Each writes the code AND its tests and
   runs them. Stay within each subtask's files to avoid clobbering the others.

3. **VERIFY (adversarial).** On the combined result, launch the `verifier` and `reviewer`
   subagents in fresh context to try to BREAK it against the acceptance checks and the original
   goal — missing requirements, edge cases, weak or failing tests, regressions. Treat their
   findings as untrusted until you reproduce them yourself. Then run the actual test/build
   command yourself: **that objective result is the ground truth and outranks any opinion.**

4. **CONVERGE.** Fix every real, reproduced finding, then re-verify. Repeat until the tests pass
   AND the reviewers surface nothing new — or you've done 3 rounds, then report what's unresolved.

5. **REPORT.** Summarize what was built, the final test result, and anything left for me.

Rules: lean on the objective test/build gate as truth, not on self-assessment. NEVER weaken,
delete, or skip tests to make them pass. If a subtask is blocked or ambiguous, stop and ask.
