# Block 3 — Wizard plan editing · Mid-run replanning · Eval corpus

Roadmap block 3 (agreed 2026-07-08). Three features, one theme: **close the loop
between planning, failure, and measurable quality.**

## R1 — Plan editing in the wizard proposal modal

The proposal modal (multi-task plans) becomes a real plan editor, not just a
keep/skip list.

- R1.1 Every proposed task row has ✏️ Edit: title, description, specialist
  (live roster dropdown), domain, model, high-stakes, budget, and dependencies
  (earlier tasks only — the acyclic-by-construction invariant is preserved in
  the UI itself).
- R1.2 ➕ Add task appends an operator-authored task (removable with 🗑;
  wizard-proposed tasks keep the existing keep/skip checkbox, quality gates
  stay locked).
- R1.3 On Create, an EDITED plan is first revalidated server-side by
  `POST /api/tasks/wizard/revalidate` — the same deterministic
  `_repair_workflow()` that guards LLM output guards operator edits (gate
  insertion, dep fixing, specialist whitelist, model floors). If the repair
  changed anything, the modal re-renders with the repaired plan + repair notes
  and the operator confirms once more; an unrepaired plan creates immediately.
- R1.4 `GET /api/specialists/names` — lightweight roster (name + description
  only, no qdrant scroll) for the editor dropdown.
- R1.5 Single-task plans keep the existing flow (prefilled create form — it is
  already a full editor).

## R2 — Mid-run replanning after stage failures

When a pipeline stage fails, the system offers a replanning checkpoint instead
of leaving a stalled DAG. **Three separate gates, by design** (loop-engine
touchpoint — gated carefully):

- R2.1 DETECTION is automatic and free (no LLM): the loop-engine sweep flags a
  workflow `replan.status='needed'` when (a) a member task hits terminal
  `dispatch_state='failed'`, or (b) the acceptance verifier reports FAIL and no
  automatic fix round remains (loop absent / open / trigger exhausted).
  blocked_budget / blocked_quota are NOT failures (they self-resolve). A
  dismissed replan is not re-flagged for the same failed task.
- R2.2 DRAFTING is operator-triggered (`POST /api/workflows/{id}/replan/draft`,
  async thread like the judge): the planning-only wizard session receives the
  original goal, the DAG with per-task status, the failure evidence, and the
  done tasks as fixed context — and must return a plan for the REMAINING work
  only. Output goes through `_repair_workflow()`. Server restart mid-draft
  resets `drafting` → `needed` at boot (same pattern as stuck judges).
- R2.3 APPLYING is operator-approved and editable
  (`POST /api/workflows/{id}/replan/apply` with the — possibly edited — task
  list; the proposal opens in the R1 plan editor). Apply refuses while any
  member task is actively executing (409). Superseded non-done tasks become
  `status='archived'` (kept for audit, released from claims, excluded from
  rollups/board/loop-engine); new tasks are created in Backlog wired to
  each other and to every done predecessor (roots inherit them as INPUT);
  loop-trigger round counters reset (a new plan earns fresh rounds).
  `POST .../replan/dismiss` closes the checkpoint without acting.
- R2.4 Ownership: draft/apply/dismiss are `_owned_workflow`-gated; new tasks
  belong to the workflow owner; engine acts through DB state, notifications
  target the owner.

## R3 — Eval corpus (remediation #6)

Fixed per-domain eval briefs, executed through the REAL dispatch framing and
scored by the frontier judge against the domain RUBRIC — so a playbook/prompt
change is measured, not vibes-checked.

- R3.1 Corpus: `~/knowledge/domains/<domain>/evals/*.md` — frontmatter
  (`title:`, optional `specialist:`, `model:`, `notes:`) + body = the fixed
  brief. Human-editable, git-versioned with the knowledge base. Every domain
  with a RUBRIC.md ships ≥2 cases.
- R3.2 Runner (`evals.py`): sequential background thread per run. Each case
  builds a synthetic task and uses `hermes_dispatch.build_framing()` — the
  exact framing real tasks get (playbook injection, specialist delegation,
  rubric self-score) — into a fresh user-scoped session (deleted afterwards);
  deliverable lands in `workspaces/evals/<run>/<case>/deliverable.md`; then the
  judge (`judge.cmd`, shared runner with the task judge) scores it against the
  domain rubric. Parsed per case: verdict (SHIP/REVISE/REWRITE), score `X/Y`,
  gate PASS/FAIL counts. Raw judge output is stored.
- R3.3 A run records a **config fingerprint** (hashes of PLAYBOOK, RUBRIC,
  specialist definitions, STYLE-VOICE, BUSINESS-CONTEXT at run time): two runs
  with different fingerprints measure the change between them.
- R3.4 Tables `eval_runs` / `eval_results` (additive, user-scoped fail-closed).
  Endpoints: `GET /api/evals` (corpus), `POST /api/evals/run` (409 while
  another run is active; refuses during quota backoff), `GET /api/evals/runs`,
  `GET /api/evals/runs/{id}`, `GET /api/evals/runs/{id}/file`,
  `POST /api/evals/runs/{id}/cancel`.
- R3.5 UI: Specialists view gains subtabs — 🧑‍🔬 Team (existing) and 📏 Evals:
  domain cards (case count, last score, Run button), run history with score
  trend + Δ vs the previous run of the same domain, run detail modal with
  per-case scores and judge output.
- R3.6 Test hooks (gates only, default off): settings `evals.corpus_root`
  (redirect corpus discovery) and `evals.stub` (canned generation — the judge
  stays stubbable via the existing `judge.cmd`). Both restored by the gate;
  no simulated data ever ships by default.

## Verification

- Static: `bash scripts/verify.sh` (new Block-3 checks: endpoints exist,
  evals module + corpus parse, replan detection present, app.js functions,
  `?v=` bump).
- Runtime: `.venv/bin/python scripts/verify_block3_e2e.py` — revalidate
  round-trip (gate re-insertion, dep repair), replan detect→dismiss→draft-less
  apply with archival + rewiring proof, eval run lifecycle on a scratch corpus
  with stubbed generation + judge, per-user isolation (user B sees nothing),
  self-cleaning.
- Existing suites must stay green: agentic 30, playwright 11, v3 UI 24,
  interactions 24, multiuser 83, real-dispatch 54.
