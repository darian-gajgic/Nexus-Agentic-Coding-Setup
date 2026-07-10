# SUPER-RESULT-PLAN-Check — grounded-critic review of the quality-program plan set

**Date:** 2026-07-10 · **Critic:** Claude Fable 5 (fresh session, refute-by-default)
**Inputs reviewed:** `EXECUTION-RUNBOOK-2026-07-10.md`, `SUPER-RESULT-PLAN-2026-07-09.md` (incl. Appendix C), `QUALITY-AUTOPILOT-PLAN-2026-07-10.md`, `DEEP-PLAN-MODE-PLAN-2026-07-10.md`, `MODEL-PRICING-2026-07-10.md`, `IMPLEMENTATION-REPORT-SUPER-RESULT.md`, git history `c16e18f…df67c6f` + HEAD `906b3c0`, live working tree, live code (`app/server.py`, `app/evals.py`, `app/loop_engine.py`, `app/scripts/`), the local `claude` CLI, and web research on judging methodology.
**Standard:** no claim accepted without primary evidence I personally observed (code read, command run, or cited literature).

## Verdict

**REVISE (targeted) — the program is coherent, well-grounded, and executable, but 3 findings should be fixed *before* Phase 0/1 run and 2 methodology findings before Phase 8 spends real tokens.** The core claim ledger holds up unusually well: all 9 Phase-1 findings are real at HEAD (verified with file:line below), every cross-document reference resolves, the pricing/tokenizer/CLI-capability claims check out against primary sources, and the architecture matches the state of the art it cites. The failures found are at the edges: an operational trap in Phase 0, two gaps the fix batch forgot, one path bug that will break the Phase 2 judge, and two benchmark-methodology claims that are refuted by the literature and by arithmetic.

---

## Findings (most severe first)

### F1 — BLOCKER (operational): Phase 0 `git add -A` buries a complete, unrelated STT/dictation feature inside a `docs:` commit
- **Where:** `EXECUTION-RUNBOOK-2026-07-10.md:41-48` (Phase 0).
- **Evidence observed:** `git status`/`git diff --stat` on the live tree: `app/voice.py` (475 lines changed), `app/server.py` (+133, all in STT/dictation hunks — zero mentions of "critic" in the diff), `app/settings_registry.py` (+146), `app/scripts/verify.sh` (+21), `app/requirements.txt`, `app/static/jarvis3d.js` (926 lines), `app/vision.py`, `app/static/index.html`, both `nexus.service` units — plus 8 untracked files (`app/dictation*.py` ×4, `app/stt_worker.py`, `app/scripts/verify_stt_e2e.py`, `setup/systemd/nexus-cleanup-llm.service`, `system/nexus-cleanup-llm.service`). This is the completed STT/dictation consolidation feature, not documentation. The runbook was written assuming only the plan docs were dirty.
- **Why it matters:** ~1,250 lines of feature code land under the message "docs: quality program plans finalized…". History becomes unauditable; a later revert/bisect of the quality program drags the voice stack with it; the pre-commit hook runs `verify.sh` over a mixed change with no dedicated review.
- **Fix:** split Phase 0 into two commits: first `feat(stt): dictation + meetings consolidation (whisper stt_worker, overlay, cleanup unit)` staging exactly the STT files, then the docs commit as written. `.gitignore` already covers `nexus.db.bak-*`/`*.bak-*` (verified), so the DB backup is safe either way.

### F2 — HIGH (methodology, blocks Phase 8's validity): "provenance stripped + position-swapping kills position/self-preference bias" is false for self-preference
- **Where:** `SUPER-RESULT-PLAN-2026-07-09.md:409` (Appendix C4: "provenance stripped, pairwise with position-swapping (kills position/self-preference bias)") and the runbook Phase 8 prompt (`EXECUTION-RUNBOOK-2026-07-10.md:270-271`).
- **Evidence observed:** position swapping addresses *position* bias only. Self-preference does not require provenance labels: LLM evaluators recognize their own unlabeled generations and favor them, with self-preference strength causally linked to self-recognition accuracy — [Panickssery et al., *LLM Evaluators Recognize and Favor Their Own Generations*, NeurIPS 2024](https://arxiv.org/abs/2404.13076) ([OpenReview](https://openreview.net/forum?id=4NJBV6Wp0h)); follow-up work confirms the bias survives blinding ([Quantifying and Mitigating Self-Preference Bias of LLM Judges](https://arxiv.org/pdf/2604.22891)). Phase 8's judge is Fable 5 and one of the four arms is **Fable-5-direct** — the judge scores its own generations in every comparison involving the reference arm.
- **Why it matters:** the reference arm's win-rate is inflated, so the founding narrative "system quality approaches one Fable-5 pass at lower $" is measured against a self-flattered bar. The primary criterion (system vs Opus-4.8-direct) is less contaminated but same-family style preference remains unquantified.
- **Fix:** for any pair involving the judge's own arm, use a second judge (Opus 4.8) or dual-judge both models and report agreement; at minimum, annotate all Fable-5-direct comparisons in the output matrix as upper-bound-biased. One sentence in the Phase 8 prompt.

### F3 — HIGH (methodology, blocks Phase 8's decisions): n≈12 cannot support "win-rate > 50%" as a success criterion, and cannot support the revert rule
- **Where:** `SUPER-RESULT-PLAN-2026-07-09.md:409` (C4, "~12-task suite"), runbook Phase 8 ("Success criterion: system win-rate vs Opus-4.8-direct > 50%… list features showing no measurable delta as disable candidates"), `QUALITY-AUTOPILOT-PLAN-2026-07-10.md:132` (Part 3 item 8: "anything that doesn't show a delta gets reverted or disabled then").
- **Evidence observed (arithmetic, checkable):** 7 wins of 12 = 58% observed carries an exact binomial 95% CI of ≈ [32%, 81%] — indistinguishable from a coin flip. Detecting a true 65%-vs-50% difference at 80% power needs ~85 paired comparisons. The Eco/Smart behavioral validation runs on n=2–3 rows — directional at best. Under these sample sizes, "no measurable delta" is the *expected* outcome for real-but-moderate effects, so the Part-3 revert rule will systematically fire on noise and disable features that work.
- **Fix:** (a) run ≥3 independent seeds per task per arm (~36+ comparisons per arm-pair) — cheap relative to the campaign; (b) report exact binomial CIs, not point win-rates; (c) pre-register the decision thresholds; (d) treat "no evidence yet" as a third outcome distinct from "no effect" — only revert on evidence of harm or clear cost-without-benefit; (e) treat the Eco/Smart rows as smoke tests, not validation.

### F4 — MEDIUM (forgotten adjustment in the Phase 1 batch): finding-5's fix covers `create_task` only, but `update_task` can also attach a task to an SR workflow
- **Where:** runbook Phase 1 finding 5 ("inherit the workflow flag **in create_task** when workflow_id is set"); code at `app/server.py:641-642`.
- **Evidence observed:** `TaskUpdate` (server.py:313) accepts `workflow_id`, and `update_task` applies it (`if body.workflow_id is not None: updates["workflow_id"] = body.workflow_id or None`). A task PATCHed into a `super_result=1` workflow after creation inherits neither the flag nor the loop trigger — exactly the same hole as finding 5, via a second door the fix text doesn't mention.
- **Fix:** extend the Phase 1 prompt's finding 5 to cover the `update_task` workflow_id path (inherit flag + `_sync_super_result_loop`), with its own regression check.

### F5 — MEDIUM (forgotten adjustment in Phase 7/C3): capturing usage via `claude -p --output-format json` changes the runner output contract that the sentinel parsers consume — no plan mentions this
- **Where:** `SUPER-RESULT-PLAN-2026-07-09.md:408` (C3) and runbook Phase 7 ("Capture frontier token usage via claude -p --output-format json usage fields").
- **Evidence observed (live run on this machine):** `claude -p "…" --output-format json` returns a single JSON envelope — the model's reply is inside `.result`, alongside `usage{input_tokens, output_tokens, cache_*}`, `total_cost_usd`, and per-model `modelUsage[*].costUSD`. Today `cverify`/`cjudge` emit plain text and `parse_critic_json`/`parse_judge_metrics` (`app/evals.py`) extract sentinel-fenced JSON from that raw stdout. Flip the flag without unwrapping `.result` and **both parsers break** — every critic run stores `error`.
- **Also an opportunity:** the envelope already computes API-equivalent dollars (`total_cost_usd`, `modelUsage.costUSD`), so the ledger can store the CLI's own figure for frontier runs instead of recomputing usage × price table (keep the table for GLM and for display).
- **Fix:** Phase 7 prompt should state explicitly: cverify/cjudge adopt `--output-format json`; `run_critic_cmd`/`run_judge_cmd` unwrap `result` before sentinel parsing and persist `usage` + `total_cost_usd`; the transcript-size estimate stays as fallback. Add a regression check that a stubbed JSON-envelope output still parses.

### F6 — MEDIUM (doc coherence): the SR plan still declares itself "NOT IMPLEMENTED"
- **Where:** `SUPER-RESULT-PLAN-2026-07-09.md:3` — "**Status:** APPROVED DESIGN, NOT IMPLEMENTED. Execute in a dedicated session."
- **Evidence observed:** steps 0–10 landed as commits `c16e18f…df67c6f` (git log verified); `IMPLEMENTATION-REPORT-SUPER-RESULT.md` exists and details them; `QUALITY-AUTOPILOT-PLAN-2026-07-10.md:6` itself says "(implemented; 2 REVISE blockers pending)". The Phase 7 session is instructed to read this plan — a stale "NOT IMPLEMENTED, execute this" header at the top of the file it must treat as context invites confusion or re-implementation.
- **Fix:** one-line header edit in Phase 0: "IMPLEMENTED 2026-07-10 (c16e18f…df67c6f, see IMPLEMENTATION-REPORT-SUPER-RESULT.md); Appendix C still open."

### F7 — MEDIUM (runbook bug): Phase 2's literal verification command fails from the directory the runbook puts the operator in
- **Where:** `EXECUTION-RUNBOOK-2026-07-10.md:127-128`: "re-run bash app/scripts/verify.sh and `.venv/bin/python scripts/verify_super_result_e2e.py` yourself".
- **Evidence observed:** every session starts at `~/Nexus-Agentic-Coding-Setup` (rule 2). From there, `.venv/` does not exist (the venv is `app/.venv/`, verified with `ls`) and `scripts/` does not exist (the gate is `app/scripts/verify_super_result_e2e.py`, verified present). The judge will hit file-not-found; worst case it concludes the gate is missing and issues a false finding. Phase 1's "scripts/verify_super_result_e2e.py" wording has the same ambiguity.
- **Fix:** correct both prompts to `app/.venv/bin/python app/scripts/verify_super_result_e2e.py`.

### F8 — LOW/MEDIUM (overclaim): C1c's "system ≥ judgment-tier-direct **by construction**" is not by construction
- **Where:** `SUPER-RESULT-PLAN-2026-07-09.md:405` (C1c).
- **Evidence observed:** the argument assumes the escalation dossier (draft + critic findings + contradiction list) is net-positive input. The plan's own §7 concedes grounded critics invent problems (CriticGPT data), and anchoring on a flawed draft can drag a rework *below* a clean direct pass. "Worst case the judgment-tier model writes the final version with better inputs" is an empirical claim, not a construction. It's also setting-gated (`super.escalation`) — off by default, so the guarantee doesn't even engage unless enabled.
- **Fix:** soften the wording ("designed so the floor approaches judgment-tier-direct") and, if cheap, add an escalated-rework-vs-direct ablation row to the Phase 8 campaign so the claim gets measured rather than assumed.

### F9 — LOW (underspecified gate hook): Deep Plan's e2e stub for the *planning conversation* has no existing injection point
- **Where:** `DEEP-PLAN-MODE-PLAN-2026-07-10.md:122` (Step 10: "stub the planning model turns via a settings-stubbed command or fixed Hermes stub like eval's `evals.stub` pattern").
- **Evidence observed:** `evals.stub` exists (`app/evals.py:669`) but it stubs the *eval-runner generation* path. Deep Plan sessions run through Hermes chat sessions (`hermes_dispatch`), which have no equivalent stub today — the judge/critic stubs (`judge.cmd`, `super.critic_cmd`) are command templates, a different mechanism. The Phase 5 implementer must invent the hook; "or" phrasing leaves the gate design ambiguous.
- **Fix:** name the mechanism in the Phase 5 prompt (e.g. a `plan.stub` setting that short-circuits the turn call with canned slot-filling replies, mirroring `evals.stub`).

### F10 — LOW (async hygiene): Deep Plan's `/turn` endpoint will block the event loop unless threadpooled
- **Where:** `DEEP-PLAN-MODE-PLAN-2026-07-10.md:100` (Step 4 endpoints).
- **Evidence observed:** `POST /api/plan/sessions/{id}/turn` synchronously awaits a Hermes model turn (seconds–minutes). The B7 no-block-in-async rule is cited elsewhere in these plans (SR Step 5c does it right) but not here; `check_async_blocking.py` exists as a backstop but the plan should not rely on the gate catching a foreseeable design omission.
- **Fix:** one line in the DP plan/Phase 5 prompt: "turn/draft/critique endpoints run blocking work via `run_in_threadpool` (B7)."

### F11 — LOW (operational fragility): Phase 2 hard-depends on resuming "the original SR review session"
- **Where:** `EXECUTION-RUNBOOK-2026-07-10.md:21,121`.
- **Evidence observed:** not verifiable from here — which is the point: the runbook has no fallback if that session is gone, compacted past usefulness, or was run from a different directory (resume lists are per-project-dir). **Do NOT continue past here without SHIP** then deadlocks on a missing session.
- **Fix:** add a fallback line: "if the resume is unusable, start a FRESH Fable 5 session using the Phase 4 grounded-critic template with `<PLAN_DOC>` = the findings list (QA Part 4 P8+P1) and `<REPORT_DOC>` = the Fixes section."

---

## Claim ledger — verified PASS items (primary evidence)

The refute-by-default pass **confirmed** the following; these are the load-bearing claims and they hold:

| # | Claim | Evidence personally observed |
|---|-------|------------------------------|
| 1 | Phase-1 finding 1 (sandbox misses task branch) is real | `app/evals.py:380-433`: `git clone --local` → `rev-parse --verify nexus/<slug>` (fails in a fresh clone; branch exists only as `origin/…`, and resolution via `refs/remotes/` needs a remote literally named `nexus`) → checkout skipped → `remote remove origin` discards the only refs. Critic reviews the base branch. CONFIRMED |
| 2 | Finding 2 (`_critic_thread` strands 'running') is real | `app/server.py:3930-3982`: endpoint sets `critic_verdict='running'` *before* spawning; thread catches only `ValueError` from parse — exceptions in `judge_model_for`, `_insert_critic_comments`, or the final UPDATE strand 'running' until restart (B1 boot-reset only fixes it *at* restart). CONFIRMED |
| 3 | Finding 3 (no frontier backpressure) is real | grep across `server.py`/`evals.py`/`hermes_dispatch.py`: no semaphore, no `frontier.max_concurrent`; only GLM `dispatch.max_concurrent*` caps exist (`hermes_dispatch.py:267-277`). Spawn-site inventory complete: cjudge/cverify are the only headless-claude paths (evals.py:212, 525) — P1's fix list covers them all. `dispatch.quota_backoff_until` pattern exists to mirror (`hermes_dispatch.py:403-439`). CONFIRMED |
| 4 | Finding 4 (`tasks[:7]` drops the appended reconciler) is real | `app/server.py:5030` returns `tasks[:7]` *after* the reconciler append at :4995-5008; with `max_raw=7` under fan-out (:5264) the appended reconciler is #8 and silently truncated. CONFIRMED |
| 5 | Finding 5 (no flag inheritance on later-added tasks) is real | `create_task` (server.py:571-604) inserts `body.super_result` only; no workflow lookup. CONFIRMED (and extended — see F4) |
| 6 | Finding 6 (`keys and` guard) is real | `app/loop_engine.py:519`: empty-findings REVISE never satisfies `keys and set(keys) <= set(prev)` → falls through to retry instead of escalating. CONFIRMED |
| 7 | Finding 7 (no WS broadcast on SHIP/escalation) is real | zero `broadcast` calls in `loop_engine.py`; `_critic_thread` does log+notify_desktop only — `task_updated` fires only from HTTP endpoints. CONFIRMED |
| 8 | Finding 8 (critic 409 TOCTOU) is real | `app/server.py:3996-4000`: read-check-then-UPDATE, no CAS. CONFIRMED |
| 9 | Finding 9 (false "Speed mode" line) is real | `app/loop_engine.py:148-161`: `super_result=True` forces `auto_judge=False`, and the `elif judge_ok and high_stakes` branch then emits "Speed mode: the judge is NOT run automatically…" even when the user chose quality. CONFIRMED |
| 10 | Canonical findings list resolves | QA plan Part 4 P8 (2 blockers + 6 follow-ups) + P1 = exactly the runbook's 9 numbered findings. Commit range `c16e18f…df67c6f` matches git log |
| 11 | All runbook cross-references resolve | Q1–Q7/L1–L4/rules 1–12/P1–P10/Part 5 exist in the QA plan; DP §3 locked decisions + all four premortem-fix notes exist; Appendix C build-order supersession note present in the working-tree SR plan; C6=Q2, N5–N7 = SR Appendix A Tier 2, B4 = Appendix B — all check out |
| 12 | Pricing table is correct | `MODEL-PRICING-2026-07-10.md` matches the runbook verbatim, and both match the authoritative Claude API reference: Opus 4.8 $5/$25, Fable 5 $10/$50, cache write 1.25× (5-min TTL), cache read 0.1×. The "~30% more tokens" tokenizer note is corroborated by official guidance (~1×–1.35× on the Opus 4.7+ tokenizer vs older models; Fable 5 = same tokenizer as Opus 4.8) — the doc's advice to compare dollars, not tokens, is sound |
| 13 | CLI capability claims hold | `claude --help`: `--output-format json` present; `--allowedTools`/`--disallowedTools`/`--permission-mode` all present (SR §4.3b's "verified on this machine" re-verified). Live `-p --output-format json` run returns `usage` + `total_cost_usd` + `modelUsage` — C3 is feasible (with the F5 caveat) |
| 14 | Implementation artifacts exist as the runbook assumes | `app/scripts/verify_super_result_e2e.py` (32 checks), `verify_block2_e2e.py`, `verify_block3_e2e.py`, verify.sh §17 "SUPER RESULT" section, `setup/bin/cverify` + `~/.local/bin/cverify` (both 7,094 B, executable), `IMPLEMENTATION-REPORT-SUPER-RESULT.md` (honest §5 "what was NOT done"). Service URL `https://127.0.0.1:8777` matches `server.py:7254` |
| 15 | Claimed-implemented B-items actually landed | B1 boot-reset of orphaned `critic_verdict='running'` (`server.py:~114`); B8 sweep state filters (`loop_engine.py:453-462` — status IN ('review','done') AND dispatch_state='completed', so archived/blocked/mid-dispatch never touched); B2 JARVIS framing documents SR (`server.py:2061`) |
| 16 | Uncommitted code does not collide with the program | `git diff app/server.py` contains zero critic/SR hunks (STT endpoints + startup only) — Phase 1's edits won't conflict textually, only historically (F1) |

## Architecture & value assessment (method step 4)

**The design is sound and the goal coherent.** The three-plan stack implements exactly what the 2023–2026 evidence it cites prescribes, and the citations check out where I verified them: grounded tool-using critics over document-only judges (CRITIC, Agent-as-a-Judge, CriticGPT), external cross-model feedback over self-refinement (Huang ICLR'24), fan-out with a reconciling verifier over debate-to-consensus (Anthropic multi-agent research), structured localized feedback over scores (Self-Refine ablations), hard stops + cost gating for loops. The tier principle (cheap executor + judgment-tier verification, top tier as reference-only) is the economically correct way to chase frontier quality at sub-frontier cost, and C2/C3 (registry-only roles + full-cost ledger) are precisely the infrastructure that makes the claim testable and the rotation cheap. The premortem layers (QA Part 4, DP fixes) caught real issues — P1 backpressure in particular is confirmed-critical by code inspection.

**Where it is weakest, in order:** (1) the *measurement* leg — the one paid campaign is the program's epistemic foundation, and F2/F3 show its two headline mechanisms (blind judging, win-rate criterion) are currently specified in a way that cannot deliver the certainty the program plans to act on (feature reverts, threshold tuning, default profiles); (2) *unmeasured heuristics shipping in bulk* — the plans are candid about this (C1/C5/profile bands "HEURISTIC and unmeasured"), which is honest, but it raises the stakes on fixing F3 since Phase 8 is the sole validation event for everything; (3) *sheer Phase-3 scope* — Q1–Q5 + L1–L4 + Q7a/b/c + 12 guardrails + N5–N7 + B4 in one session is the largest single bet in the runbook; the handoff protocol (rule 7) mitigates but expect it to be exercised.

**Not findings, worth knowing:** the runbook's "judge sessions on Fable 5" does not contradict "Fable 5 is never a system component" — interactive dev-time review is the reference-model role the tier principle assigns it. And the ~5–10× SR cost estimate remains consistent with the cited multi-agent literature (~15× for full fan-out).

## Bottom line for the operator

Fix before running anything: **F1** (split the Phase 0 commit), **F7** (Phase 2 path), **F6** (SR status header — one line). Fold into Phase 1's prompt: **F4** (update_task inheritance). Fold into Phase 5/7 prompts: **F5, F9, F10**. Fix before spending Phase 8 tokens: **F2, F3** (a few sentences in the prompt buy the campaign its validity). **F8, F11** are wording/fallback insurance. Everything else in the plan set verified clean — proceed.
