Read QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §7 (the BINDING methodology),
SUPER-RESULT-PLAN-2026-07-09.md Appendix C4 (incl. the 2026-07-10 additions) +
Step 11, MODEL-PRICING-2026-07-10.md, and QUALITY-AUTOPILOT-PLAN Part 3 item 8.

Build the benchmark harness: 4 arms (system-SR under the Optimal profile,
GLM-5.2-direct, Opus-4.8-direct, Fable-5-direct as reference); blind pairwise
judging by the reference model — provenance stripped, positions swapped,
rubric-anchored. JUDGING FIXES (binding): position-swapping does NOT remove
self-preference — an LLM judge favors its own unlabeled text (Panickssery et al.,
arXiv 2404.13076, NeurIPS'24) — so every pair involving the Fable-5-direct arm is
ALSO judged by Opus 4.8 (dual-judge, report agreement, flag disagreements for human
review). Run ≥3 independent seeds per task per arm (~36+ comparisons per arm-pair)
and report exact binomial 95% CIs, never bare win-rates; pre-register the decision
thresholds before the first run.

Suite: ~12 tasks (3 × coding / research-audit / content / long-project) including
the original stability-audit brief; a deep-plan-vs-quick-plan arm on the complex
rows; 2–3 rows additionally under Eco and Smart as behavioral SMOKE TESTS (not
validation — low-effort modes may cut thoroughness, not just tokens). Define
"Optimal" empirically: log (route, correctness, cost) per case, compute the oracle
cheapest-correct frontier, score with the weighted harmonic mean (β≈0.1), and
propose tuned triage thresholds as a Decisions card. Check for router collapse.
Where cheap, add an escalated-rework-vs-direct comparison row (master plan C-7).
Cost per arm = the C3 ledger's API-equivalent dollars; compare DOLLARS, not raw
tokens.

Success criterion: the 95% CI of system win-rate vs Opus-4.8-direct excludes 50%
(from below counts as a measured loss — report it), at mean $ below one
Fable-5-direct pass. Report honestly to ~/knowledge/feedback/WINS.md and LESSONS.md.
Classify each feature THREE-way: measured benefit / measured
harm-or-cost-without-benefit (disable candidates) / insufficient evidence (keep,
re-test next campaign) — at this n, "no measurable delta" is the expected outcome
even for real effects; never disable on absence of evidence alone.
