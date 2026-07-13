# SPEC-JUDGE-LOOP — the quality-verdict cascade (2026-07-13 overhaul)

**This file is the source of truth for how deliverable verification works.**
Read it before changing anything in the judge/screen/retry/closure machinery.
The "why" evidence (live-DB numbers that motivated the design) lives in the
repo-root `IMPLEMENTATION-REPORT-JUDGE-LOOP-2026-07-13.md`; the operator-approved
design is `~/.claude/plans/check-if-the-functionallity-rippling-stallman.md`.
Anchors below are FUNCTION names (line numbers drift — grep the symbol).

History in one line: before 2026-07-13 the Opus judge reviewed every quality
task (75%+ of frontier spend), demanded perfection (0% round-1 SHIP observed),
re-read everything every round, and each REVISE re-ran the whole task fresh —
this spec describes what replaced that.

---

## 1. The cascade (cheap → expensive)

```
finalize (status review/done, dispatch_state=completed)
  │  loop_engine._sweep_task_loops (20s tick, ≤3 actions/sweep shared)
  ▼
[0] closed-family check      _judge_closed(trig, per_task)   → skip forever until operator reject
[1] hard caps                judge_round ≥ judge.max_runs    → _close_judge_loop (card)
                             _frontier_cost_capped(t)        → _close_judge_loop (card)
[2] tier resolution          _judge_tier(t, auto_scope)      → 'frontier' | 'screen' | 'none'
[3] deterministic pre-gate   evals.judge_pregate(t)          → FREE retry w/ fix list (consumes a round)
[4] verdict run              POST /api/tasks/{id}/judge {source:'loop', tier}
                               tier='screen'  → server._screen_thread   (1 GLM turn)
                               tier='frontier'→ server._judge_thread    (cjudge / Opus)
[5] on REVISE/REWRITE        POST /retry {origin:'loop_judge'} → server._retry_task
                               round 1: continue-session rework; round ≥2: fresh
[6] re-judge                 round ≥2 = DELTA re-judge (prior fix-list + diff, criteria frozen)
[7] convergence/exhaustion   keys⊆prev | round cap | max_runs | cost cap | verdict 'error'
                               → _close_judge_loop → ONE 'deliverable' decision card
                                 (screen tier: accept-with-notes, NO card)
```

Super Result (`super_result=1`) REPLACES steps 2–7 with the sandboxed critic
loop (`_sweep_super_result`) — the two loops never stack (belt-and-braces skip
in `_sweep_task_loops` on any config carrying a super_result trigger). They
SHARE `_retry_task` (comment drain, budgets, session policy) and
`_insert_critic_comments`.

## 2. Tier resolution — `loop_engine._judge_tier(t, auto_scope)`

| condition (first match wins) | tier |
|---|---|
| `high_stakes` | frontier (rule-2 floor — no profile can lower it) |
| profile `smart` | frontier (its SR usually replaces the loop anyway) |
| profile `eco` | none (pre-gate only; HS floor above still applies) |
| profile `optimal` (Balanced) | frontier if `_is_sink(t)` else screen |
| no profile + `judge.auto_scope='sinks'` | frontier if sink else screen |
| no profile + `'all_quality'` | frontier |
| no profile + `'high_stakes'` (default) | none |

`_is_sink(t)`: no non-archived workflow member depends on the task, or the
task is standalone — i.e. it IS the client-facing deliverable. Coding
pipelines are unaffected: their sink (acceptance-verifier) is forced
high_stakes at plan repair. `judge.screen='off'` turns screen slots into none.
The screen requires the same `_judgeable(domain)` rubric check as the judge.

## 3. The verdict contract (cjudge)

Three synced copies — **verify.sh diffs them; keep all three identical**:
`setup/bin/cjudge` (vendored, committed) = `~/.local/bin/cjudge` (installed).
The pre-overhaul prompt is retrievable with
`git show 2b7200a~2:setup/bin/cjudge` (the A/B replay's OLD arm uses it).

Contract essentials (all verbatim in the script):
- **Refute-by-default is SCOPED** "to FACTUAL CLAIMS inside this deliverable's
  binding contract", with an explicit anti-nitpick clause ("do not manufacture
  findings to appear thorough"). Polish/style/extra-depth = notes, never blockers.
- Gate table states: `PASS / FAIL / N-A (owned by a later stage) /
  UNVERIFIABLE-HERE` — the last is a note unless the stage contract demands
  that evidence inline. Every domain RUBRIC.md + rubrics/INVESTIGATION.md
  carries a "Frontier-judge scoping (2026-07-13)" preamble so rubric text
  ("any FAIL → do not publish") can't contradict this. Rubrics live in
  `~/knowledge` (operator-owned) + vendored `setup/knowledge/`.
- **SHIP-with-notes**: verdict vocabulary stays `SHIP|REVISE|REWRITE`; SHIP is
  correct "when zero blockers exist, even with medium/low findings open".
  Blockers are ONLY: an in-scope must-pass gate at FAIL, or a critical/high
  finding (unmarked-false claim, contradiction with stage contract/SPEC, unmet
  binding 'Done when:'). `revision_brief` must be a NUMBERED `[F1]..[Fn]`
  fix-list of blockers only.
- Optional env blocks (absent = feature off): `JUDGE_TASK` (stage contract),
  `JUDGE_SPEC` (Deep-Plan spec, background when a contract exists, OMITTED on
  delta rounds), `JUDGE_ARTIFACTS` (size-capped file copy),
  `JUDGE_PRIOR`+`JUDGE_ROUND` (delta re-judge, §5).
- Output: `claude --output-format json -p`; `evals._unwrap_frontier_output`
  strips the envelope and books tokens/$ (contract C-8);
  `evals.parse_judge_metrics` reads the `NEXUS_JUDGE_JSON_BEGIN/END` sentinel
  and computes `_keys` (sha1 `file|severity|claim-or-problem[:120]` — exact
  mirror of the critic's, feeds convergence).

The **GLM screen** (`server._screen_thread`) inlines the same stance/verdict
rules into one Hermes turn on the owner's 'complicated' model (deliverable
inlined ≤24k + stage contract, no artifact copy; session file tools cover the
rest). Screen-specific semantics enforced in code, not just prompt: a REVISE
without any critical/high finding is stored as SHIP; unparseable output stores
SHIP (a screen must never block on its own failure); output prefixed
`[GLM SCREENING JUDGE]`; `judge_tier='screen'`.

## 4. Round lifecycle — exact hops

1. **Flip**: `POST /api/tasks/{id}/judge` CAS-flips `judge_verdict='running'`
   + stamps `judge_ts` (this NULLs judge_output — round memory lives in files,
   §6). Body `{source:'loop'}` enforces `judge.max_runs`; the manual button
   sends no body and BYPASSES caps + pre-gate (operator intent wins). Body
   `tier:'screen'` routes to `_screen_thread`.
2. **Run**: `server._judge_thread` is a crash-safe wrapper (B1 pattern —
   on any exception heal `WHERE judge_verdict='running'` to 'error'); the body
   is `_judge_thread_inner` → `evals.run_judge_cmd` (frontier semaphore
   `frontier.max_concurrent`, subprocess timeout 900s hardcoded).
3. **Store**: verdict + `judge_output[-30000:]` + `judge_ts` +
   `judge_round += 1` + `judge_keys={round,keys,prev}` + `judge_tier` in ONE
   UPDATE; then `workspace/_judge/round-{N}.json` (findings, brief, keys, ts);
   then findings → `review_comments source='judge'` via
   `_insert_critic_comments` (same-source open comments superseded per round;
   anchors validated ±2 against the workspace AND the repo worktree).
   Quota-classified failures (`is_frontier_quota_error`) store 'interrupted' +
   `judge_ts=NULL` (re-judgeable after backoff) and do NOT count a round.
4. **Rework** (`_retry_task(task_id, feedback, origin)`): feedback = operator
   text > prior feedback > judge `revision_brief` (else output tail); ALL open
   review_comments drained with `[F#]` ids + verbatim patches, marked
   consumed; `deliverable.md → deliverable.v{N}.md`; workspace snapshotted to
   `_history/v{N}` (repo tasks too, since the overhaul); budget slice (§7);
   `origin in (loop_judge, loop_sr)` + first rework (zero existing
   `deliverable.v*`) + `dispatch.rework_continue_session=1` → **session kept**,
   else `session_id=NULL`.
5. **Dispatch**: worker passes `rework=True` when `retry_feedback AND
   session_id`; `run_task_dispatch(rework=True)` SKIPS the orphan-harvest
   ladder (harvesting would resurrect the rejected reply) and sends a
   continue-turn starting `"Rework round for task {id}:"` — that exact string
   is the **epoch marker**: if it already appears in the transcript (rework
   blocked/cut mid-round), the normal ladder is correct again and `rework`
   demotes to False. Framing carries the RETRY block: prior version named,
   "TARGETED REVISION", mandatory `## Fixes applied` [F#] echo.
6. **Delta re-judge** (round ≥2, `judge.delta_rejudge=1`):
   `server._build_judge_prior` = prior round's blocker fix-list + unified diff
   (previous version vs current) → `JUDGE_PRIOR`; artifacts copied only with
   mtime > prior round's ts; SPEC omitted. cjudge's DELTA block: verify each
   `[F#]` fixed, scan only changed regions for NEW critical/high, criteria
   FROZEN at round 1.
7. **Closure** (`_close_judge_loop`): fires on verdict `error`, convergence
   (`_judge_keys_converged`: round>1 ∧ keys⊆prev), round cap, `judge.max_runs`,
   or the frontier cost cap. Marks the judge_revise trigger
   `closed`/`closed_tasks[tid]`, then files ONE pending `deliverable` approval
   (idempotent via the pending-probe; HS tasks already hold their finalize
   approval — no double card). Screen tier closes with `card=False` =
   accept-with-notes, log only. Decision semantics (in `decide_approval`):
   approve → done + `close_judge_loop_marker` (approval bumps completed_at,
   which would otherwise re-arm auto-judge); reject → `reopen_judge_loop`
   (marker cleared, `judge_round=0`, `judge_keys=NULL`) + `_retry_task`. **Only
   an operator reject re-arms a family — automation cannot.**

## 5. Pre-gate — `evals.judge_pregate(task)`

Free (<50ms, filesystem-only), LOOP-sourced runs only. Fails: missing/
unreadable deliverable; < `judge.pregate_min_chars` (400); <2 markdown
headings; TBD/TODO( in the first 2k; repo task with empty `changes.diff` —
UNLESS the deliverable declares a NO-OP round (regex: no-op / "no changes
needed" / "review clean" in the first 3k — the pipeline's fix stage is a
documented NO-OP when review is clean). A failure POSTs `/retry` with the
exact list, **bumps the judge_revise round** (can't ping-pong); rounds
exhausted → one real judge run so the at-cap closure owns the ending.

## 6. State inventory

| where | what |
|---|---|
| `tasks.judge_verdict/judge_output/judge_ts` | current round's result (output NULLed at each 'running' flip) |
| `tasks.judge_round` | stored verdicts THIS version family (quota runs don't count); reset only by operator reject |
| `tasks.judge_keys` | `{round, keys, prev}` convergence state (sentinel-format rounds only) |
| `tasks.judge_tier` | 'frontier' \| 'screen' — which tier verdicted (exemplars + auto-approve read it) |
| `tasks.budget_original` | creation-derived budget; slices/ceiling compute from it |
| `workspace/_judge/round-N.json` | per-round findings/brief/keys/ts — the ONLY cross-round memory (feeds `_build_judge_prior`) |
| `workspace/deliverable.vN.md` | version history (renamed at each retry) |
| `workspace/_history/vN/` | full workspace snapshots per retry (review comparison base; repo tasks too) |
| `workspace/_history/rounds.json` | repo finalize HEAD shas (`{round, head_sha, ts}` — review round-diffs) |
| loop cfg `judge_revise.closed`/`closed_tasks` | operator-accepted family marker |
| `approvals action_type='deliverable'/'budget'` | closure + budget-ceiling decision cards |
| `frontier_ledger` kinds | judge / judge_screen / critic / escalation / judge_eval / premortem |

`_judge/`, `_history/`, `artifacts/` are EXCLUDED from judge artifact copies
(`evals._ARTIFACT_SKIP_DIRS`), review walks (`review.SKIP_DIRS`) and
deliverable listings (`server._WS_SKIP_DIRS`) — internal state, never evidence.

## 7. Budgets & cost bounds

- Retry slice = `dispatch.retry_slice_frac` (0.5) × `budget_original`
  (lazy-pinned on first retry for legacy rows); lifetime ceiling =
  `dispatch.rework_ceiling_mult` (2.0) × original → at ceiling: NO extension,
  one `budget` card (approve = +1 slice past the ceiling; reject = accept
  as-is for non-HS + close the judge family).
- `frontier.task_cost_cap_usd` (3.0) × profile mult (eco .5 / bal 1 / smart 2)
  checked before every loop-sourced judge, screen→n/a, critic and escalation
  run against `tasks.frontier_cost_usd`; 0 = uncapped.
- Screen spend is GLM: booked `kind='judge_screen'` with
  `db.glm_cost_estimate`; everything else books the claude-envelope's own $.
- Visibility: task-card `$` chip (`frontier_cost_usd`), task-detail True-cost
  line (`GET /api/tasks/{id}/ledger`), Usage-tab Quality-Loop panel
  (`tools_hub.get_usage` → `quality_loop`), health light in
  `/api/health/full` (stranded verdicts + zombie dispatches).

## 8. Escalation & SR interplay

`super.escalation=1` (ARMED since the overhaul). `_try_escalate_super` runs on
REWRITE (Balanced+Smart) or round-cap-with-criticals (Smart only — C5
thresholds derive per profile in `autopilot.derive`), bounded by
`super.escalation_max` (1) AND the frontier cost cap; quota backoff → 'wait'
(never demoted to a GLM retry). Assisted involvement now runs SR fix-rounds
CLOSED (`sr_mode='closed'`); humans are pulled in only at terminal
checkpoints (cap / convergence / contradiction / error / escalation-failure).
Manual involvement keeps every round open.

## 9. Review surface (operator-facing consequence of this loop)

`review.build_task_review(task, pair, from_v, to_v)`:
- repo tasks: DEFAULT pair `'round'` once `rounds.json` has ≥2 entries —
  `worktree.capture_diff_between(root, shaA, shaB)` (two-dot, SHA-validated);
  `'base'` = the old cumulative `changes.diff`. A diffed **Report entry** for
  `deliverable.md` (prev `_history` version vs live) is prepended so judge
  findings (which anchor to deliverable.md) always have a rendering surface.
- workspace tasks: `from_v`/`to_v` version pairs over `_history/vN`.
- UI: pair selector + **Findings panel** (`rvFindingsHTML`) listing every
  judge/critic/user comment, open + addressed, anchored rows jump to the line.

## 10. Settings reference (registry `settings_registry.py`)

| key | default | one line |
|---|---|---|
| judge.auto_scope | high_stakes | profile-less fallback: high_stakes \| sinks \| all_quality |
| judge.pregate / pregate_min_chars | 1 / 400 | free deterministic checks before loop judging |
| judge.max_runs | 4 | hard cap on loop-sourced judge calls per family |
| judge.delta_rejudge | 1 | round ≥2 fix-list + diff bundle |
| judge.screen | interior | GLM screen tier ('off' disables) |
| judge.cmd | cjudge {file} {domain} | gate stub hook — RESTORE after testing |
| frontier.task_cost_cap_usd | 3.0 | per-task frontier ceiling ×profile mult; 0=off |
| frontier.max_concurrent | 2 | shared judge/critic/escalation/eval/premortem semaphore |
| dispatch.rework_continue_session | 1 | first automated rework continues its session |
| dispatch.retry_slice_frac / rework_ceiling_mult | 0.5 / 2.0 | honest budgets |
| super.escalation (+_max, _trigger) | **1** / 1 / rewrite_or_cap | armed C1c ladder; profiles override the trigger |
| autopilot.auto_approve_ship_hours | 0 | Full-Auto + frontier-SHIP only (incl. HS); 0=never |

## 11. INVARIANTS — do not break these when improving

1. **A rework session must never be harvested as its own new result** — the
   `"Rework round for task {id}:"` epoch marker is what prevents the orphan
   ladder from resurrecting the rejected reply. If you change that string,
   change both the sender (`run_task_dispatch`) and the detector in one edit.
2. **A screen SHIP authorizes nothing**: not exemplars
   (`COALESCE(judge_tier,'frontier') != 'screen'` in `golden_exemplars`), not
   auto-approve, not "judged quality" anywhere new you add.
3. **The manual judge button is unconditional** — no pre-gate, no caps, no
   tier downgrade. Operator intent wins.
4. **Quota ≠ error**: rate-limit outcomes store 'interrupted' (judge) / NULL
   (critic) + backoff and never consume rounds, never escalate, never card.
5. **Judge loop and SR never run on the same task version** (super_result
   trigger presence skips `_sweep_task_loops`); they share `_retry_task` —
   any change to its signature/semantics must keep BOTH `origin` flavors and
   the SR e2e green.
6. **Only an operator decision re-arms a closed family** (reject →
   `reopen_judge_loop`). No sweep may clear the closed marker or reset
   `judge_round`.
7. **cjudge copies stay byte-identical** (setup/bin + ~/.local/bin; verify.sh
   diffs them) and rubric edits go to BOTH `~/knowledge` and
   `setup/knowledge/`.
8. **Round memory is file-based** (`_judge/round-N.json`) because the
   'running' flip NULLs `judge_output` — don't move it to the column without
   removing that NULL.
9. Every new frontier-adjacent call books to `frontier_ledger` with a distinct
   `kind` and respects `_FRONTIER_GATE` + the cost cap.
10. New settings need a registry entry + a verify.sh grep pairing key ↔
    consumer (house pattern, section 22).

## 12. Verification map

| gate | covers |
|---|---|
| `scripts/verify.sh` §22 (26 checks, total 481) | static presence: prompts, keys, plumbing, byte-identical copies |
| `scripts/verify_judge_loop_e2e.py` (41) | parsing/keys, pre-gate matrix, delta bundle + env plumbing, stubbed judge-thread drive, crash+reaper, [F#]/keep-session, closure/convergence/reopen, screen guards, round-pair review |
| `verify_mode_coherence_e2e.py` (47) | derive matrix, tier/sink/cost-cap, slice/ceiling/budget card |
| `verify_autopilot_e2e.py` (72) | presets incl. new sr_mode/auto-approve semantics |
| `verify_super_result_e2e.py` (90) | the SR side of the shared machinery |
| `verify_block2_e2e/_ui` (48/21) | review surface incl. repo snapshots |

Judge-stub tells (from [[judge-stub-leak-incident]]) still apply: identical
instant verdicts = a leaked `judge.cmd` stub; the loud "⚠ STUB JUDGE" first
line and startup restore guard it.

## 13. Known limitations / improvement backlog

- **UNMEASURED**: all quality-per-$ claims are engineering-grounded, not
  benchmarked. The A/B replay (`benchmarks/judge-loop-ab/RUNBOOK.md`, paid,
  operator-gated) is the designed proof; Phase 8 is the full campaign. Watch
  the review_comments severity mix over the first ~10 judged tasks for
  blocker-misclassification drift (SHIP-with-notes' main risk).
- Balanced interior stages are policed by the screen only — a mid-pipeline
  defect surfaces one stage later (at the frontier-judged sink). Rollback:
  `judge.screen=off`, or set the stage high_stakes.
- Deferred (designed, not built): `judge.pregate_tests` (run the Q3
  acceptance suite in a sandbox before judging implement stages — needs a
  worker-thread runner, never the 20s sweep thread); `judge.artifact_total_mb`
  knob; findings-chip "verified fixed" tie-in (delta verdicts → comment
  status); PATCH-time re-derive has no runtime gate check (registry grep only).
- The screen prompt is inline in `_screen_thread` (not a synced script like
  cjudge) — fine at one call site; extract it if a second consumer appears.
- `rounds.json` SHAs can dangle if the operator prunes/rebases the task
  branch — `build_task_review` falls back to 'base' when the diff comes back
  empty; a stronger fix would validate SHAs with `git cat-file`.
