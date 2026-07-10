Read QUALITY-AUTOPILOT-PLAN-2026-07-10.md at the repo root COMPLETELY — including
Part 4 (premortem resolution) which is BINDING and overrides earlier text where in
conflict; QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §5 overrides both on conflict.
Implement Part 1 (Q1–Q5 — SKIP Q6, deferred), the Learning-loop additions L1–L4,
and Part 2 (Q7a/b/c) with all guardrail rules 1–12, in the Part 3 order. Also
implement the still-open N5, N6, N7 (SUPER-RESULT-PLAN-2026-07-09.md Appendix A
Tier 2, setting-gated — verified absent from code) and B4 (Appendix B) in the same
pass. Do NOT implement Deep Plan or Appendix C — separate sessions. All frontier
calls go through the Phase-1 frontier.max_concurrent semaphore. Remember rule 11
(audit all 18 specialist definitions against the new executor contracts) and rule 12
(update the JARVIS system-control framing and re-run the JARVIS gates at the end).
Protocol: verify.sh green after every step, one commit per lever, full gate suite at
the end including the new app/scripts/verify_autopilot_e2e.py you build (with the
Part 5 checks incl. the P4 additions), then write
IMPLEMENTATION-REPORT-QUALITY-AUTOPILOT.md (per item: built/deviated/skipped + real
gate outputs). An independent judge will verify — claim nothing unverified.
