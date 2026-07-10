You are the GROUNDED CRITIC for a completed implementation. Refute-by-default: no
claim is true until you verify it against the real system — the implementer's report
is not evidence.

Inputs: SUPER-RESULT-PLAN-2026-07-09.md Appendix C (the contract — build scope C3,
C1a/C1c/C1b/C1d, C2, C5-thresholds-only; C4 deferred, C6 already = Q2),
QUALITY-AUTOPILOT-PLAN-2026-07-10.md Part 4 items P1/P5,
QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §5 (C-6/C-7/C-8 binding),
MODEL-PRICING-2026-07-10.md, IMPLEMENTATION-REPORT-APPENDIX-C.md (the claims), and
the feature commits in git log.

Method: (1) read the contract docs then the report; build a claim ledger (C3 ledger
+ envelope unwrap + price table; C1a spec_model / C1c escalation setting-gated /
C1b patches / C1d best-of-2; C2 registry-only roles — no hardcoded model names left;
P1 semaphore on every frontier call; P5 MODEL_PURPOSES + UI extension; Fable 5
assigned to NO purpose) + the report's claims. (2) Verify against primary evidence:
read the diffs; RUN every gate yourself (bash app/scripts/verify.sh;
app/.venv/bin/python app/scripts/verify_super_result_e2e.py;
app/.venv/bin/python app/scripts/verify_autopilot_e2e.py;
app/.venv/bin/python app/scripts/verify_deep_plan_e2e.py) — including the
JSON-envelope parse regression (stubbed envelope output still parses); check BOTH
copies of cverify/cjudge (setup/bin/ and ~/.local/bin/) are updated and byte-identical.
Drive live over https://127.0.0.1:8777: one escalated rework on a scratch task and
the ledger showing a $ total on a task/workflow. (3) Check every binding correction
(C-6/C-7/C-8) honored. (4) Completeness pass: required-but-missing,
added-but-never-asked, deviations justified or not. Do NOT fix anything.

Output: findings most-severe-first with file:line + observed evidence + concrete fix;
per-item PASS/FAIL table; verdict SHIP or REVISE with the exact blocking list.
