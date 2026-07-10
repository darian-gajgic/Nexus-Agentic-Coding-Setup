Read SUPER-RESULT-PLAN-2026-07-09.md Appendix C (note: its build order is superseded
— this phase builds C3, then C1a/C1c/C1b/C1d, then C2; C4 is deferred to the next
phase; C6 already landed as Q2; for C5 only add escalation-threshold settings). Also
read MODEL-PRICING-2026-07-10.md, QUALITY-AUTOPILOT-PLAN Part 4 items P1/P5, and
QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §5 (C-6/C-7/C-8 are binding here).

C3 specifics: seed the per-model price table in settings from the pricing doc
(GLM-5.2 $1.40/$4.40, cache-hit $0.26; Opus 4.8 $5/$25, cache write $6.25, hit
$0.50; Fable 5 $10/$50, cache write $12.50, hit $1 — per 1M tokens; re-verified
2026-07-10). The ledger reports API-EQUIVALENT dollars (label it as the comparison
currency, not a bill). Capture frontier token usage via claude -p
--output-format json. CONTRACT CHANGE (binding, C-8): that flag wraps the model's
reply in a JSON envelope — cverify/cjudge stdout becomes {result, usage,
total_cost_usd, modelUsage} and the sentinel parsers break unless
run_critic_cmd/run_judge_cmd unwrap the `result` field BEFORE
parse_critic_json/parse_judge_metrics run (verified: both parsers consume raw stdout
today). Do that unwrap; persist usage + total_cost_usd per run (use the envelope's
own dollars for frontier runs; the price table covers GLM + display); keep the
transcript-size estimate as fallback; add a regression check that a stubbed
JSON-envelope output still parses. Update BOTH copies of cverify/cjudge
(setup/bin/ + ~/.local/bin/ — they are byte-identical by convention).

C1/C2 specifics: extend db.MODEL_PURPOSES + the assignment API/UI with spec_model
and escalation_model (P5 — coordinate with Deep Plan's spec_model seed if it landed
first: same purpose, seed once); every frontier call goes through the
frontier.max_concurrent semaphore (P1); complete Eco's staged model-floor routing
(guardrail rule 3); fingerprint-tag tuned thresholds (L4). C1c's floor is an
empirical claim, not a guarantee (C-7) — implement it setting-gated
(super.escalation) and let Phase 8 measure it. Judgment-tier roles resolve to the
frontier_judge assignment (Opus 4.8); Fable 5 is NEVER assigned to any purpose.

Protocol: verify.sh per step, commits per step, gates at the end, JARVIS framing
update (rule 12), report IMPLEMENTATION-REPORT-APPENDIX-C.md.
