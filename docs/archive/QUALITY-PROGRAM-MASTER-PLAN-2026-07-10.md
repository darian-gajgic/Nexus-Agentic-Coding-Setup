# QUALITY PROGRAM — MASTER PLAN (verified edition)

**Date:** 2026-07-10 · **Status:** VERIFIED READY TO EXECUTE (second grounded pass at HEAD `9d385c7`)
**What this document is:** the single corrected, code-verified summary of the whole quality
program — what is already built, what remains, the exact defects to fix (with verified
file:line evidence), and every correction that overrides earlier doc text. Execute it via
`EXECUTION-RUNBOOK-2026-07-10.md` (v2, the operator manual). The three design docs remain
the DETAILED specs — this document does not replace them, it sits above them and resolves
their conflicts.

**Verification provenance:** grounded critic review 2026-07-10 (`SUPER-RESULT-PLAN-Check.md`,
verdict REVISE with 11 findings F1–F11) → all fixes folded into the docs → independent
second pass same day (3 parallel read-only code agents + pricing check against the
authoritative API reference): all 9 code findings re-confirmed present, all F-items
verified folded, 5 residual doc defects found and fixed (§5).

---

## 1. The goal

Make Nexus produce near-frontier-quality deliverables at sub-frontier cost, permanently:

- **Bulk executor** = best cheap model (today GLM-5.2).
- **Judgment roles** (critic / judge / spec / escalation) = best affordable frontier (today **Opus 4.8** via the Claude CLI subscription).
- **Top tier** (today **Fable 5**) is NEVER a system component — it is the reference bar and the blind judge in benchmark campaigns only.
- **Success criterion per model generation:** system win-rate vs judgment-tier-direct measured properly (see §7), at mean $ per task below one top-tier direct pass.
- On each model generation, every role rotates up one tier (registry edits only — that is what C2 buys) and the benchmark re-runs.

## 2. Where the system stands today (verified against code at `9d385c7`)

**Implemented and gate-green:**
- **Super Result** (grounded critic loop): Steps 0–10 + N1–N4 + B-items, commits `c16e18f…df67c6f`. Artifacts verified present: `app/scripts/verify_super_result_e2e.py` (32 checks), `verify_block2_e2e.py`, `verify_block3_e2e.py`, verify.sh §17, `cverify`/`cjudge` (setup/bin ↔ ~/.local/bin byte-identical), B1 boot-reset (`server.py:112-118`), B8 sweep filters (`loop_engine.py:455,461`).
- Unrelated features since committed: STT/dictation consolidation (`81e876d`), hologram avatar P1–P6 + cyan look pass (`906b3c0…9d385c7`), full-stack preview v3.5 (`ca0616f`).

**NOT implemented yet (the program):**
- The 9-finding fix batch (§4) — **nothing else may land first**.
- Quality Autopilot: Q1–Q5, L1–L4, Q7a/b/c, guardrail rules 1–12, plus still-open N5/N6/N7 and B4 (verified absent: no `judge.auto_scope`, `replan.auto_draft`, `judge.on_blind_reject` settings exist).
- Deep Plan mode (all of it).
- Appendix C: C3 cost ledger → C1 escalation ladder → C2 registry-only roles (verified: `db.MODEL_PURPOSES` is still `("complicated","easy","mechanical","frontier_judge")` — no `spec_model`/`escalation_model`).
- Phase 8: the one paid measurement campaign (C4 + Step 11 + Q6), with the §7 methodology rules.

**Current dirty tree (Phase 0 input):** the six program docs (3 modified + this file, the runbook, and the check report untracked) plus whatever feature work is in flight at commit time — as of this writing an avatar torso pass (`app/static/{index.html,jarvis3d.js}` modified; `app/scripts/build_torso_from_scan.py` + `app/static/avatar/torso_scan.glb` untracked). Phase 0's rule is state-robust: feature work gets its own commit(s) first, then the six docs commit alone. Never `git add -A`.

## 3. Build order (operator decision, final)

1. **Phase 1** — fix the 9 findings (§4). 2. **Phase 2** — judge re-verifies → SHIP.
3. **Phase 3** — Quality Autopilot (Q1–Q5 + L1–L4 + Q7 + rules 1–12 + N5–N7 + B4). 4. **Phase 4** — judge → SHIP.
5. **Phase 5** — Deep Plan mode. 6. **Phase 6** — judge → SHIP.
7. **Phase 7** — Appendix C (C3 → C1a/C1c/C1b/C1d → C2; C4 deferred; C6 already = Q2; C5 = thresholds only) + judge → SHIP.
8. **Phase 8** — the ONE paid measurement campaign (§7). Everything above ships heuristic/unmeasured until then — recorded risk, accepted.

Benchmarks are deferred to Phase 8 by operator decision (token saving). Anything that shows measured harm or cost-without-benefit gets disabled then; **absence of evidence alone never disables a feature** (§7).

## 4. The 9 fixes — verified findings ledger

All confirmed present at HEAD `9d385c7` on 2026-07-10 with the evidence below. Anchors are
exact at that commit — re-locate by symbol before editing. Fix protocol: confirm against
HEAD first; each fix adds a regression check to `app/scripts/verify_super_result_e2e.py`.

**BLOCKERS**

1. **Critic reviews the wrong branch for repo tasks.** `build_critic_sandbox` (`app/evals.py:411-429`): `git clone --local` of the operator's main repo → the task branch `nexus/<slug>` exists in the clone only as `refs/remotes/origin/nexus/<slug>` (the branch is created in a linked worktree by `worktree.py:96-97`; the main repo HEAD stays on base) → the guard `git rev-parse --verify nexus/<slug>` (`:421-423`) fails → checkout skipped, `repo_branch` stays None → `git remote remove origin` (`:428-429`) discards the only refs. The critic silently reviews the BASE branch and `context.json` doesn't say so. **Fix:** verify + checkout `origin/<branch>` (create the local branch from it) BEFORE removing the remote; record `repo_branch` correctly; regression check = an UNSTUBBED sandbox test against a scratch git repo with a `nexus/<slug>` branch, asserting the sandbox working tree contains the branch-only file.
2. **`_critic_thread` strands `critic_verdict='running'`.** (`app/server.py:3930-3982`): endpoint sets 'running' then spawns (`:3997-3999`); inside the thread, `judge_model_for` (`:3940`) runs before any try; the parse block catches ONLY `ValueError` (`:3949`); `_insert_critic_comments` (`:3966`) and the final UPDATE (`:3967-3971`) are unguarded. Any other exception kills the thread with the row stuck at 'running' until restart (B1 boot-reset at `:112-118` only heals AT restart). **Fix:** persist the verdict before the comment insert, and wrap the whole thread body in a catch-all that stores 'error' + logs.

**CRITICAL (premortem P1)**

3. **No frontier backpressure.** The only headless-claude spawn sites are `run_judge_cmd` (`evals.py:212` template, `:230` sp.run) and `run_critic_cmd` (`:525`, `:540`), called from `_judge_thread`, `_critic_thread`, and the eval runner — all via bare `threading.Thread(...).start()`, no shared cap, against ONE Claude CLI subscription with hard usage ceilings. Only GLM-side caps exist (`hermes_dispatch.py:265-281`). **Fix:** a global semaphore gating every frontier call (new setting `frontier.max_concurrent`, default 2 — mirror the GLM slot-gate pattern), plus quota-vs-content error classification from stderr/exit patterns: on quota → backoff + requeue (mirror `dispatch.quota_backoff_until`, `hermes_dispatch.py:403-439`), NEVER store verdict 'error', NEVER escalate to the human on quota. Regression checks: semaphore honored under 3 parallel critic POSTs; simulated quota error leaves the task queued, not escalated.

**CORRECTNESS**

4. **Truncation drops the appended reconciler.** `_repair_workflow` (`server.py:4866`): `max_raw` caps only the input (`:4881`); the reconciler is appended at `:5005`; the return hard-caps at `return tasks[:7]` (`:5030`, hardcoded, not `max_raw`); fan-out passes `max_raw=7` (`:5264`) so the appended reconciler is #8 and silently dropped. The same cap can also drop impl-path verifier/fix appends at 7 raw tasks. **Fix:** never truncate quality-gate/reconciler tasks — apply the cap before appends, or exempt appended repair tasks.
5. **Tasks attached to a super_result workflow inherit no flag** (→ no loop). `create_task` (`server.py:571`) inserts only `body.super_result` (`:598`), syncs only `if body.super_result` (`:601-602`); `update_task` applies `body.workflow_id` (`:641-642`) with no inheritance and syncs only when `body.super_result` is explicitly set (`:667-678`). **Fix BOTH doors:** when `workflow_id` points at a `super_result=1` workflow and the body doesn't set the flag, inherit it and call `_sync_super_result_loop`. **Binding correction:** there is NO existing high_stakes inheritance pattern to mirror — high_stakes has the SAME gap; only the workflow-PATCH→members cascades exist (`:5440` / `:5450-5453`). Write the inheritance fresh; record the symmetric high_stakes gap in the report as a follow-up observation, do NOT change high_stakes behavior in this batch.
6. **Empty-findings REVISE retries instead of escalating.** `loop_engine.py:516-519`: `keys and set(keys) <= set(prev)` — empty `keys` skips the convergence escalation and falls through to retry (`:543`). Empty findings + REVISE is a contradiction; escalate it.

**POLISH**

7. **No WS broadcast on verdict transitions.** Zero `broadcast` calls in `loop_engine.py`; SHIP path (`:496-504`) and `_escalate_super` (`:398-441`) do log+desktop-notify only; `_critic_thread` stores the verdict (`server.py:3968`) with no `task_updated` broadcast. The UI toast is dead on those paths. **Fix:** broadcast `task_updated` on SHIP / escalation / stored-verdict transitions.
8. **Critic endpoint 409 is check-then-act.** `run_critic` (`server.py:3988-3998`): read → check `=='running'` → unconditional `UPDATE ... WHERE id=?`. Two concurrent POSTs both pass. **Fix:** CAS UPDATE — `WHERE id=? AND (critic_verdict IS NULL OR critic_verdict!='running')` + `rowcount==0 → 409`, mirroring `claim_task` (`:2847-2860`) / `db.claim_task_cas`.
9. **False "Speed mode" reasoning line.** `design_loop` (`loop_engine.py:148-149`): `super_result` forces `auto_judge=False`; the `elif judge_ok and high_stakes` branch (`:156-160`) then emits "Speed mode: the judge is NOT run automatically…" even when the user chose quality — the suppression cause is Super Result, not speed. **Fix the text** (say the grounded critic replaces the judge).

## 5. Binding corrections (override any conflicting earlier text)

| # | Where the old text lives | Correction (now binding) |
|---|---|---|
| C-1 | old runbook Phase 0 | Avatar recolor is COMMITTED (`9d385c7`). The only non-doc dirt is `app/static/avatar/_probe_scan.glb` — delete it, never stage it. |
| C-2 | old finding-5 text ("mirror the high_stakes cascade semantics") | FALSE — no such inheritance exists to mirror; see §4.5. |
| C-3 | QA plan Part 4 P1 ("added … as finding 9") | Backpressure is **finding 3** in the fix batch; finding 9 is the Speed-mode text. (Fixed in the doc.) |
| C-4 | QA Part 5 / DP Step 10 gate paths | Gates live at `app/scripts/verify_autopilot_e2e.py` and `app/scripts/verify_deep_plan_e2e.py`. Verification commands: `app/.venv/bin/python app/scripts/<gate>.py` from the repo root (no root `.venv`; root `scripts/` holds only `refresh-app.sh`). |
| C-5 | DP Step 10 stub wording ("settings-stubbed command or fixed Hermes stub") | The mechanism is a new **`plan.stub`** setting that short-circuits the Hermes session turn with canned slot-filling replies, mirroring `evals.stub` (`evals.py:669`, which stubs the eval-runner GENERATION path only). The judge/critic command-template stubs do not apply to session turns. |
| C-6 | SR plan Appendix C build order | Superseded: Phase 7 builds C3 → C1a/C1c/C1b/C1d → C2; C4 deferred to Phase 8; C6 already lands as Q2 (Phase 3); C5 = escalation-threshold settings only. |
| C-7 | C1c "≥ judgment-tier-direct by construction" | Softened: the floor *approaches* judgment-tier-direct; it is an empirical claim (a bad dossier can anchor the rework below a clean direct pass). Phase 8 measures it where cheap. |
| C-8 | Phase 7 output contract | Adding `claude -p --output-format json` wraps the reply in a JSON envelope `{result, usage, total_cost_usd, modelUsage}`. Verified: cverify/cjudge emit plain text today and `parse_critic_json`/`parse_judge_metrics` sentinel-parse raw stdout — they BREAK unless `run_critic_cmd`/`run_judge_cmd` unwrap `.result` before parsing. Persist `usage` + `total_cost_usd` (the envelope's API-equivalent dollars are authoritative for frontier runs; the price table covers GLM + display). |
| C-9 | Phase 8 judging | Position-swapping does NOT remove self-preference (Panickssery et al., NeurIPS'24): every pair involving the Fable-5-direct arm is dual-judged by Opus 4.8, agreement reported. |
| C-10 | Phase 8 statistics | n≈12 cannot support win-rate>50% or any revert rule (7/12 → 95% CI ≈ [32%,81%]). Run ≥3 seeds per task per arm (~36+ comparisons per arm-pair), report exact binomial CIs, pre-register thresholds, and classify features three-way: measured benefit / measured harm-or-cost-without-benefit (disable candidates) / insufficient evidence (keep, re-test). Never disable on absence of evidence. |

## 6. Document map (what is authoritative for what)

| Document | Authoritative for |
|---|---|
| `EXECUTION-RUNBOOK-2026-07-10.md` (v2) | HOW to execute: phases, exact prompts, models, gates, failure paths. **Start here.** |
| this file | Program state, verified findings ledger (§4), binding corrections (§5), Phase-8 methodology (§7). Overrides conflicting text anywhere else. |
| `SUPER-RESULT-PLAN-2026-07-09.md` | Super Result design reference (§6 steps — implemented, do not re-implement) + Appendix A (N5–N8) + Appendix B (B4) + Appendix C detailed specs. |
| `QUALITY-AUTOPILOT-PLAN-2026-07-10.md` | Q1–Q7, L1–L4, guardrail rules 1–12, Part 4 premortem fixes (P1–P10, binding), Part 5 gates — the Phase 3 contract. |
| `DEEP-PLAN-MODE-PLAN-2026-07-10.md` | Deep Plan design — the Phase 5 contract (locked decisions §3; premortem-fix notes inline). |
| `SUPER-RESULT-PLAN-Check.md` | Historical record of the grounded critic review (F1–F11). Superseded where §5 corrects it. |
| `MODEL-PRICING-2026-07-10.md` | Price table (re-verified 2026-07-10: Opus 4.8 $5/$25, Fable 5 $10/$50 per MTok; cache write 1.25×, read 0.1× → $6.25/$0.50 and $12.50/$1). Compare DOLLARS, not tokens (newer tokenizer ≈ up to +30–35% tokens for the same text). |
| `IMPLEMENTATION-REPORT-SUPER-RESULT.md` | What the SR implementation actually did; Phase 1 appends its "Fixes 2026-07-10" section here. |

## 7. Measurement methodology (Phase 8 — binding)

1. **Arms:** system-SR (Optimal profile), GLM-5.2-direct, Opus-4.8-direct, Fable-5-direct (reference). Suite ~12 tasks (3 × coding / research-audit / content / long-project) incl. the original stability-audit brief; deep-plan-vs-quick-plan on complex rows; 2–3 rows additionally under Eco and Smart (smoke tests, not validation).
2. **Judging:** blind pairwise by Fable 5, provenance stripped, positions swapped, rubric-anchored — AND every pair involving Fable-5-direct is also judged by Opus 4.8 (dual-judge; report agreement; flag disagreements for human review) per C-9.
3. **Statistics:** ≥3 independent seeds per task per arm; exact binomial 95% CIs, never bare win-rates; pre-registered decision thresholds; three-way feature classification per C-10.
4. **Success criterion:** the 95% CI of system win-rate vs Opus-4.8-direct excludes 50% (from below = a measured loss, report it honestly), at mean $ below one Fable-5-direct pass (dollars from the C3 ledger).
5. **Also:** define "Optimal" empirically (log (route, correctness, cost) per case → oracle cheapest-correct frontier → weighted harmonic mean, β≈0.1 → tuned triage thresholds as a Decisions card); check for router collapse; where cheap, add an escalated-rework-vs-direct row (C-7). Log outcomes to `~/knowledge/feedback/WINS.md` / `LESSONS.md`.

## 8. Definition of done

- Phases 1–7 each end with an independent judge verdict of **SHIP** (grounded, refute-by-default, gates re-run by the judge personally).
- After Phase 8: a win-rate/CI/cost matrix exists; WINS/LESSONS updated; defaults set from data (autopilot involvement + spend profile); disable-candidates list contains only measured-harm items.
- Standing rules that survive the program: every phase updates the JARVIS system-control framing and re-runs the JARVIS gates (QA rule 12); Fable 5 never gets assigned to a registry purpose; tier rotation = registry edits + Phase 8 re-run.
