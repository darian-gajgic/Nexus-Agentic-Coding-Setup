# EXECUTION RUNBOOK v2 — Quality Program (operator's step-by-step manual)

**Date:** 2026-07-10 (v2 — verified edition) · **For:** the operator (you), executing phase by phase.
**Verification status:** READY TO EXECUTE — second grounded pass at HEAD `9d385c7` (2026-07-10): all 9 Phase-1 findings re-confirmed in code with file:line evidence, all critic-check items (F1–F11) folded in, pricing re-verified against the authoritative API reference, all residual doc defects fixed. The verified findings ledger and all binding corrections live in `QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` (§4/§5) — where any other doc conflicts with the master plan, the master plan wins.
**What this delivers when finished:** Super Result fixed and verified → all quality levers + autopilot presets + Decisions inbox → Deep Plan mode → cost ledger + escalation ladder + rotation readiness → one properly-measured benchmark campaign answering "beats Opus 4.8 direct, cheaper than one Fable 5 pass."
**Plan docs this executes:** `QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` (state + findings + corrections), `SUPER-RESULT-PLAN-2026-07-09.md` (Appendix C), `DEEP-PLAN-MODE-PLAN-2026-07-10.md`, `QUALITY-AUTOPILOT-PLAN-2026-07-10.md` (incl. Part 4, binding).

---

## RULES FOR EVERY PHASE (read once, applies always)

1. **One session at a time.** Never run two implementation sessions in parallel — they share the working tree and the live service.
2. **Where:** open your normal terminal, then:
   ```bash
   cd ~/Nexus-Agentic-Coding-Setup
   ```
   Every session starts from this directory. All gate commands in this runbook are written to work from here (`app/.venv/bin/python app/scripts/<gate>.py` — there is no `.venv` or gate script at the repo root).
3. **Starting a session:** run `claude`. For long implementation phases you may prefer `claude --permission-mode acceptEdits` (auto-accepts file edits, still asks for risky commands) or your usual full-autonomy flag.
4. **Which model:**
   - **Implementation sessions (Phases 1, 3, 5, 7, 8): Opus 4.8** — the default; every decision is already made in the docs.
   - **Judge sessions (Phases 2, 4, 6, and the Phase-7 judge): Fable 5** — type `/model` after the session starts and select Fable 5. Judgment is where the strongest model pays.
5. **Fresh session per phase** — except Phase 2, which prefers RESUMING the original SR review session (`claude --resume`, pick it from the list); a fresh-session fallback is written into Phase 2.
6. **If a session asks you a design question**, reply:
   ```
   The decision is locked in the plan documents — follow them. QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §5 overrides on conflict. If the docs are genuinely wrong about the code, record the deviation in your report and continue.
   ```
7. **If a session runs very long / context fills up**, tell it:
   ```
   Write a handoff note of exactly where you are (step, files touched, what's left), commit your work, then stop.
   ```
   Then start a fresh session: `Read <plan doc> and the handoff note in your last commit; continue from step N.`
8. **If implementer and judge disagree:** don't referee it yourself — resume the planning conversation (`claude --resume`, the session that produced these docs) and paste both positions; it has the design context to arbitrate.
9. **After EVERY implementation phase, before moving on:**
   - [ ] `git log --oneline -10` shows the phase's commits;
   - [ ] the phase's gates printed green in the session;
   - [ ] `systemctl --user restart nexus` ran and https://127.0.0.1:8777 loads;
   - [ ] click around for 2 minutes — real usage catches what gates miss;
   - [ ] the report file for the phase exists at repo root.
10. **Database safety** before each schema-touching phase (1, 3, 5, 7):
    ```bash
    cp app/nexus.db app/nexus.db.bak-phase<N>
    ```
    (`.gitignore` already covers `*.bak-*` — verified.)
11. **Costs:** Phases 0–7 bill mostly your Claude subscription (sessions) + small GLM amounts for live smoke tests. Phase 8 spends real GLM + judge tokens on purpose — it is the one paid campaign.
12. **Anchors drift.** File:line references in the docs were verified at HEAD `9d385c7`. Sessions must re-locate by symbol name before editing — earlier phases shift later offsets.

---

## PHASE 0 — Housekeeping (you, 2 minutes, no AI)

```bash
cd ~/Nexus-Agentic-Coding-Setup
cp app/nexus.db app/nexus.db.bak-pre-quality-program
git status --short    # LOOK at this before staging anything
```

**Commit hygiene (critic check F1): never `git add -A` here.** The tree WILL contain
in-flight feature work alongside the docs (at the time of writing: an avatar torso pass —
modified `app/static/{index.html,jarvis3d.js}` plus untracked
`app/scripts/build_torso_from_scan.py` and `app/static/avatar/torso_scan.glb`). Rule:

1. **Anything that is not one of the six program docs gets its OWN commit first**, with a
   message describing that feature (e.g. `feat(avatar): torso scan pass`). If that work is
   still mid-flight in another session, FINISH AND COMMIT IT before starting the program —
   rule 1 (one session at a time) applies from here on.
2. Then stage exactly the six program docs and commit:

```bash
git add QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md \
        EXECUTION-RUNBOOK-2026-07-10.md \
        SUPER-RESULT-PLAN-Check.md \
        SUPER-RESULT-PLAN-2026-07-09.md \
        QUALITY-AUTOPILOT-PLAN-2026-07-10.md \
        DEEP-PLAN-MODE-PLAN-2026-07-10.md

git commit -m "docs: quality program verified — master plan + runbook v2 + critic check folded in"
```

**Done when:** `git status` shows a completely clean tree, the docs commit contains only
these six .md files, and any feature work sits in its own separate commit(s).

---

## PHASE 1 — Fix the 9 findings (implementation session, Opus 4.8)

**Purpose:** the grounded review found 2 blockers + 6 follow-ups, and the premortem added 1 critical (frontier backpressure). All 9 re-confirmed in code on 2026-07-10. **Nothing else may land first.**

```bash
cp app/nexus.db app/nexus.db.bak-phase1
```

Terminal → `cd ~/Nexus-Agentic-Coding-Setup` → `claude` → paste:

```
Read QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §4 COMPLETELY — it is the verified
findings ledger for this fix batch, with exact file:line evidence confirmed at HEAD
9d385c7 (re-locate by symbol before editing; offsets may have drifted). Fix all 9
findings, in ledger order:

BLOCKERS:
1. build_critic_sandbox (app/evals.py ~:411-429): in a fresh `git clone --local` the
   task branch exists only as origin/nexus/<slug> (created in a linked worktree —
   worktree.py ~:96; the main repo HEAD stays on base); the `git rev-parse --verify
   nexus/<slug>` guard fails, checkout is skipped, then `git remote remove origin`
   discards the only refs — the critic silently reviews the BASE branch. Fix: verify
   + checkout origin/<branch> (creating the local branch) BEFORE removing the remote;
   set repo_branch correctly in context.json.
2. _critic_thread (app/server.py ~:3930-3982): judge_model_for runs before any try;
   the parse block catches ONLY ValueError; _insert_critic_comments and the final
   UPDATE are unguarded — any other exception strands critic_verdict='running' until
   restart. Fix: persist the verdict before the comment insert and wrap the whole
   thread body in a catch-all that stores 'error' + logs.

CRITICAL (premortem P1):
3. FRONTIER BACKPRESSURE: the only headless-claude spawn paths are run_judge_cmd
   (evals.py ~:212/:230) and run_critic_cmd (~:525/:540), called from _judge_thread,
   _critic_thread, and the eval runner — all unbounded against one Claude CLI
   subscription. Add a global semaphore gating every frontier call (new setting
   frontier.max_concurrent, default 2 — mirror the GLM slot-gate pattern in
   hermes_dispatch ~:265-281), and classify CLI rate-limit/quota errors distinctly
   from content errors (stderr/exit patterns): on quota → backoff + requeue (mirror
   dispatch.quota_backoff_until, hermes_dispatch ~:403-439), NEVER store verdict
   'error' and NEVER escalate to the human on quota.

CORRECTNESS:
4. _repair_workflow (server.py ~:4866): `return tasks[:7]` (~:5030, hardcoded) runs
   AFTER the reconciler append (~:5005); with max_raw=7 under fan-out (~:5264) the
   appended reconciler is #8 and silently dropped. Never truncate quality-gate or
   reconciler tasks — cap before appends or exempt appended repair tasks.
5. Tasks attached to a super_result workflow inherit no flag (→ no loop). Fix BOTH
   doors — create_task (~:571) AND update_task's workflow_id PATCH path (~:641):
   when workflow_id points at a super_result=1 workflow and the body doesn't set the
   flag, inherit it and call _sync_super_result_loop. IMPORTANT: there is NO existing
   high_stakes inheritance pattern to mirror — high_stakes has the same gap (only the
   workflow-PATCH→members cascades exist, ~:5440/:5450). Write the inheritance fresh.
   Record the symmetric high_stakes gap in your report as a follow-up observation;
   do NOT change high_stakes behavior in this batch.
6. loop_engine.py ~:516-519: the `keys and set(keys) <= set(prev)` guard makes an
   empty-findings REVISE fall through to retry (~:543) instead of escalating — empty
   findings + REVISE is a contradiction; escalate it.

POLISH:
7. Broadcast task_updated on SHIP / escalation / stored-critic-verdict transitions
   (zero broadcasts exist in loop_engine.py; _critic_thread does log+notify only —
   the UI toast is dead on those paths).
8. POST /api/tasks/{id}/critic (~:3988-3998) is check-then-act — make it a CAS
   UPDATE (WHERE id=? AND verdict not 'running', rowcount==0 → 409), mirroring
   claim_task (~:2847-2860).
9. design_loop (loop_engine.py ~:148-160) emits a false "Speed mode" reasoning line
   when super_result suppresses auto_judge even though the user chose quality — fix
   the text to say the grounded critic replaces the judge.

Protocol: confirm each finding against HEAD before patching (record
"already-ok/not-reproducible" instead of patching if so). Each fix adds a regression
check to app/scripts/verify_super_result_e2e.py; finding 1 needs an UNSTUBBED
build_critic_sandbox test against a scratch git repo with a nexus/<slug> branch
(assert the sandbox tree contains the branch-only file); finding 3 needs: semaphore
honored under 3 parallel critic POSTs + a simulated quota error leaves the task
queued, not escalated. Afterwards run: bash app/scripts/verify.sh &&
app/.venv/bin/python app/scripts/verify_super_result_e2e.py &&
app/.venv/bin/python app/scripts/verify_block2_e2e.py &&
app/.venv/bin/python app/scripts/verify_block3_e2e.py. Finish by appending a
"Fixes 2026-07-10" section to IMPLEMENTATION-REPORT-SUPER-RESULT.md: per finding,
confirmed/fixed/already-ok + which regression check covers it. Commit (one commit
per finding or small coherent groups — never one blob).
```

**Expect:** 1–3 hours of agent work. **Done when:** rule-9 checklist passes and the report's Fixes section covers all 9.

---

## PHASE 2 — Re-verify the fixes (judge session, Fable 5)

Terminal → `claude --resume` → **pick the original Super Result review session** → paste:

```
The 9 findings (your 8 + premortem P1 frontier backpressure) have been fixed — see
the "Fixes 2026-07-10" section of IMPLEMENTATION-REPORT-SUPER-RESULT.md and the
latest commits. The canonical verified findings ledger is
QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §4. Verify the fix diff against the
findings: for each, confirm closed with evidence you personally observe (read the
diffs; re-run bash app/scripts/verify.sh and
app/.venv/bin/python app/scripts/verify_super_result_e2e.py yourself).
Verdict: SHIP, or the exact list of what remains.
```

**If the original session can't be resumed** (not in the list, or resumes compacted/unusable): start a FRESH `claude` session → `/model` → Fable 5 → use the Phase 4 grounded-critic template below with `<PLAN_DOC>` = `QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §4` and `<REPORT_DOC>` = the "Fixes 2026-07-10" section of `IMPLEMENTATION-REPORT-SUPER-RESULT.md`.

**If REVISE:** paste the remaining list back into the Phase 1 session (`claude --resume`, pick it) with `The judge says these remain — fix and update the report.` Repeat Phase 2. **Do NOT continue past here without SHIP.**

---

## PHASE 3 — Quality Autopilot (implementation session, Opus 4.8)

**The biggest phase.** `cp app/nexus.db app/nexus.db.bak-phase3` first. Expect the rule-7 handoff to be exercised.

Terminal → `claude` → paste:

```
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
```

**Done when:** rule-9 checklist + report exists + the Decisions view renders in the UI + the two preset card rows appear in the wizard.

---

## PHASE 4 — Judge Phase 3 (judge session, Fable 5, FRESH)

Terminal → `claude` → `/model` → **Fable 5** → paste:

```
You are the GROUNDED CRITIC for a completed implementation. Refute-by-default: no
claim is true until you verify it against the real system — the implementer's report
is not evidence.

Inputs: QUALITY-AUTOPILOT-PLAN-2026-07-10.md (the contract, incl. Part 4 premortem
resolution — binding; QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md §5 overrides on
conflict), IMPLEMENTATION-REPORT-QUALITY-AUTOPILOT.md (the claims), and the feature
commits in git log.

Method: (1) read plan then report; build a claim ledger from the plan's requirements
(all guardrail rules 1–12, L1–L4, P1–P10) + the report's claims. (2) Verify against
primary evidence: read the diffs; RUN every gate yourself (bash app/scripts/verify.sh;
app/.venv/bin/python app/scripts/verify_autopilot_e2e.py;
app/.venv/bin/python app/scripts/verify_super_result_e2e.py; Block2/3 e2e); drive the
new surfaces live over https://127.0.0.1:8777 — the Decisions inbox, one
exemplar-injected dispatch, the preset cards deriving knobs, an Eco+high_stakes task
still getting judged (rule 2). (3) Check every locked decision honored. (4)
Completeness pass: required-but-missing, added-but-never-asked, deviations justified
or not. Do NOT fix anything.

Output: findings most-severe-first with file:line + observed evidence + concrete fix;
per-item PASS/FAIL table; verdict SHIP or REVISE with the exact blocking list.
```

**If REVISE:** new Opus session with `Fix these judge findings — verify each against HEAD first, add a regression check per fix, update the report: <paste list>`, then send the diff back to this judge (`claude --resume`) for re-verification. Loop until **SHIP**.

---

## PHASE 5 — Deep Plan mode (implementation session, Opus 4.8)

`cp app/nexus.db app/nexus.db.bak-phase5` first. Terminal → `claude` → paste:

```
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
```

**Done when:** rule-9 checklist + a complex goal typed into the wizard shows the Deep Plan recommendation banner, and accepting it opens the chat+spec-pane modal.

---

## PHASE 6 — Judge Phase 5 (judge session, Fable 5, FRESH)

Same prompt as Phase 4 with these swaps:
- `<PLAN_DOC>` → `DEEP-PLAN-MODE-PLAN-2026-07-10.md`
- `<REPORT_DOC>` → `IMPLEMENTATION-REPORT-DEEP-PLAN.md`
- gate list → add `app/.venv/bin/python app/scripts/verify_deep_plan_e2e.py`
- the live-drive instruction becomes: "drive one Deep Plan session end-to-end over HTTPS with the planning model stubbed via `plan.stub`; verify the questions/spec/draft/critique/create flow and that SPEC.md lands as a workflow attachment and in the SR critic context."

REVISE → fix → re-verify → **SHIP**, same as before.

---

## PHASE 7 — Appendix C: ledger, escalation, rotation (implementation session, Opus 4.8)

`cp app/nexus.db app/nexus.db.bak-phase7` first. Terminal → `claude` → paste:

```
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
```

Then judge it: **fresh Fable 5 session**, Phase 4 template with `<PLAN_DOC>` = SR plan Appendix C + QA Part 4 P1/P5 + master plan §5 C-6/C-7/C-8, `<REPORT_DOC>` = `IMPLEMENTATION-REPORT-APPENDIX-C.md`; live-drive = one escalated rework on a scratch task + the ledger showing a $ total. REVISE → fix → **SHIP**.

---

## PHASE 8 — The measurement campaign (implementation session, Opus 4.8; the one paid benchmark)

**This phase spends real tokens on purpose** (GLM arms + judge calls + Fable 5 reference arms/judging). Run it when you won't need the machine's full attention for a day.

Terminal → `claude` → paste:

```
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
```

**Done when:** the win-rate/CI/cost matrix exists, WINS/LESSONS updated, and you have a measured answer to the founding question. Then (optional, per results): Q6 prompt-lab iterations, and the critic-only Fable 5 upgrade as a second cheap A/B (one registry row) — decide with the data.

---

## AFTER THE PROGRAM
- Set your defaults: Settings → autopilot default = Optimal + Assisted (or per Phase 8's data).
- Independent backlog unaffected and runnable anytime after Phase 2: B8–B10 batches and other feature work.
- Next tier rotation (Fable 5 as judge when affordable / GLM successor as executor): registry edits + re-run Phase 8. That's the whole procedure — that's what C2 bought you.

## QUICK REFERENCE — the whole program on one line each
| Phase | Who | Model | Input | Output | Gate to pass |
|---|---|---|---|---|---|
| 0 | you | — | git status | clean docs commit | tree clean, .md-only commit |
| 1 | fresh session | Opus 4.8 | master plan §4 | 9 fixes + regression checks | verify.sh + SR/Block2/Block3 e2e green |
| 2 | resumed (or fresh) judge | Fable 5 | fixes diff + report | SHIP | judge re-ran gates personally |
| 3 | fresh session | Opus 4.8 | QA plan (Part 4 binding) | Q1–Q5, L1–L4, Q7, N5–N7, B4 | verify_autopilot_e2e.py + UI surfaces |
| 4 | fresh judge | Fable 5 | QA plan + report | SHIP | live-drove Decisions/presets/Eco+HS |
| 5 | fresh session | Opus 4.8 | DP plan | Deep Plan mode | verify_deep_plan_e2e.py + banner→modal |
| 6 | fresh judge | Fable 5 | DP plan + report | SHIP | stubbed e2e session drive |
| 7 | fresh session + judge | Opus 4.8 / Fable 5 | SR App. C + §5 C-6/7/8 | ledger, escalation, registry roles | envelope-parse regression + $ total visible |
| 8 | fresh session | Opus 4.8 | master plan §7 | win-rate/CI/cost matrix | pre-registered thresholds honored |
