# BUGFIX CAMPAIGN — 2026-07-12 — 29 verified review findings, 2 sessions

Source of truth for the fix sessions. Derived from the xhigh code-review workflow of
2026-07-12 (29 CONFIRMED findings, 0 refuted, across `git diff @{upstream}...HEAD` —
the whole unpushed branch, 164 files). Full per-finding evidence (verifier verdicts
with exact code quotes) lives in the workflow journal:
`~/.claude/projects/-home-sinep-Nexus-Agentic-Coding-Setup/c11573a8-f690-4f9b-b300-d19c11d43a28/subagents/workflows/wf_dfd1dc25-b0c/journal.jsonl`
(each `{"type":"result",...}` line is one agent's return; `candidates` arrays carry the
findings, `verdicts` arrays the confirmations). The campaign plan (identical content +
context) is also at `~/.claude/plans/we-have-to-make-eventual-sketch.md`.

**Rules for the executing session**
- Clusters IN ORDER. Per cluster: re-verify each finding against HEAD (line anchors may
  have drifted) → implement the pre-made design (§Decisions) → run the named gate →
  ONE commit per cluster (`fix(<area>): … [n,n]` naming finding indices) → tick the
  checklist below and note the commit sha.
- Never mix clusters in a commit or leave mixed uncommitted work. On a usage-limit or
  repeated API failure mid-cluster: `git stash push -m "wip-<cluster>"`, note it here,
  stop cleanly. Resume re-does that cluster from scratch (never half-trust a stash).
- **A HARD quota cutoff cannot run the stash step** (no tool calls left) — so EVERY
  session (fresh or `claude --continue`) starts with resume hygiene: `git status` +
  `git stash list`; if uncommitted changes or a `wip-*` stash exist, `git checkout -- .`
  (and/or review-then-drop the stash), find the first unticked cluster in the checklist,
  and re-do it from scratch. This makes resume deterministic whether or not the protocol ran.
- **User note for a quota pause:** don't restart nexus or reboot while a cluster is
  half-applied — `app/` is the LIVE tree; the running process is unaffected until restart,
  but a restart would load partial edits. Resume the session first (it commits or reverts),
  or run `git -C ~/Nexus-Agentic-Coding-Setup checkout -- app/` yourself before restarting.
- Do NOT redesign what §Decisions fixes unless the code contradicts it — then STOP and ask.
- server.py changes: verify per the app:verify skill (restart service, drive HTTP, loop probe).

---

## Session 1 — correctness (17 findings, 8 clusters)

| ✓ | Cluster | Findings | Files | Gate | Commit |
|---|---------|----------|-------|------|--------|
| ☑ | C1 dispatch stream/resume | [29][24] | hermes_dispatch.py (+settings_registry help) | verify_real_dispatch_e2e 57/57 | 9667367 |
| ☑ | C2 escalation state machine | [22/32][30][31] | server.py, loop_engine.py, app.js | verify_super_result_e2e 89/89 | 33b5a0d |
| ☑ | C3 judge quota-deferral | [21] | server.py (deferral + boot heal) | super_result 89/89 + verify.sh 437/437 | 7c24b0e |
| ☑ | C4 restart-drain gaps | [0][1][2] | server.py (_restart_prep_*), worker.py | NEW verify_restart_prep_e2e 26/26 | 4bbac84 |
| ☑ | C5 lessons/distillation | [20][5][13] | lessons.py | verify_autopilot_e2e 58/58 (incl. sweep dry-run) | 8cc32a1 |
| ☑ | C6 scheduler/autopilot | [7/33][11] | scheduler.py, server.py, autopilot.py | verify_autopilot_e2e 62/62 | 85c3b9a |
| ☑ | C7 STT/dictation | [26][27][25] | voice.py, stt_worker.py, server.py | verify_stt_e2e 24/24 | 9de844c |
| ☑ | C8 approvals scope | [23] | server.py decide_approval | verify_agentic_e2e 32/32 + curl pair (200/404) | e966418 |

**Session-1 exit (human checkpoint):** full sweep (verify.sh + real_dispatch + super_result +
autopilot + stt gates + loop_probe) → `/code-review` at MEDIUM effort scoped to
`git diff <pre-session-sha>..HEAD` (record the pre-session sha at step 0) → per-finding
fixed/skipped table → **user runs the real reboot test** (`~/Desktop/RESTART-TEST.md`),
which now validates the FIXED drain.

> **Session-1 RESULT (2026-07-12):** pre-session sha `0d113ca`; all 8 clusters committed
> (`9667367`, `33b5a0d`, `7c24b0e`, `4bbac84`, `8cc32a1`, `85c3b9a`, `9de844c`, `e966418`);
> all 17 findings FIXED, none skipped. Exit sweep green: verify.sh 441/441, real_dispatch
> 57/57, super_result 89/89, autopilot 62/62, stt 24/24, loop_probe LOOP-FREE. The medium
> code review confirmed 7 findings on the session's own diff; 5 small ones were fixed in a
> follow-up commit (drain-mode _find_work shadowing, regen dropping esc state, critic GET
> running flag missing 'escalating', drain dead-orphan transcript hammering, retry-path CUDA
> classification, + the [21] verify.sh pin tightened). **CARRY-OVER → Session 2 / decision:
> loop_config lost-update race** — _escalation_thread's bump/state-clear (and the pre-existing
> failure-branch + sweep writers) do unlocked read-modify-writes of the same loop_config JSON;
> a stale sweep save can erase the esc_used bump → escalations past super.escalation_max
> (CONFIRMED by review; race class pre-dates this campaign, consequence widened by D2's bump
> move). Promoted to S2 item [R1] with pre-made design §D6 (user decision 2026-07-12).
> **Reboot test is now ready for the user.**

## Session 2 — cleanups + installer/doc drift (13 findings, 2-3 grouped commits)

| ✓ | Findings | What |
|---|----------|------|
| ☐ | [3] | nexus-up hardcoded container names → compose-file fallback when a named container is absent |
| ☐ | [4] | root install.sh: explicitly `systemctl --user disable nexus` on upgrade installs (posture claim must be true) |
| ☐ | [8/28] | stale "5/6 core-mods" counts in setup/CLAUDE.md + setup/install.sh → "the count in guardian/core-mods.json (7 today)" |
| ☐ | [6] | harvest_decisions appends per retry round, no supersede → dedup by task id (replace that task's block) |
| ☐ | [9] | judge_model_for/spec_model_for/escalation_model_for triplication → one `_cli_model_for(purpose)` |
| ☐ | [10] | _regen_loop_for_profile vs _sync_super_result_loop meta-dict drift → shared builder |
| ☐ | [12] | _judge_thread inline SPEC path → reuse `_workflow_spec_md` |
| ☐ | [14] | startup's synchronous sweep_stale_plan_sessions (serial 10s HTTP DELETEs) → background/deferred |
| ☐ | [15] | hardcoded 'u_owner' in routing.py:192 + lessons.py:183 → auth.DEFAULT_USER_ID |
| ☐ | [16] | loop-invariant judge.auto_scope read inside per-candidate loop → hoist |
| ☐ | [17] | double _turn_cut_count query in the cut-turn budget block |
| ☐ | [18] | _lessons_safe getattr-by-string → direct callables |
| ☐ | [19] | eval judge spend stuffed into frontier_ledger.workflow_id → proper source column (small migration) |
| ☐ | [R1] | loop_config lost-update race (session-1 exit review, CONFIRMED) → implement §D6; also collapses the 3 duplicated locate/unpack/save blocks in _escalation_thread |
| ☐ | [R2] | watchdog restart circuit-breaker counts CLEAN service restarts: every `systemctl restart nexus` kills lanes → watchdog respawn +1 each, cumulative forever — the 2026-07-12 campaign's ~8 restarts retired the whole fleet (Worker 1-5 + Manual) at 01:21 (healed by hand: counters reset + POST /agents/{id}/restart). Fix: don't increment when the death is within ~120s of service boot (startup ts marker), OR decay restart_count to 0 after 1h of healthy uptime. Gate: seeded restart_count + fake boot marker → no increment on the post-boot respawn |

**Session-2 exit:** verify.sh + verify_autopilot_e2e + verify_deep_plan_e2e + screenshot
sweep → final `/code-review` on the combined campaign diff → update program memory files.

---

## §Decisions — pre-made designs (implement as specified)

### D1 — stall/quiet inversion [29]
Derive the effective quiet window INSIDE `orphan_run_state()` (hermes_dispatch.py:1313 —
the single choke point shared by `worker._wait_on_active_orphan`, the resume path, and
`reconcile_stalled_dispatches.keep_session`):
`quiet_eff = max(dispatch.resume_quiet_s, effective_stall + RESUME_QUIET_MARGIN_S)`,
new constant `RESUME_QUIET_MARGIN_S = 300` next to `RESUME_QUIET_DEFAULT_S` (~1293);
effective stall from the same setting/fallback as the stall guard (`DEFAULT_TURN_STALL_SECONDS`,
line 53). Invariant: a run surviving a stall-cut is by definition already silent > stall when
the lane re-enters (~stall+90s), so any quiet ≤ stall guarantees a false 'dead' verdict and a
continue-turn into a live run. `max()` ⇒ raising stall auto-raises quiet; lowering quiet below
the floor is a no-op. Update `dispatch.resume_quiet_s` help in settings_registry.py (~63):
"effective minimum is the stall cutoff + 300s". Margin covers cut→re-entry lag (90s
STALE_DISPATCH_S) + 120s read timeout + flush lag.
Edge cases: crash-resume with chatty run unaffected (fresh transcript → 'active'); empty
transcript still 'dead' immediately; runaway ceiling (2× max_turn_seconds) unchanged.
Verify (add to verify_real_dispatch_e2e): transcript aged stall−60 → 'active'; stall+400 →
'dead'; `resume_quiet_s=30` + stall 900 + age 950 → still 'active' (floor holds).

### D2 — quota-deferred escalation retry [30]
Three coordinated edits:
1. Move the budget bump OUT of `loop_engine._try_escalate_super` (line ~557) INTO
   `server._escalation_thread` after `run_escalation_cmd` returns non-deferred (next to
   `note_frontier_quota_ok`, ~4574) via `_locate_super_cfg` + `_bump_escalations` + `_save_cfg`;
   tolerate `loc is None` (manual /escalate without loop config — mirror the existing
   4608-4616 block). Budget is spent exactly once, only when a frontier run actually executed.
2. Deferral branch (~4565-4573): RESTORE `critic_verdict` from `critic_json`'s stored
   `"verdict"` (reliably present — written at ~4470 as `json.dumps(parsed)`) and KEEP
   `critic_ts` when restored (≥ completed_at ⇒ the sweep does NOT re-critique the unchanged
   deliverable); NULL both only when there was never a critique. Also clear the trigger
   state to None via `_locate_super_cfg` (mirrors the failure branch).
3. `_try_escalate_super` becomes tri-state `"sent"|"wait"|"no"`: `"wait"` when eligible but
   `frontier.quota_backoff_until` is armed (move the backoff check AFTER eligibility);
   both sweep call sites (~724, ~740) treat `"wait"` as continue-pending — NOT fall-through
   to GLM retry or checkpoint.
Edge cases: repeated deferrals → no bump until a real run, backoff grows; process kill mid-
thread leaves 'escalating' → healed at boot to 'error' (D3b) → human checkpoint, no budget
leak; non-quota failure still bumps (a real attempt was consumed) → 'error' path unchanged.
Verify (verify_super_result_e2e new scenario): 429-stub `super.escalation_cmd` → POST
/escalate → deferral restores the pre-escalation verdict (not NULL), esc_used unspent,
backoff armed, no new critic round; clear backoff + working stub → live sweep re-escalates,
esc_used lands at exactly 1 with a rewritten deliverable.

### D3 — restart-drain semantics [0][1][2]
(a) Worker executes `mode=="resume"` even when dispatch is off, restricted to the
no-new-token halves: worker.py:232 → `if task and (dispatch_on or mode == "resume")`;
pass `dispatch_on` into `_execute`; in the resume branch, when `not dispatch_on`, after
`_wait_on_active_orphan` returns False only proceed to supersede + `run_task_dispatch(resume=True)`
if `hd.orphan_run_state(task) == "finished"` (pure harvest), else return untouched.
Effect: active orphans get heartbeats refreshed every ~90s tick (inside the 120s
SLOT_HEARTBEAT_FRESH_S window) ⇒ `slots_in_use()` counts them again — the drain count fix
comes free AND provably reaches zero (harvest finalizes; dead orphans age out). Do NOT add
an unconditional `IN ('dispatching','streaming')` count (nothing transitions those rows
during drain ⇒ "safe" would never come). Queued/retry/claimed modes stay gated.
Known-accepted edge: an unharvestable failure-text final reply sets resume_with_context and
sends one bounded turn — acceptable, note in a comment. Watchdog keeps respawning lanes
during drain (required; it doesn't consult dispatch.enabled).
(b) `_restart_prep_busy` counts `critic_verdict IN ('running','escalating')` (~5133); extend
the startup heal (~119-125) to flip `'escalating'` → `'error'` + append
`' [escalation orphaned by restart]'` to critic_output — the sweep's error branch routes to
the human checkpoint (consistent with the critic heal; also unsticks the pre-existing
forever-skip: sweep skips 'escalating', /critic + /escalate 409 on it).
(c) Module-level `threading.Lock` (`_RESTART_PREP_LOCK`, next to `_RESTART_PREP_KEY`)
wrapping the bodies of `_prep` AND `_cancel` (single process; also serializes prepare-vs-cancel).
Verify: with dispatch off, a stale streaming dispatch whose upstream reply is finished
harvests to completed while a queued task does NOT execute; seeded 'escalating' →
GET /api/system/restart-prep shows busy.critics ≥ 1; two concurrent prepares keep the
original prev_dispatch_enabled; verify.sh static grep pins the healed state list.
Commit the recreated gate as `scripts/verify_restart_prep_e2e.py` (prepare/double/cancel/
grace/403/restore-across-restart — from the 2026-07-11 scratch test, which dies on reboot).

### D4 — STT timeout + retry [26][27]
Keepalive + inactivity kill; NO duration plumbing. `stt_worker.op_transcribe` consumes the
faster-whisper segment generator in a loop and emits `{"keepalive": true}` lines (one ack
immediately on request receipt — before the model load — then per decoded segment, throttled
≥2s apart); `voice._ask_stt_sync` becomes a read-loop re-arming the kill timer on every
received line (new `STT_INACTIVITY_KILL_S = 180`, which absorbs the 45s gpu_lock wait +
eviction + cold load because the ack lands first) and skipping keepalives before any parsing
side effects (`fallback`/_stt_loaded bookkeeping only on the final response); the existing
`timeout` param becomes an ABSOLUTE ceiling — `_transcribe_path` passes 1800, warm keeps 120,
ping default 90. `transcribe_pcm`/`_transcribe_bytes_sync` signatures untouched. Same tree
spawns both sides — no protocol skew. EOF handling unchanged (empty line → kill + raise).
[27]: restore the old one-shot GENERIC retry (any failure → drop model → retry once), not
just CUDA-classified.
Verify (verify_stt_e2e + 2 new checks via worker knob `NEXUS_STT_TEST_STALL_S`, sleeping in
5s slices with a keepalive per slice, `NEXUS_STT_TEST_STALL_SILENT=1` suppressing them):
(i) stall 20s + keepalives + inactivity 8s → transcription succeeds; (ii) stall 20s silent →
worker killed + RuntimeError. Both < 1 min.

### D5 — autopilot placement [7/33][11]
Move the derivation into autopilot.py as public
`preset_fields(autopilot, spend_profile, high_stakes, explicit_budget)`;
`server._autopilot_fields` (line ~372) becomes a one-line delegate (NAME KEPT — the
verify.sh static gate at scripts/verify.sh:402 and the create_task call site ~677 stay
untouched); scheduler.py top-imports `autopilot` (kills the server-import cycle);
`_trigger` (~111-126) derives `(inv, sp, budget)` from the template and adds
`budget_tokens` to the INSERT (bonus: axes normalized — raw junk strings no longer land in
the column). Edge cases: autopilot-without-spend → budget stays NULL (rule 4 keys on the
spend axis, matches create_task); neither axis → (None,None,None) legacy; pass template
`high_stakes` as bool (rule-2 eco floor).
[11] separate small fix, same commit: after the workflow-PATCH member UPDATEs (~7249), loop
`SELECT * FROM tasks WHERE workflow_id=? AND loop_config IS NOT NULL` and call
`_regen_loop_for_profile("task", member)` for each (helper stays in server.py). Do NOT
re-derive member budgets on PATCH — rule 4 is creation-only (matches the task-PATCH path).
Verify (verify_autopilot_e2e): eco-template job → `scheduler._trigger(job_row)` directly →
task has `budget_tokens == 2_500_000` (0.5 × 5M default) + normalized axes (cleanup after);
cascade check: a member with its own enabled loop_config gets re-derived on workflow PATCH
(round cap follows the profile) with `used` counters preserved.

### D6 — loop_config lost-update race [R1] (session-1 carry-over)
All loop_config writers live in ONE process (server request threads, escalation
daemon threads, the loop-engine sweep thread), so a module lock suffices:
1. `loop_engine._CFG_LOCK = threading.RLock()` (module level, next to _save_cfg).
2. New `loop_engine._mutate_super_cfg(task_id, fn) -> bool`: under _CFG_LOCK,
   FRESH `_locate_super_cfg(task_id)` → `fn(trig, per_task)` → `_save_cfg`;
   returns False when loc is None (manual /escalate without loop config — keep
   the existing tolerance). Replace the THREE server.py blocks with one-line
   calls: deferral state-clear (`fn=lambda trig, pt: _set_super_state(trig, pt, None)`),
   budget bump (`fn=lambda trig, pt: _bump_escalations(trig, pt)`), failure
   re-arm (same as deferral). Kills the triple locate/unpack/save duplication.
3. The sweep keeps DECIDING on its query-time snapshots (never hold the lock
   across `_api` HTTP calls), but every mutate+persist goes through the same
   fresh-read path: wrap `_bump_rounds/_set_super_state/_bump_escalations +
   _save_cfg` pairs in `_sweep_task_loops`/`_sweep_super_result` (and the
   approve/reject helpers ~795-813) in `_CFG_LOCK` with a RE-LOCATED cfg —
   e.g. route them through `_mutate_super_cfg` too (the trig identity check is
   by trigger id, so a fresh read is safe even if another writer landed).
   Decision staleness (acting on a snapshot) is acceptable — the idempotence
   guards (`handled_ts == critic_ts`, verdict CAS on the endpoints) already
   bound double-acting; only the WRITE must never be lost.
4. Edge: `_regen_loop_for_profile` (server.py) also rewrites whole cfgs — take
   `_le._CFG_LOCK` around its read→design→save too (import loop_engine there).
Verify (verify_super_result_e2e new in-process check): one workflow cfg with
two member esc entries; two threads × 50 iterations each calling
`_mutate_super_cfg` bumping THEIR member's esc_tasks; assert both counters
land at exactly 50 (no lost updates). Plus a static verify.sh grep pinning
`_CFG_LOCK` + `def _mutate_super_cfg`.

---

## Quota resilience (Max 20 plan)
Session 1 ≈ one solid feature session; gates cost ~0 tokens. The limit is a 5h ROLLING
window — a cutoff is a pause, not a loss: the cutoff protocol above + per-cluster commits +
this checklist make any resume (`claude --continue` or a fresh session) lossless.

## Session prompts

**Session 1:** Read `BUGFIX-CAMPAIGN-2026-07-12.md` in the repo root. FIRST: resume hygiene
(`git status` + `git stash list`; revert any uncommitted/wip-* leftovers; find the first
unticked cluster). Record the pre-session sha. Execute Session 1 exactly as specified:
clusters C1→C8 in order; per cluster re-verify
each finding against HEAD, implement the pre-made design (§Decisions), run the named gate,
commit with a `fix(<area>):` message naming the finding indices, tick the checklist with the
sha. ONE commit per cluster. On usage-limit mid-cluster: stash as `wip-<cluster>`, note it
here, stop. Do not redesign §Decisions unless the code contradicts it — then STOP and ask.
Finish with the batch checkpoint (full gate sweep + /code-review at medium effort scoped to
`git diff <pre-session-sha>..HEAD`) and a per-finding fixed/skipped table.

**Session 2:** Read `BUGFIX-CAMPAIGN-2026-07-12.md`. FIRST: the same resume hygiene as
Session 1. Confirm Session 1 complete via git log.
Execute the S2 table in 2-3 grouped commits, same re-verify→fix→gate→commit rhythm, then the
S2 exit sweep and a final /code-review on the combined campaign diff. Report per-finding
outcomes and update the program memory files.
