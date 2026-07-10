# IMPLEMENTATION REPORT — Super Result (grounded quality loop)

**Date:** 2026-07-10 · **Implements:** `SUPER-RESULT-PLAN-2026-07-09.md` Steps 0–10,
Appendix A Tier 1 (N1–N4 incl. the eval-corpus compatibility block), Appendix B
items B1, B2, B3, B5, B6, B8 (+B9, a one-toast nicety folded into the same WS
handler edit). **Intentionally NOT done** (per operator instruction): N5–N8, B4,
and Step 11 (measurement — separate session).
**Discipline:** one commit per step, `bash app/scripts/verify.sh` green before
every commit (pre-commit hook enforces it), service restarted only via
`systemctl --user restart nexus`, `app.js ?v` bumped 73→74.

## 1. What was built, per step

- **Step 0 — preconditions.** Nothing to commit: the working tree was already
  clean (see Deviation 1).
- **Step 1 — migrations + seed** (`app/database.py`, commit `c16e18f`). 8 new
  task columns (`super_result`, `deliverable_type`, `critic_verdict`,
  `critic_output`, `critic_json`, `critic_ts`, `critic_round`, `critic_keys`),
  `workflows.super_result`, `review_comments.source` (DEFAULT 'user'), settings
  seed `super.critic_cmd = "cverify {file} {domain} {sandbox}"`. Verified live
  via read-only PRAGma after restart.
- **Step 2 — settings section** (`app/settings_registry.py`, `2957dd7`). New
  `super` section: critic_cmd / max_rounds(3) / timeout_s(1500) /
  max_findings(25) / fanout_default(1) / fanout_n(3) / keep_sandbox(0);
  `PREFIXES` picked `super.` up automatically. Verified via
  `GET /api/settings/schema` + `sreg.conf`.
- **Step 3 — cverify** (`setup/bin/cverify` + `~/.local/bin/cverify`,
  `9a60113`). cjudge's MODEL_ARGS/KEY_ENV/env-scrub reused verbatim; argv
  contract `<file> <domain|-> <sandbox>` with a hard requirement on
  `_critic_context/context.json`; `--permission-mode acceptEdits` + allow list
  + deny rules (git push/remote, gh, sudo); claim-ledger →
  refute-by-default → contradictions → completeness → rubric-gates method
  prompt; sentinel-fenced JSON schema incl. optional `learning_note` (B6);
  honesty note (accident boundary, not adversary boundary) in the header.
  **Hand-tested for real** against a throwaway sandbox with three planted false
  claims: the critic *executed the sandbox code*, refuted all three with real
  command output as evidence, returned valid sentinel JSON (verdict REWRITE),
  and the real repo was untouched. `setup/install.sh` chmod line extended.
- **Step 4 — critic engine** (`app/evals.py`, `cd7e0dd`).
  `detect_deliverable_type` (explicit column → structural signals → keyword
  regex → content), `type_rubric_path` (analysis/research →
  `<knowledge root>/rubrics/INVESTIGATION.md`), `_scrubbed_env` (§4.3c regex,
  JUDGE_ANTHROPIC_API_KEY re-added by the runner), `build_critic_sandbox`
  (24h crash sweep; workspace copytree excluding `_critic*`/node_modules/
  `.venv*`/`.next`/dist/build/`__pycache__` and INCLUDING `_history/`,
  `deliverable.v*.md`, `attachments/`; repo tasks `git clone --local` +
  branch-checkout via `hermes_dispatch._repo_slug` + `git remote remove
  origin`, failure → `repo_note`; `_critic_context/` with domain rubric, type
  rubric, BUSINESS-CONTEXT, DONE-predecessor sibling reports, exact
  `context.json` schema incl. `open_comments`), `run_critic_cmd` (mirrors
  `run_judge_cmd`: shlex tokens, `~/.local/bin` PATH fallback, owns timeout
  `super.timeout_s`, `finally:` rmtree unless `super.keep_sandbox=1`),
  `parse_critic_json` (sentinel extract + last-balanced-`{}` fallback, verdict
  enum required, limits clamped, `..` traversal → anchor dropped,
  workspace/repo prefix normalization, severity sort + max_findings cut,
  `_keys` sha1 fingerprints for convergence). **N1:** `run_judge_cmd(...,
  type_rubric=None)` optional param + `{type_rubric}` token +
  `JUDGE_TYPE_RUBRIC` env; `_judge_thread` resolves it per task; the eval
  runner passes it ONLY when a case opts in via new optional frontmatter
  `deliverable_type`; `fingerprint()` now hashes `~/knowledge/rubrics/*.md`.
  Verified via stubbed `run_critic_cmd` against a real done task (sandbox
  created+destroyed, parse validated, env scrub leak-free, setting restored).
- **Step 5 — server wiring** (`app/server.py` + evals parse addition,
  `64d5ecc`). `_critic_thread` (round bookkeeping, `critic_keys`
  {round,keys,prev}, error path → verdict 'error' for sweep escalation,
  desktop notify); `_insert_critic_comments` (supersede-then-insert per §4.4,
  anchor validation: realpath-prefix check, ±2-line quote match, `line_text`
  taken from the REAL file, `_COMMENT_MAX_OPEN` respected, severity-ordered
  input so the cap drops least-severe); `POST/GET /api/tasks/{id}/critic`
  (owner-gated, 400 no deliverable, 409 running, blocking work in the thread);
  `_retry_task`: `[CRITIC]/[JUDGE]/[REVIEWER]` tags, approval expiry widened to
  `('deliverable','super_result')`, fb cap 8000→16000 (§4.8), **N4** prefer
  parsed `revision_brief`; flag plumbing: TaskCreate/TaskUpdate fields +
  `deliverable_type` 400-validation, create/update_task, create/update_workflow
  (cascade mirrors high_stakes), `_sync_super_result_loop` (regenerate design
  preserving used counts / strip trigger), loop_design meta, `decide_approval`
  `super_result` branch (approve → mark_super_done; reject → threadpool
  `_retry_task` + bump_super_round), replan_apply passthrough; **B1** startup
  reset of orphaned `critic_verdict='running'` → 'error'; **N3** judge
  auto-comments (`source='judge'`) from the judge's parsed findings; **N2
  parse side**: `parse_judge_metrics` best-effort sentinel-JSON tail
  (findings/revision_brief/verdict fallback), strictly additive; user-comment
  INSERT hardcodes `source='user'`. Verified 23/23 over HTTPS with a stubbed
  critic (incl. supersede round 2, convergence keys, retry drain).
- **Step 6 — loop engine** (`app/loop_engine.py`, `5429452`). `design_loop`
  emits the `super_result` trigger first and guards `judge_revise`/`auto_judge`
  off when the flag is set (§4.5) + reasoning line; `_sweep_super_result`
  (called before `_sweep_workflow_loops`): own + inherited candidates
  (task-level `super_result=1`, review/done + dispatch completed → **B8**
  archived/blocked/mid-dispatch never touched), critic on fresh deliverables
  in BOTH modes, per-version idempotence via `state`/`state_tasks`
  `{kind, handled_ts}` (mirrors `used_tasks`), SHIP quiet terminal, error /
  convergence (`round>1 and keys ⊆ prev`) / round-cap escalations via direct
  `approvals` INSERT (`action_type='super_result'`, payload
  {task_id, round, findings, verdict, reason?}, pending-checkpoint dedupe,
  desktop notify), open-mode checkpoint, closed-mode `_api` retry with
  `SUPER RESULT round N/M` + `revision_brief[:2500]` feedback + round bump;
  `bump_super_round` / `mark_super_done` exported for decide_approval;
  belt-and-braces super-trigger skip in `_sweep_task_loops`. Verified 24/24
  against the REAL in-server sweep (closed auto-retry, convergence escalation,
  once-per-critique idempotence, SHIP, open checkpoint, approve/reject).
- **Step 7 — wizard fan-out** (`app/server.py`, `cd567dd`). `task_wizard`
  accepts `super_result` + `fanout` (None → `super.fanout_default`), passes
  `fanout_n`; framing gains the SUPER RESULT FAN-OUT block (analysis:
  {fanout_n} lens-investigators + reconciler; coding: TWO parallel lens
  reviewers, NEVER parallel implementations, fix+verifier gate on both;
  content/research: 2 drafts + adversarial synthesis; ≤7 tasks;
  non-parallelizable fallback) and a `deliverable_type` TASK FIELD;
  `max_raw=7` under fan-out; deterministic post-step sets
  `workflow.super_result` + sink-task flags (single-task plans too);
  `_clamp_wizard_task` passes `super_result`/`deliverable_type` through;
  `_repair_workflow`: `rev_is` generalization (dep-repair per reviewer, fix
  task waits for ALL reviews, verifier gates on `sinks | rev_is | spec`),
  reconciler enforcement (`fanout`/`investigation`/`draft` tags ≥2 + no coding
  pipeline → append `_reconciler_gate_task` or complete its deps). Verified
  via `/api/tasks/wizard/revalidate` (reconciler appended as unique sink with
  flags; 2-reviewer coding plan correctly wired).
- **Step 8 — knowledge layer + N2** (`a036a60`).
  `~/knowledge/rubrics/INVESTIGATION.md` (live; committed to the knowledge
  repo) + vendored `setup/knowledge/rubrics/INVESTIGATION.md`: gates
  A1 VERIFIED-NOT-INFERRED / A2 ALTERNATIVES-RULED-OUT / A3 COVERAGE /
  A4 RE-VERIFY-BORROWED-CLAIMS + 4 scored dimensions (evidence density,
  falsifiability, contradiction handling, actionability), /16 bands. **N2**
  cjudge upgrade (both copies): refute-by-default stance, ONE binary gate
  table across all rubrics read, `JUDGE_TYPE_RUBRIC` dual-rubric grading,
  sentinel `NEXUS_JUDGE_JSON` tail (verdict/findings≤15/revision_brief),
  Learning-note kept. Era boundary: eval `fingerprint()` also hashes
  `~/.local/bin/cjudge`. `setup/install.sh` now installs `setup/knowledge` →
  `~/knowledge` (full copy when missing, additive otherwise);
  `sync-brain.sh` carries cverify.
- **Step 9 — frontend + JARVIS** (`d78c514`). `superChip` on kanban cards and
  project-detail task rows (roll-up, B5); deliverables tab + JARVIS deck
  critic badges (B5, server payload extended); 🤖/⚖ source badges + accent
  border on review comments (still editable/deletable); collapsible "🤖 Critic
  — round N (verdict)" panel in the review modal (summary, contradictions,
  missing, revision brief, learning note); task-detail critic section with
  Run-critic button + polling (judge pattern); ✨ toggles: task detail (PATCH),
  task create, wizard ask modal (super_result+fanout → BOTH wizard POST
  bodies), proposal modal (`#wf-super` → workflow POST, client-side sink
  flagging when the plan was made without the flag, per-task
  super_result/deliverable_type in task POSTs, loop-design meta); plan editor
  (B3): rows show ✨SR + type, editor gains `#pe-super` + `#pe-dtype`,
  survives the edit→revalidate round-trip; Agentic approval cards render SR
  checkpoints (✨ round/findings/verdict chips + decision guidance; reject
  prompt → `_retry_task` feedback, unchanged `decideApproval`); WS
  `task_updated` toast on critic verdict transitions, review modal never
  force-refreshed (B9: "reopen the review" wording when a modal is open);
  JARVIS (B2): system-control framing documents the SR flag, critic
  endpoints and the `super_result` approval type (with the ~5–10× cost
  warning), daily briefing counts pending SR checkpoints, spoken event
  callbacks read SR escalations, deck rows show descriptions + ✨ prefix.
  `?v=73→74`. Screenshot sweep over all 14 tabs: zero console errors.
- **Step 10 — gates + docs** (final commit). `verify.sh` section 17 "SUPER
  RESULT" (21 checks); `scripts/verify_super_result_e2e.py` (31 checks,
  self-cleaning, stubbed critic restored in `finally`, probes parked behind a
  backlog dependency so live lanes never claim them); `app/CLAUDE.md` feature
  block + canonical-command entry.

## 2. Deviations from the plan (each = plan vs. reality, with justification)

1. **Step 0 had nothing to commit.** The plan expected dirty B7 edits
   (`server.py`, `secrets_store.py`, `tools_hub.py`); the tree was clean —
   they had already landed as `f072e11` (chore(batch7)) before this session.
2. **`verify.sh` gate line "retry feedback cap raised" updated** from
   `fb[:8000]` to `fb[:16000]`. The plan mandates the 16000 cap (§4.8) but
   didn't mention this pre-existing gate line asserting the old value; without
   the update the suite can never be green.
3. **Wizard framing "never exceed 5 tasks" made conditional (5→7 under
   fan-out).** The plan's fan-out block says "≤7 tasks total" but the same
   prompt's NEVER-list hard-codes "exceed 5 tasks" — left contradictory, the
   model would be told both. Factual omission in the plan; minimal fix.
4. **Belt-and-braces judge-loop skip uses an explicit any()-scan, not
   `_trigger()`.** The plan's snippet `if _trigger(cfg, "super_result")`
   returns None once `used >= max_rounds`, which would resurrect the judge
   loops exactly when SR hits its round cap — contradicting §4.5 ("skips items
   whose config carries a super_result trigger"). Implemented the stated
   intent.
5. **`_sweep_super_result` additionally filters candidates on task-level
   `super_result=1`.** The plan's candidate spec ("own-or-inherited cfg
   pattern") would, for a workflow-level trigger, critique EVERY member task —
   but §5 scopes the critic to deliverable-bearing tasks and §7a flags only
   sink tasks. Without the filter, every investigator/draft of a fan-out
   project would burn a critic run per round. The cascade (`PATCH
   super_result`) still covers all members when the operator explicitly flags
   the whole project.
6. **`setup/install.sh` did not copy `setup/knowledge` at all** (plan: "verify
   install.sh copies setup/knowledge wholesale; add the dir if needed"). Added
   step 5c: full copy when `~/knowledge` is missing, additive
   `rsync --ignore-existing` otherwise (never clobbers a live brain). Also
   added `cverify` to `sync-brain.sh`'s bin allowlist — without it the next
   brain-sync would silently drop the vendored cverify.
7. **N2 era boundary implemented mechanically, not as a prose note**: the eval
   `fingerprint()` now hashes `~/.local/bin/cjudge`, so the judge upgrade
   shifts the config fingerprint and the existing fingerprint-scoped trend
   display already keeps eras separate ("scores comparable within a
   fingerprint only" — the plan's own criterion).
8. **`decide_approval` (Step 5) references `loop_engine.mark_super_done` /
   `bump_super_round` which land in Step 6.** Kept the plan's step order; no
   runtime window exists because only the Step-6 sweep creates
   `super_result` approvals.
9. **superChip "escalated" state** is derived from the trigger state only for
   tasks with their OWN loop config (inherited state lives on the workflow row,
   which task list payloads don't carry); inherited tasks fall back to
   verdict-based chips. Cosmetic only — the Agentic tab shows the checkpoint
   either way.

## 3. Commits

```
c16e18f step 1 — migrations + settings seed
2957dd7 step 2 — Super Result settings section
9a60113 step 3 — cverify grounded-critic script
cd7e0dd step 4 — critic engine in evals.py (+N1 type-aware judge)
64d5ecc step 5 — server wiring (critic thread/comments/endpoints, flag plumbing)
5429452 step 6 — loop engine (super_result trigger + sweep)
cd567dd step 7 — wizard fan-out (planning-time, per goal family)
a036a60 step 8 — INVESTIGATION type rubric + N2 cjudge upgrade
d78c514 step 9 — frontend + JARVIS awareness (B2/B3/B5/B9)
df67c6f  step 10 — gates + docs
```

## 4. Full gate results (real output)

| Gate | Result |
|---|---|
| `bash app/scripts/verify.sh` | **ALL CHECKS PASSED: 277/277** (was 256 before this feature; +21 SUPER RESULT checks) |
| `scripts/verify_super_result_e2e.py` | **ALL CHECKS PASSED: 31 passed, 0 failed** |
| `scripts/verify_block2_e2e.py` | **BLOCK 2 E2E: 48 passed, 0 failed** |
| `scripts/verify_block3_e2e.py` | **ALL PASSED: 33 passed, 0 failed** |
| `scripts/verify_agentic_e2e.py` | **RESULT: 30 passed, 0 failed** |
| `scripts/verify_agentic_playwright.py` | **RUNTIME RESULT: 11 passed, 0 failed** |
| `scripts/verify_block2_ui.py` | **BLOCK 2 UI: 21 passed, 0 failed** |
| `scripts/verify_block3_ui.py` | **ALL PASSED: 15 passed, 0 failed** |
| `scripts/verify_v3_ui.py` | **V3 UI RESULT: 24 passed, 0 failed** |
| `scripts/screenshot_all_tabs.py` (step 9) | all 14 tabs, **no console errors** |

Also verified live during the build (not part of the suite): a REAL
(non-stubbed) cverify run on a throwaway sandbox — the critic executed the
sandboxed code and refuted all three planted claims with quoted command
output (verdict REWRITE, valid sentinel JSON, learning_note present).

## 5. What was NOT done (and why)

- **Step 11 (measurement)** — excluded by the operator; separate session. The
  feature's quality claims are therefore *unmeasured*; only its mechanics are
  verified.
- **N5 (auto-judge scope), N6 (auto-draft replans), N7 (judge-before-blind-
  retry), N8 (recurring-findings distillation)** — Tier 2/3 follow-ups,
  excluded by the operator.
- **B4 (scheduler template passthrough)** — excluded by the operator; cron
  jobs cannot yet set `super_result`/`deliverable_type` on their task
  template.
- **B7's optional `critic_runs` counter** — only the plan's stated minimum was
  done (every critic run lands in the activity feed; CLAUDE.md documents that
  the Usage tab under-reports SR cost because critic runs bill the Claude CLI
  subscription, not GLM tokens).
- **No real end-to-end SR workflow run** (wizard → fan-out → GLM executors →
  real critic rounds): all loop mechanics were verified with a stubbed critic
  + the real sweep; the real-critic path was verified only standalone
  (Step 3). A full live run is Step 11 territory (costs several × 10⁶ GLM
  tokens + multiple frontier critic runs).
- **`docs/` spec file**: the plan itself (repo root) is the spec; no separate
  SPEC-SUPER-RESULT.md was created (the plan doesn't ask for one).

---

## Fixes 2026-07-10 — the 9-finding quality batch

Phase 1 of the quality program (`QUALITY-PROGRAM-MASTER-PLAN-2026-07-10.md` §4).
All 9 findings were re-confirmed present at HEAD before patching. Each fix adds a
regression check to `app/scripts/verify_super_result_e2e.py` (now **46 checks**,
was 31). Gates re-run green after the batch: `verify.sh` 300/300 · SR e2e 46/46 ·
block2 48/48 · block3 33/33.

**BLOCKERS**

1. **Critic reviewed the wrong branch for repo tasks — CONFIRMED, FIXED.**
   `evals.build_critic_sandbox`: `git clone --local` brings the task branch in
   only as `refs/remotes/origin/nexus/<slug>` (the branch is born in a linked
   worktree; the source HEAD stays on base), so `git rev-parse --verify
   nexus/<slug>` missed it and `git remote remove origin` then discarded the only
   refs — the critic silently reviewed BASE. Now: verify
   `refs/remotes/origin/<branch>`, `git checkout -B <branch> origin/<branch>` to
   materialize a local branch, and record `repo_branch`/`repo_note` correctly —
   all BEFORE removing the remote. Covered by an UNSTUBBED sandbox test against a
   scratch repo whose task branch exists only as `origin/nexus/sandbox01`
   (asserts the sandbox tree contains the branch-only file + `repo_branch`).

2. **`_critic_thread` stranded `critic_verdict='running'` — CONFIRMED, FIXED.**
   `judge_model_for` ran before any try; the parse block caught only
   `ValueError`; the comment insert + final UPDATE were unguarded. Now the whole
   thread body is wrapped in a catch-all that stores `'error'` (guarded `WHERE
   critic_verdict IS NULL OR ='running'` so a post-store failure keeps the real
   verdict), and the verdict UPDATE is persisted BEFORE `_insert_critic_comments`.
   Covered by: content-error → terminal `'error'` (never stranded) + a
   source-level guard for the catch-all and the verdict-before-insert ordering.

**CRITICAL (premortem P1)**

3. **No frontier backpressure — CONFIRMED, FIXED.** The only headless-Claude
   spawn sites (`run_judge_cmd`, `run_critic_cmd`) ran unbounded against one
   subscription. Added `evals._FrontierGate` — a global concurrency cap (new
   registered setting `frontier.max_concurrent`, default 2; re-reads the limit
   each acquisition) wrapping both `sp.run` sites — plus quota-vs-content
   classification (`is_frontier_quota_error`, consulted only when no usable
   output) and an exponential frontier backoff (`frontier.quota_backoff_until` /
   `.quota_consecutive`, mirroring `dispatch.*`). On quota: `_critic_thread`
   clears the verdict (re-critiquable, **never** `'error'`, **never** escalates)
   and arms the backoff; `_judge_thread` stores `'interrupted'` (re-judgeable)
   not `'error'`; the loop sweeps skip critic/auto-judge dispatch while the
   backoff is active. Covered by: 3 parallel critic POSTs observe peak
   concurrency == 2; an in-process `_FrontierGate` never exceeds its limit; a
   simulated 429 leaves the task queued (not `'error'`), arms the backoff, and
   raises no escalation.

**CORRECTNESS**

4. **Truncation dropped the appended reconciler — CONFIRMED, FIXED.**
   `_repair_workflow` returned `tasks[:7]` AFTER the reconciler/gate appends; a
   fan-out with `max_raw=7` put the appended reconciler at index 8 → silently
   dropped, so the critic saw an unreconciled fan-out. The raw input is already
   capped at `max_raw` at the top of the function, so the second hard cap is
   removed entirely (`return tasks, repairs`) — mandatory quality gates are never
   truncated. Covered by: 7 raw fan-out tasks → the appended reconciler survives
   as the unique sink depending on all 7.

5. **Tasks attached to a super_result workflow inherited no flag — CONFIRMED,
   FIXED (both doors).** `create_task` inserted only `body.super_result`;
   `update_task` cascaded only when the flag was explicitly set. Since the
   inherited-loop sweep requires `tasks.super_result=1`, a member created/attached
   without the flag never looped. New `_inherit_super_result` helper: when
   `workflow_id` points at a `super_result=1` workflow and the body doesn't set
   the flag, the task inherits it (and `_sync_super_result_loop` ensures the
   project loop carries the trigger). Wired into BOTH `create_task` and
   `update_task`'s `workflow_id` path. Written fresh — there is NO high_stakes
   inheritance pattern to mirror. Covered by: create-into-SR-workflow and
   PATCH-workflow_id-into-SR-workflow both inherit the flag.
   *Follow-up observation (NOT changed in this batch):* **high_stakes has the
   symmetric gap** — a task created into / attached to a `high_stakes=1` workflow
   does not inherit `high_stakes`; only the workflow-PATCH→members cascade
   (`server.py`, `UPDATE tasks SET high_stakes=? WHERE workflow_id=?`) sets it.
   Worth fixing the same way in a later batch.

6. **Empty-findings REVISE retried instead of escalating — CONFIRMED, FIXED.**
   `loop_engine._sweep_super_result`: the `keys and set(keys) <= set(prev)`
   convergence guard let an empty-`keys` (no findings) REVISE fall through to a
   retry on an empty brief. Added an explicit branch: empty findings + a
   non-SHIP verdict is a contradiction → escalate to a human checkpoint. Covered
   by: an empty-findings REVISE escalates (reason contains "no findings"), no
   auto-retry.

**POLISH**

7. **No WS broadcast on verdict transitions — CONFIRMED, FIXED.** Added
   `server.broadcast_threadsafe` (schedules `mgr.broadcast` onto the event loop
   captured at startup) + `server._broadcast_task_row`, and
   `loop_engine._broadcast_task`. `_critic_thread` broadcasts `task_updated` on
   every stored-verdict transition (quota/error/normal/crash); the sweep
   broadcasts on SHIP; `_escalate_super` broadcasts on every escalation. Covered
   by a source-level wiring check (WS delivery itself is exercised by the JARVIS
   UI gate).

8. **Critic endpoint 409 was check-then-act — CONFIRMED, FIXED.** `run_critic`
   now flips to `'running'` with a CAS `UPDATE ... WHERE id=? AND (critic_verdict
   IS NULL OR critic_verdict!='running')` and 409s on `rowcount==0`, mirroring
   `claim_task`. Covered by: two concurrent POSTs → exactly one 200, one 409.

9. **False "Speed mode" reasoning line — CONFIRMED, FIXED.**
   `loop_engine.design_loop`: when `super_result` suppressed auto-judge, the
   `elif judge_ok and high_stakes` branch wrongly claimed "Speed mode" even
   though the user chose quality. Added a super_result-specific branch that says
   the grounded critic replaces the document-only judge. (Text-only; verified by
   the existing `super_result flag designed its loop trigger` check exercising
   the same `design_loop` path.)
