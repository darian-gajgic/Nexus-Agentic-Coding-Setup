# Quality-Loop & Frontier-Judge Improvement — Findings + Proposal

**Status:** PARKED for a dedicated session. Not part of the stability bugfix batches. Read-only analysis; nothing implemented.
**Date opened:** 2026-07-09
**Author:** Opus 4.8 (frontier side), during the Nexus stability-fix work.
**Companions:** `STABILITY-AUDIT-2026-07-08.md`, `FIX-RUNBOOK-2026-07-08.md`.

---

## 0. Why this document exists (in one paragraph)

While fixing the Nexus stability bugs, we noticed something bigger: **Nexus's own quality loop (the frontier judge + `loop_engine`) does not reliably drive an analytical deliverable to its best form.** The evidence: the operator ran the *same* stability-audit prompt through Nexus as a workflow ("Nexus stability audit"), which produced three recon reports. Reports 1 & 2 were well-formatted but reached the **wrong root-cause conclusion**, and the internal judge did not catch it. The report only became genuinely good (Report 3) **after the operator manually rejected it and injected an external frontier critique** (this side's review of reports 1 & 2). The self-improvement was driven by a human carrying external feedback in — not by the loop. This document captures why, and proposes how to make the loop produce that quality automatically.

---

## 1. What we observed (the evidence)

- **Same input, three outputs.** The operator gave the identical stability-audit prompt to (a) this frontier side, which produced `STABILITY-AUDIT-2026-07-08.md` (a deep code audit, 86 verified defects), and (b) Nexus-as-a-workflow, which produced three "Regression Recon Brief" reports over successive runs.
- **Reports 1 & 2 were confidently wrong on the headline.** Both concluded *"the system is not broken at the code level — verify.sh passes 251/251 and the JARVIS e2e passes, so the instability is an upstream Z.AI 429 storm + runtime resource exhaustion, not an application regression."* They were well-structured, cited, and **self-scored ~4.0 against their own rubric.**
- **That conclusion was substantively wrong.** The dominant instability driver was a *code* problem — **systemic event-loop blocking** (`async def` handlers doing blocking work on the single uvicorn loop; `/api/stats` `psutil(interval=0.5)` every 3 s; ~15 more sites) — which produces latency/stalls that **never write an error line**, so a logs-first recon can't see it. Reports 1 & 2 mistook "green tests + noisy logs" for "healthy code."
- **The internal judge did not catch this.** Reports 1 & 2 passed their own quality bar.
- **Report 3 improved dramatically — but only after external feedback.** The operator fed this side's critique of reports 1 & 2 back in and rejected report 2; the re-run produced Report 3, which **adopted the correct root cause** (event-loop blocking + JARVIS regressions), **re-verified against source**, correctly **refuted 2 of this side's own findings** (watchdog stuck-lane is config-gated; slot-keying is mainly the fallback path — both verified true), and even **added a finding this side missed** (the Wav2Lip `/talk`+`/lipsync` endpoints are live+reachable, not dormant).
- **The complementarity is the point.** Nexus's briefs contributed genuinely-additive **runtime forensics** this side under-covered (189/454 executor-resume dispatches, 16 graceful-shutdown-timeout tracebacks, 10 CUDA-OOM events, restart/memory-pressure counts, integration/doc-drift items). This side contributed the **code-deep root causes** the briefs missed (the systemic event-loop blocking; 86 file:line defects). **The best output was the UNION of the two — and today nothing produces that union automatically.**

---

## 2. How the loop + judge actually work today (grounded, with file refs)

### 2.1 `loop_engine.py` — the closed-loop quality engine
- Background thread, ~20 s sweep. Two modes per task/project:
  - **open** — engine only *detects*; every failed verification or judge-REVISE is a human checkpoint.
  - **closed** — engine auto-feeds findings back and re-runs, up to a round cap.
- Triggers (`design_loop`, ~line 51):
  - **`verify_fail`** (~line 77): verifier task FAILs → retry the *fix* task with the verifier's findings → re-verify. Round-capped.
  - **`judge_revise`** (~line 108): high-stakes + judgeable domain → the frontier judge grades the deliverable against the domain RUBRIC; on REVISE/REWRITE it sends findings back, re-runs, re-judges. Terminal on SHIP or round-cap.
  - **`auto_judge`** (~line 126): quality + high-stakes + closed → the judge runs automatically on fresh deliverables.
- Bounded: per-trigger round caps, 3 actions per sweep, token budgets. Speed mode = judge not auto-run.

### 2.2 The judge — `evals.run_judge_cmd` (~line 152) + `cjudge`
- Invoked as `cjudge {file} {domain}` (settings `judge.cmd`), which runs a **headless `claude -p`** with `cwd=~/knowledge`, `JUDGE_MODEL` = the resolved frontier-judge assignment (**`claude-opus-4-8`**, route=cli), reading **both** the deliverable file (copied into `~/knowledge/.nexus-judge-tmp`) **and** the domain RUBRIC tree.
- It emits a free-form verdict parsed (`_extract`, ~line 216) into the **cjudge contract: SHIP / REVISE / REWRITE**.
- **Crucially: the judge reads the artifact + the rubric. It does NOT independently investigate the system** — it does not run the verify scripts, tail the logs, or read the source the report is *about*.

### 2.3 The rubric — `~/knowledge/domains/software-engineering/RUBRIC.md`
- **Gates G1–G10** are all *code-change* oriented: G1 test suite passes, G2 lint/typecheck, G6 authz test, G8 down-migration, G9 diff hygiene, etc.
- **Dimensions D1–D7** are code-quality/form dimensions: D1 "correctness vs spec (*backed by citations*)", D4 readability, D7 operability.
- **Kill list**: amateur/AI-slop markers.
- There is **no gate for "did you reach the correct diagnosis, and did you independently verify it?"**

---

## 3. Root-cause diagnosis — why the loop underperformed

Two structural reasons, plus the empowering punchline:

1. **The judge grades the *report*, not the *system*.** Because `cjudge` only reads the deliverable + rubric, it cannot catch omissions or a wrong conclusion that a well-formed report hides. When reports 1 & 2 were internally consistent with their own (green-tests) evidence, the judge had nothing to contradict them with → SHIP. The external critique worked precisely because it brought **independent evidence** (a separate deep audit) — a different *mechanism* than grading a document.
2. **Wrong rubric for the deliverable type.** An analytical/audit report was graded against a **code-diff** rubric whose hard gates (G1–G10) don't even apply to a read-only brief, and whose soft dimensions reward **form, citations, readability** — which a polished-but-wrong report passes at ~4.0. There is no rubric for "investigation/diagnosis" deliverables that would gate on verified conclusions.
3. **PUNCHLINE — it's a role problem, not a model problem.** The frontier judge is **already Opus 4.8**, the same model as the external critic. The capability is present; it simply isn't *asked* to independently investigate and adversarially refute. **This is fixable with prompt/rubric/workflow changes — no model upgrade, minimal new infrastructure.**
4. **No union of independent passes.** The best result came from reconciling two independent investigations with different blind spots (runtime-forensics vs code-deep). Today the pipeline is one executor → one grader; there is no step that runs multiple independent investigations and reconciles their union.

---

## 4. Proposal — make "two independent investigations, reconciled" the default

All items below are prompt / rubric / wizard-template changes. **No new infrastructure required.** Gate them to **high-stakes analytical/audit/review deliverables** so cost stays bounded.

### P1 — Add an "analysis/audit" rubric (substance gates)
Create an investigation rubric (new `~/knowledge/domains/.../RUBRIC.md` or a shared `investigation` rubric the judge selects by deliverable type) with binary gates the current rubric lacks:
- **A1 — Verified, not inferred.** Every load-bearing conclusion is independently verified against *primary* evidence (a command run, a log line, source read). A proxy inference (*"tests pass" ⇒ "code correct"*) fails A1. **Reports 1 & 2 fail A1 outright.**
- **A2 — Alternatives ruled out.** The top symptom's competing explanations are explicitly considered and eliminated with evidence.
- **A3 — Coverage.** Each named subsystem was actually investigated (not just listed); uncovered areas are stated as gaps.
- **A4 — Re-verify borrowed claims.** Claims taken from another source/report are re-checked against the source, not trusted. (This is literally the lesson Report 3 wrote in its own "Learn" section — bake it into the rubric.)

### P2 — Upgrade the judge's *role* for claim-bearing deliverables (highest leverage)
Change the `cjudge` prompt (or add a `verifier` variant selected for analytical deliverables) so that, **before scoring**, it:
- **Independently checks the deliverable's load-bearing claims against the real system** (run the verify scripts, read the cited source, tail the logs), and
- Operates **refute-by-default** (try to prove the conclusion wrong), and
- Emits **cited, actionable findings** (file:line / log line / "you concluded X but Y disproves it"), not just an abstract score.
This is the single change that would have caught reports 1 & 2 with zero human intervention.

### P3 — Fan-out + reconcile pipeline for high-stakes audit/analysis goals (bigger win)
For "audit / analyze / review / investigate" goals, the wizard should propose **2–3 independent investigators** (different framings — e.g. runtime-forensics angle vs code-deep angle) → a **reconciliation pass** that takes the **union** of their findings and adversarially verifies each. This covers each investigator's blind spot by design and reproduces — automatically — the union that gave the best result here. (This is the multi-agent fan-out+verify pattern the frontier audit used internally.)

### P4 — Keep the critic independent of the executor
Run the verifier/critic in a **fresh context** that does not see the author's reasoning, so it can't inherit the same blind spot (why cross-context review beats self-review). Same model (Opus 4.8) is fine as long as the *role* is "refute with independent evidence."

### P5 — Completeness-critic pass
A final agent whose only job is: *"What's missing — a subsystem not investigated, a claim unverified, an evidence source not checked?"* This directly closes the "each side found what the other missed" gap.

### Suggested phasing
1. **First: P1 (A1 gate) + P2 (independent-verification judge role).** Cheapest, highest leverage; would have caught reports 1 & 2 alone.
2. **Then: P3 (fan-out + reconcile)** once P1/P2 prove out — the largest quality gain, more work.
3. **Refinements: P4, P5.**

---

## 5. Open questions to decide in the dedicated session

- **Cost gating.** Independent verification + fan-out is expensive. Confirm it fires only for high-stakes analytical deliverables (extend the existing `high_stakes` + judgeable-domain gate). Everyday code tasks keep the current judge.
- **Evidence access & safety.** The judge runs headless `claude -p` with `cwd=~/knowledge`. For P2 it needs to *run commands / read the target repo* to verify claims. How is that scoped safely? (Permission model, which commands are allowed, guardian implications, not letting the judge mutate state.) This is the biggest design question.
- **Deliverable-type detection.** How does the loop know a deliverable is "analytical/audit" (→ investigation rubric) vs "code diff" (→ current rubric)? Task template? Domain? An explicit `deliverable_type` field?
- **Interaction with the eval corpus.** The eval runner already shares `run_judge_cmd`. Any new rubric/verifier role must stay compatible with `evals.py` and the config-fingerprint scoring.
- **Verdict semantics.** Does an A-gate failure map to REVISE or REWRITE? Should there be a distinct "conclusion unverified" verdict?
- **Round caps vs correctness.** If the verifier keeps finding unverified claims, how many rounds before it escalates to a human?

---

## 6. Evidence appendix (file:line, contracts, artifacts)

- **Loop:** `app/loop_engine.py` — modes/open-closed (docstring ~L5-12); `design_loop` ~L51; `verify_fail` trigger ~L77; `judge_revise` ~L108; `auto_judge` ~L126; `_verdict_from_summary` ~L197; `_sweep_workflow_loops` ~L228.
- **Judge:** `app/evals.py` — `judge_model_for` ~L139; `run_judge_cmd` ~L152 (`judge.cmd` default `cjudge {file} {domain}`, `cwd=~/knowledge`, `JUDGE_MODEL`/`JUDGE_ANTHROPIC_API_KEY` env, deliverable copied to `~/knowledge/.nexus-judge-tmp`); verdict extraction `_extract` ~L216 (**SHIP / REVISE / REWRITE** contract). `cjudge` lives at `~/.local/bin/cjudge` and runs headless `claude -p`; frontier judge seeded as `claude-opus-4-8` (route=cli) in the model registry.
- **Rubric:** `~/knowledge/domains/software-engineering/RUBRIC.md` — gates G1–G10 (code-diff oriented), dimensions D1–D7 (form/quality), kill list. No conclusion-verification gate.
- **Artifacts:** the three Nexus recon briefs (in the workflow output / operator's hand) + `STABILITY-AUDIT-2026-07-08.md`. Report 3's own "Learn" section states the exact lesson to institutionalize: *"when two sources conflict on a load-bearing claim, the source code is the tiebreaker, never a third summary"* and *"verify.sh passing while the app is unstable is the key diagnostic — existence gates can't see behavior."*

---

## 7. Relationship to the stability work

This is a **meta-improvement** (how Nexus *produces and quality-gates* work), orthogonal to the stability **bugfixes** (Batches 1–7 in `FIX-RUNBOOK-2026-07-08.md`). It is intentionally **parked** until the fix batches are done. Note the one small overlap: Batch 6 fixes `loop_engine.py`'s fragile substring verdict parsing (F033) — unrelated to this proposal, but touches the same file, so sequence this work *after* Batch 6 to avoid churn.
