Read DEEP-PLAN-MODE-PLAN-2026-07-10.md at the repo root COMPLETELY and implement it
step by step, including every "Premortem fix" note (MODEL_PURPOSES whitelist
extension — verified: the tuple is still (complicated, easy, mechanical,
frontier_judge), so extend it AND the assignment API/UI when seeding spec_model;
async non-blocking triage sampling; family→deliverable_type map; session hygiene).
Decisions in §3 are locked — do not revisit. Re-locate all code anchors by symbol
name. All frontier calls (premortem critique) go through the Phase-1
frontier.max_concurrent semaphore. Two binding additions (master plan §5 C-4/C-5):
(1) the e2e gate is app/scripts/verify_deep_plan_e2e.py and stubs the PLANNING model
via a new `plan.stub` setting that short-circuits the Hermes session turn with canned
slot-filling replies (mirror `evals.stub` in evals.py — the judge/critic
command-template stubs do NOT apply to session turns); (2) every plan-session
endpoint that calls the model (turn/draft/critique) runs its blocking work via
run_in_threadpool or a worker thread (B7 no-block-in-async rule —
app/scripts/check_async_blocking.py enforces it).
Protocol: verify.sh per step, commit per step, gates at the end including
verify_deep_plan_e2e.py, update the JARVIS framing (Quality Autopilot rule 12), then
write IMPLEMENTATION-REPORT-DEEP-PLAN.md for the independent judge.
