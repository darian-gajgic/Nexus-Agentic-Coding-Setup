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
