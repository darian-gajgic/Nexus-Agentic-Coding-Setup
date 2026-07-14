# Implementation Report — Judge-Loop & Task-Management Efficiency Overhaul (2026-07-13)

Plan: `~/.claude/plans/check-if-the-functionallity-rippling-stallman.md` (operator-approved:
full overhaul, GLM interior screen, escalation armed, land before bench-02 runs 2–3).
Commits: `571d59b` (Phases 0–2) + `2b7200a` (Phases 3–4) + the gates/report commit. Service
restarted on the new code 2026-07-13 ~03:12; all migrations applied.

## Why (evidence that drove it)

- Frontier ledger: judge = 75%+ of ALL frontier spend; top-5 spec tasks = 83%.
- Round-1 SHIP rate ≈ 0% across every real judged task; 3–7 full Opus passes per heavy
  task (caps counted retries, not judge calls); bench-02 spec: $8.02 Opus + 16.96M GLM,
  68% of GLM tokens on rework; judge input GREW per round (470k→689k→849k tokens).
- cjudge demanded perfection (REFUTE BY DEFAULT, binary gates, "SHIP requires every gate
  PASS") while being text-only; the reworker got a feedback blob, no prior-version pointer,
  fresh session each round; judge stateless across rounds; at-cap non-HS tasks kept an
  unresolved REVISE silently; budgets silently grew 5M→16.96M.
- Operator-reported review defects (all verified): repo review = branch-vs-base only
  (rework invisible, all-green "new file"), judge comments anchored to deliverable.md which
  the repo review never rendered (0 of 44 could display), no unanchored-findings surface.

## What changed (by phase)

**0 — robustness.** `_judge_thread` crash-safe wrapper (B1 parity; heals only rows still at
'running'); runtime stale-frontier reaper in `loop_sweep` (2h, runs in drain posture too);
watchdog step-7 zombie-dispatch detector (throttled, detection-only); `quality_loop` light
in `/api/health/full`.

**1 — first-pass quality.** cjudge recalibrated (both copies byte-identical): REFUTE scoped
to factual in-contract claims + anti-nitpick clause; gate table gains N-A /
UNVERIFIABLE-HERE; SHIP-with-notes verdict rule (only blockers block: in-scope gate FAIL or
critical/high finding); revision_brief = numbered [F1..Fn] fix-list; judge-scoping preamble
in all 10 rubrics (live ~/knowledge + vendored setup/knowledge). Worker framing gains the
QUALITY GATE evidence contract + mandatory 'Gate evidence' table for judged tasks.
Deterministic pre-gate (`evals.judge_pregate`) retries stub/placeholder/no-diff
deliverables for FREE before any frontier pass (consumes a round; manual button exempt).
Routing telemetry fixed (`_rounds_used` counts only the task's own judge/SR rounds;
`judge_runs` recorded).

**2 — round economics.** First automated rework CONTINUES its own session
(`dispatch.rework_continue_session`, epoch-marker guards the harvest ladder from
resurrecting the rejected reply; round ≥2 + operator rejects stay fresh);
targeted-revision retry contract (prior version named, '## Fixes applied' [F#] echo).
Delta re-judge on round ≥2 (`JUDGE_PRIOR` = prior blocker fix-list + version diff, criteria
frozen at round 1, artifacts mtime-filtered, SPEC omitted); `judge_round`/`judge_keys`/
`judge_tier` columns + per-round `_judge/round-N.json` memory. Hard cap `judge.max_runs=4`
on loop-sourced judge calls. At-cap/converged/error closure files ONE 'deliverable'
decision card (approve = accept-as-is, reject = re-arm: marker cleared + round/keys reset)
— the silent `continue` is gone. Retry budget slice = 0.5× original with a 2.0× lifetime
ceiling + 'budget' decision card; `budget_original` pinned at creation/PATCH.

**3 — mode ladder & visibility.** Balanced judge_scope all_quality→**sinks** (frontier
judge only for client-facing deliverables + high-stakes); interior members get the **GLM
screening judge** (`judge.screen=interior`: one Hermes turn, same contract, REVISE with a
critical/high blocker loops ONE fix round, SHIP = accept-with-notes and never authorizes —
`judge_tier='screen'`, excluded from exemplars and auto-approve). Per-task frontier cost
cap `frontier.task_cost_cap_usd=3.0` ×budget_mult enforced before judge/screen/critic/
escalation. **Escalation ladder armed** (`super.escalation=1`; C5 profile thresholds live:
Eco off / Balanced REWRITE / Smart REWRITE-or-cap; bounded by escalation_max=1 + cost cap).
Assisted `sr_mode` open→closed (terminal checkpoints only). Dead `deep_plan.enabled` key
fixed (`plan.deep_enabled`) → plan_recommend finally derives. `auto_approve_ship_hours`
semantics fixed (was structurally dead; now Full-Auto + frontier-SHIP incl. high-stakes;
default still 0=off). Budgets re-derive on spend-profile PATCH. Cost visibility: task-card
$ chip, task-detail True-cost line (C3 ledger), Usage-tab Quality-Loop panel.

**4 — review & diff UX.** `rounds.json` (per-finalize HEAD) + `worktree.capture_diff_between`
→ repo review DEFAULTS to the round-over-round diff once ≥2 rounds exist ("what the rework
changed"); branch-vs-base stays selectable. Repo tasks snapshot their workspace on retry;
deliverable.md renders as a diffed Report entry in the repo review → judge findings anchor
onto it. Findings panel lists every judge/critic/user comment (open + addressed; anchored
rows jump to the diff line). Anchor validation also resolves against the repo worktree.
Workspace reviews get a version-pair selector. `_history`/`_judge`/`artifacts` excluded
from artifact copies, review walks and deliverable listings.

## Gates (all green post-restart)

| gate | result |
|---|---|
| `scripts/verify.sh` | 481/481 (was 455; +26 in section 22) |
| `verify_judge_loop_e2e.py` (NEW) | 41/41 |
| `verify_mode_coherence_e2e.py` | 47/47 (was 29; §5 slice + §6 derive + §7 tier/sink/cap) |
| `verify_autopilot_e2e.py` | 72/72 (auto-approve + forward-dep expectations updated) |
| `verify_super_result_e2e.py` | 90/90 |
| `verify_block2_e2e.py` / `_ui.py` | 48/48 / 21/21 (repo-snapshot check inverted by design) |
| live smoke | health_full quality_loop OK; /api/usage quality_loop rollup serving |

## Changed defaults (rollback = flip the key)

`judge.auto_scope` help now documents high_stakes|sinks|all_quality (default string
unchanged: high_stakes — profiles govern); NEW keys: `judge.pregate=1`,
`judge.pregate_min_chars=400`, `judge.max_runs=4`, `judge.delta_rejudge=1`,
`judge.screen=interior`, `frontier.task_cost_cap_usd=3.0`,
`dispatch.rework_continue_session=1`, `dispatch.retry_slice_frac=0.5`,
`dispatch.rework_ceiling_mult=2.0`; FLIPPED: `super.escalation` 0→1. Most reversible
first: `judge.screen=off`, `dispatch.rework_continue_session=0`.

## Still open

1. **A/B replay** (`benchmarks/judge-loop-ab/RUNBOOK.md`) — paid run, operator go
   (~10–25M GLM + $2–8 Opus). Success gate: ≥40% frontier-$ cut, non-inferior pairwise,
   ≤1.2× GLM.
2. bench-02 runs 2–3 on the new loop (annotate RESULTS.md: run 1 = old-loop anchor).
3. Phase-8 measurement campaign last, on settled defaults.
4. Deferred: acceptance-runner pre-gate for code (`judge.pregate_tests`), artifact-cap
   knob, finding-chip "verified fixed" tie-in.
