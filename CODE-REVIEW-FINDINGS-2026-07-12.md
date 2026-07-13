# Code review — improvement batch 2026-07-12 (complete findings)

**Scope:** `git diff 5df5d26^..87326f9` — the 7 commits of the 17-item improvement batch
(known-issues scoping · task stop + bulk + delete cascades + branch-artifact deliverables +
attachment targeting · agent-memory writers + per-user wins/lessons + eval-improve loop +
model routing · notes/sort-filter/meetings/per-user GitHub · efficiency pass +
`session-run-stop` core-mod · mode-coherence · session-effort bridge). 30 changed files.

**Method:** multi-agent review at xhigh effort — 6 independent finder angles → 51 candidates →
41 adversarial verifier agents, each asked to *refute* its assigned finding →
**48 CONFIRMED · 2 PLAUSIBLE · 1 REFUTED**. This document lists **all of them**, deduplicated to
37 distinct defects and ranked by severity. (The workflow's own summary reported only the top 15;
the rest are recovered here from the run journal.)

**Independently spot-checked by hand** (read from the code, not taken on the reviewers' word):
- `esc()` (app.js:30) escapes only `& < > "` — **never `'`** → the XSS finding is real.
- `dispatch.stub_stream` appears **0 times** in `settings_registry.py` → undeclared, invisible in
  the Settings UI, no guard.
- All four project-delete `LIKE` arms (server.py:10302, 10306, 10342, 10346) interpolate the raw
  filesystem path with **no `ESCAPE`** clause → `_` is a live SQL wildcard.

✅ **Live state verified clean at the time of writing** (`nexus.db`): `dispatch.stub_stream` is
**unset**, users are exactly `owner` (admin) + `ariana` (member) — no leaked probe account — and
there are no leftover probe tasks or probe model rows. None of these leaks has *happened* yet.

---

# P0 — fix before the next real dispatch

### 1. Project delete can permanently destroy a *sibling* project's tasks, deliverables and cron jobs
`app/server.py:10341` (also 10302, 10306, 10346) · **destructive data loss** · CONFIRMED

The delete cascade builds SQL `LIKE` patterns straight from the filesystem path without escaping
`_` / `%`. In SQL `LIKE`, `_` matches **any single character**. The sibling endpoint
`project_history` (server.py:10426) already does this correctly with `ESCAPE '\'` — the new code
does not.

**Failure:** admin deletes `~/work/my_app` with "delete tasks" ticked. The pattern
`'/home/u/work/my_app/%'` **also matches `~/work/my-app/`**. The unrelated project's workflows,
tasks and scheduled jobs are cascade-deleted and their workspaces `shutil.rmtree`'d — permanent,
no trash copy, no warning. The `scheduled_jobs` arm is worse still: it is a bare `LIKE '%<path>%'`
substring match, so a project whose path is a *prefix* of a sibling's also drags the sibling's jobs.

**Fix:** escape the wildcards and add `ESCAPE '\'` to all four arms:
```python
esc_path = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
db.query_all("SELECT * FROM workflows WHERE project_path=? OR project_path LIKE ? ESCAPE '\\'",
             (path, esc_path + os.sep + "%"))
```

---

### 2. A crashed e2e gate can silently turn **every production dispatch into a fake stub**
`app/hermes_dispatch.py:1848` · **silent corruption of all output** · CONFIRMED

The new `dispatch.stub_stream` branch replaces the real model turn with a 120 s keepalive loop
returning `content = "stubbed deliverable (dispatch.stub_stream)"`, `error=None`. It is restored
only by `verify_stop_e2e.py`'s in-process `finally` (line 240). A SIGKILL / OOM / timeout leaks the
setting **permanently**. This is the third instance of this leak class in this repo (the judge-stub
leak and the e2e scheduler-job leak both burned us before).

**Failure:** the gate dies hard → every task afterwards "completes successfully" with a garbage
deliverable, downstream workflow stages consume the stub as input, and nothing alerts because the
dispatches finish cleanly. No env guard, no expiry, not in the settings registry → invisible.

**Fix (defence in depth):** gate on a process-env marker the gate sets
(`os.environ.get("NEXUS_GATE") == "1"` **and** the DB row); refuse to stub while `dispatch.enabled`
is on and a non-probe task is in flight; declare it in `settings_registry.py`; log a loud WARN per
stubbed dispatch; clear it in the boot reconcile (same pattern as the orphaned-`drafting` reset).

---

# P1 — data isolation, data loss, broken core flows

### 4. Cross-user memory leak in the hourly agent-memory consolidation
`app/agent_memory.py:80` · **breaks the Block-1 per-user isolation contract** · CONFIRMED

`consolidate_agent`'s throwaway session never calls `hd.publish_session_scope(sid, user=…)` — every
sibling throwaway session (feedback-draft, meeting-analysis, evals, wizards) does, precisely to
avoid the scopes-file default.

**Failure:** the hourly sweep streams a lane's whole task log — titles, failure causes, learned
notes belonging to **every user whose tasks ran on that lane** — through an unscoped session. mem0
extracts memories from that turn under the default-user fallback, making one user's task details
recallable in another's JARVIS/chat.

**Fix:** publish an explicit scope before the turn (the lane is shared → a system scope, not
"whoever ran last"), and/or suppress mem0 extraction for this session — it is a meta-summary, not
knowledge worth memorising.

---

### 5. Deleting a task now destroys its deliverables irreversibly, behind the old one-click confirm
`app/server.py:899` (confirm text at `app.js:4494`) · **irreversible data loss** · CONFIRMED

For the product's entire prior life, deleting a task removed the *row* and left the workspace on
disk (recoverable). The batch changed it to an unconditional `rmtree`. Project delete got a
typed-name confirm **and** `~/.nexus-trash`; workflow cascade got a typed-name confirm; single-task
delete kept its generic *"Delete this task permanently?"*.

**Failure:** an operator tidies the board and a client `.pptx` that exists nowhere else (non-repo
task) is gone forever.

**Fix:** route the workspace through `~/.nexus-trash` like project delete does, and reword the
confirm to name what is being destroyed.

---

### 6. A stale stop flag silently kills the next retry / auto-rework round
`app/server.py:5850` · **breaks the closed loop** · CONFIRMED (found independently by 4 of 6 finders)

`_retry_task` re-queues the task but never clears `tasks.cancel_requested`. Every other restart door
does (`update_task` → todo, `/dispatch`, bulk-start).

**Failure:** ⏹ pressed while a dispatch is `finalizing` (or the run finishes before the ~30 s cancel
poll fires) → the flag is set but never consumed. Later the judge returns REVISE (auto-rework) or
the operator clicks ↻ Retry → `run_task_dispatch`'s entry check sees the flag and immediately
`_finalize_cancel`s. In Full Auto the rework loop dies silently, the task parks in Backlog, and the
log says *"stopped by operator"* — which nobody did.

**Fix:** add `cancel_requested=NULL` to `_retry_task`'s UPDATE, and clear the flag in
`_finalize_result` on any terminal state.

---

### 7. Stopping a task in its first seconds leaves the upstream run burning tokens
`app/server.py:4196` · **the exact failure item 5 was built to eliminate** · CONFIRMED

`_request_stop` forwards `/v1/runs/{run_id}/stop` **only if** `dispatches.run_id` was already
captured — but the run_id only arrives with the `run.started` SSE event. The executor's
`DispatchCancelled` path never retries the abort with the run_id that lands moments later.

**Failure:** ⏹ during `dispatching` (or the first seconds of streaming) → no upstream stop is ever
sent. Nexus parks the task and drops the session while the orphaned Hermes run executes to the end
of its turn, spending tokens the operator explicitly told it not to spend.

**Fix:** re-attempt the upstream stop from `_finalize_cancel` (the run_id is in the dispatches row
by then), or have the executor call `/v1/runs/{id}/stop` itself when it raises `DispatchCancelled`.

---

### 8. Core-mod race: the stop endpoint 404s while the agent is still being created
`setup/guardian/patches/session-run-stop.patch:16` · **same symptom as #7, gateway side** · CONFIRMED

The mod registers a `[None]` placeholder in `_active_run_agents` before the executor thread fills
it; `_handle_stop_run` unwraps it to `None`, and since session-chat runs never register in
`_active_run_tasks`, it returns **404 "run not found"** even though the run exists and is starting.

**Failure:** a stop landing in that window (widened under load — 10 concurrent runs cap, thread-pool
queueing) is swallowed by Nexus's best-effort caller and never retried. The run completes, burning
tokens, while the UI shows the task as stopped.

**Fix:** when the entry is a list whose agent is still `None`, record a "stop requested" marker for
that run_id and have `_run_agent` interrupt immediately after creating the agent (or return
`202 stopping` instead of 404 and re-check).

---

### 9. Light-tier models can be driven at **maximum** reasoning effort
`app/hermes_dispatch.py:716` · **4–10× reasoning-token burn** · CONFIRMED

`session_effort_for_task` returns `xhigh` for any high-stakes **or** Smart task **without checking
the model tier** — only the eco branch is tier-aware. And the session-effort core-mod makes the
published value **short-circuit** the zai plugin's `_LIGHT_MODEL_CAP = "medium"` clamp (the plugin
comment claims "the dispatch is already tier-aware" — it is not).

**Failure:** a user pins `glm-4.5-air` (an explicit model choice always wins) on a high-stakes or
Smart task → effort `max` on a model chosen for cheapness. The plugin's own measurement: 756 vs 190
reasoning tokens on a trivial prompt — paid every turn.

**Fix:** clamp inside `session_effort_for_task` — if the model is light-tier, never exceed `medium`,
regardless of mode or stakes.

---

### 10. The cut-turn budget extension still hands out **global 5M** slices to per-type-capped tasks
`app/hermes_dispatch.py:1770` · **bypasses the mode × type budget matrix** · CONFIRMED

The mode-coherence commit made `_retry_task`'s slice and `check_budgets` per-type
(`_type_setting`), but left the B2 cut-turn resume extension on the global
`dispatch.default_task_budget` — while its own comment claims it grants *"the same one-slice
headroom a judge retry gets"*.

**Failure:** a NULL-budget content task correctly blocks at 2M, but if its turn was cut
(`dispatch.turn_seconds.content = 5400`) the resume extends by **5M per cut**, up to 3 cuts →
**17M tokens** on a task the eco/Balanced/smart matrix caps at 1M/2M/4M.

**Fix:** use `_type_setting("dispatch.default_budget", task, default)` for `slice_` on the
cut-resume path too (one line — mirrors the `_retry_task` fix already shipped).

---

# P2 — confirmed correctness bugs (medium severity)

### 11. The stop gate leaks a live admin account and then can never run again
`app/scripts/verify_stop_e2e.py:71` · CONFIRMED

The gate creates a fixed-username **active admin** (`probe-stop-admin`) cleaned up only by the
in-process `finally`. A hard-killed gate leaves the row behind; the next run dies at
`assert admin_u, err` (username taken) **before** entering `try/finally` — the gate is unrunnable
until someone deletes the row by hand, and an unaccounted admin account sits in the auth table.
`verify_phase_c_e2e.py:69` has the same pattern with a member user.
**Fix:** suffix probe usernames with a random token, and delete any stale `probe-*` users at gate
start (idempotent pre-clean).

### 12. Project delete silently skips tasks whose workflow isn't project-linked
`app/server.py:10286` · CONFIRMED

Tasks are *collected* by `repo_path` (and counted in the "N task(s) deleted" note) but
`_project_delete_blocking` only deletes tasks with **no** `workflow_id` plus members of
project-linked workflows. A task with `repo_path` under the project but belonging to a workflow
whose `project_path` is NULL/different survives — still pointing at a trashed/purged repo, so its
next dispatch fails with "repo worktree setup failed" — while the operator was told it was deleted.
**Fix:** delete every task in the collected `tasks` set, not just the two subsets.

### 13. Renamed deliverables are invisible again (the item-1 gap, reopened)
`app/worktree.py:134` · CONFIRMED (reproduced empirically by the verifier on git 2.53)

`changed_files()` uses `--diff-filter=AM`, which **drops renames** (`R`) — and git's rename
detection is on by default.
**Failure:** a content-in-repo task reworks a deck and `git mv`s it → `_copy_branch_artifacts`
mirrors nothing, `/branch-files` omits it, and downloading returns 404 (membership is the injection
gate). The user-facing deliverable is invisible in Deliverables — exactly the bug the feature was
built to fix — while `changes.diff` shows the rename happened.
**Fix:** add `R` and `C` to the filter (`--diff-filter=AMRC`) and take the *destination* path of
rename records.

### 14. A staged attachment can be uploaded to the wrong task
`app/static/app.js:1759` · CONFIRMED

Per-file attachment targets store a plan-task **index**; `planEdRemove` splices the task array and
remaps only *dependencies*, and the clamp only resets out-of-range targets — an in-range stale index
silently now names a different task.
**Failure:** you target `adcopy-brief.docx` at task 3, then delete task 1 → on Create the brief is
uploaded as the input of an unrelated task; the ad-copy agent never sees it. No error shown.
**Fix:** remap `_target` in `planEdRemove` exactly like `depends_on_idx` (or key targets by a stable
task uid instead of an index).

### 15. The lane's rolling summary permanently loses task outcomes
`app/agent_memory.py:66` · CONFIRMED

The sweep snapshots the read window *before* the up-to-120 s model call but timestamps the new
summary *after* it, and caps the read at `LIMIT 40`. Any experience row written during the call —
or beyond the newest 40 on a busy lane — falls below the next sweep's watermark and is **never**
consolidated into any future summary, including the failure patterns the feature exists to learn.
**Fix:** watermark the summary with `max(created_at)` of the rows actually consumed, not
`time.time()`; page instead of truncating at 40.

### 16. A stale reasoning effort survives on a reused session
`app/hermes_dispatch.py:728` · CONFIRMED

`publish_session_effort` merges into the bridge entry but **never clears** a previously published
`effort` when `session_effort_for_task` returns `None` (= "use the config default").
**Failure:** an Eco task publishes `high`, gets turn-cut and parked with its session intact; the
operator switches it to Balanced/code expecting full reasoning; the resume re-uses the same session,
publishes nothing — and the stale `high` keeps being applied by the plugin.
**Fix:** when the computed effort is `None`, actively remove the `effort` key from the entry.

### 17. Re-picking a meeting's project silently unlinks its workflow
`app/server.py:2705` · CONFIRMED

`meeting_set_meta` unconditionally rewrites **both** `project_path` and `workflow_id`, but the UI's
`meetSetProject` sends only `project_path` → the existing workflow link is nulled by every project
(re)assignment, with no user action to remove it.
**Fix:** only update keys present in the body (the `tasks` PATCH pattern).

### 18. Deleting tasks leaves ghost Decisions cards in the inbox
`app/server.py:894` · CONFIRMED

`_delete_task_row` expires only pending `action_type='deliverable'` approvals — `_retry_task` (line
5859) correctly expires **both** `'deliverable'` and `'super_result'`. A cascade/project delete of a
task with a pending Super Result checkpoint leaves a card referencing the deleted task pending
forever, keeping the nav badge lit.
**Fix:** expire the same action-type set as `_retry_task`.

### 19. Eval improvements report "applied" when nothing was applied
`app/evals.py:1725` · CONFIRMED

`apply_improvements` sets `improve_status='applied'` unconditionally — even when every delta landed
in `skipped` (deliverable file gone, specialist renamed, `before` text no longer matches). The UI
treats `applied` as terminal, so the "✨ Improve from results" button never re-arms for that run.
**Fix:** set `applied` only when `applied` is non-empty; otherwise `error`/`none` with the skip
reasons surfaced.

### 20. The Specialists tab can latch a transient error — or stale data — forever
`app/static/app.js:8688` (and 8685) · CONFIRMED

Two bugs in the new anti-flicker loader: (a) the `catch` sets `data = {error}` but leaves
`lastJSON` intact, so every later *successful* refetch hashes equal (`changed=false`) and never
replaces the error panel — one restart or 502 pins the tab in an error state indefinitely; (b) the
hash cache is updated even when `render()` is skipped because `uiLocked()` — so after the modal
closes, the view never re-renders and keeps showing a stale roster (e.g. an approved lesson still
listed as pending).
**Fix:** reset `lastJSON = ''` in the `catch`; on a `uiLocked()` skip, leave `lastJSON` unchanged
(or defer via `softRender`'s `pendingRender`).

### 21. The agent-memory sweep can stall the cron scheduler for minutes every hour
`app/scheduler.py:198` · CONFIRMED

`consolidate_sweep()` runs **inline on the single scheduler thread**, making one blocking
`stream_turn` (max 120 s) per lane. With ~6 lanes that is up to ~12 minutes per hour during which
the every-15 s trigger loop is blocked and **no due cron job fires**.
**Fix:** run the sweep in a daemon thread (the same batch already does this for
`evals.run_improvement`).

### 22. The near-duplicate advisory can be silently disabled by an unrelated word
`app/server.py:7788` · CONFIRMED

The fan-out exemption uses bare substring membership over `lens`/`draft`/`angle`/… — so
`rectangle` contains `angle` and `overdraft` contains `draft`.
**Failure:** two genuinely duplicated stages with such a word in the title are exempted from the
near-duplicate check, the operator never sees the advisory, and the duplicated stage is created and
dispatched twice — double spend, two conflicting deliverables.
**Fix:** match on tokenized words, not substrings.

### 23. Branch-files shows junk after the worktree is pruned
`app/server.py:4403` · CONFIRMED

`_task_branch_ctx`'s fallback re-implements the name-status parse but **omits** the
`_JUNK_PATHSPECS` exclusion the real `changed_files()` applies — so the same task reports a
*different* file set depending on whether its worktree still exists, and committed build junk
becomes downloadable as a "deliverable".
**Fix:** extend `worktree.py` with a range-based helper sharing the parse loop **and** the junk
pathspecs; call it from both branches.

### 24. "✨ Create workflow" can silently re-run a 1-minute LLM extraction
`app/static/app.js:10260` · CONFIRMED

`meetCreateWorkflow` fetches `GET /api/meetings` into a variable it never uses, then reads the
"cached" requirements via **POST** `/requirements` — which re-runs the extraction whenever the
transcript mtime changed. The button appears hung for ~1 minute and spends tokens the user never
asked for.
**Fix:** delete the dead GET; read requirements from a read-only endpoint (or from the list payload
it already fetches).

### 25. A stopped task keeps showing as "working on…" for up to 48 hours
`app/hermes_dispatch.py:1363` · CONFIRMED

`_finalize_cancel` never removes the lane's `stm`/`inflight` scratchpad row (only `_write_experience`
does, and the cancel path doesn't call it). The Agent-memory tab shows the lane still "working on"
the stopped task until the 48 h TTL expires.
**Fix:** delete the task's stm row in `_finalize_cancel`.

---

# P3 — duplication, drift and efficiency (advisory)

> The 2 **PLAUSIBLE** (rather than CONFIRMED) verdicts of the run fall in this group — treat these
> as cleanup guidance, not proven defects.

| # | Location | Issue |
|---|---|---|
| 26 | `app/routing.py:207` | `_DEV_SPECIALISTS` now exists in **4 places** (server.py:6320, routing.py, app.js `devShaped` at 10474, app.js `DEV_SPECIALISTS` at 10947). Missing the routing.py copy silently lets auto-routing or the REVISE-escalation downgrade a dev stage's pinned model. |
| 27 | `app/plan_engine.py:319` | `recommend_spend` inlines a near-copy of `routing._MECHANICAL_RE` **that has already diverged** — plan_engine has the German verbs (`umbenenn`/`konvertier`), routing does not. A German mechanical goal gets an Eco *recommendation* whose *routing* then disagrees. |
| 28 | `app/hermes_dispatch.py:714` | A **third** divergent "light tier" definition (`air`/`flash`/`turbo` substrings) alongside the plugin's `_is_light_model` (`air`/`flash`) and the registry-based `easy`/`mechanical` lookup. Rotating in a light model whose id lacks those substrings silently doubles its effort. |
| 29 | `app/autopilot.py:76` | `preset_fields` inlines the per-type settings lookup that `hermes_dispatch._type_setting` already implements — two implementations of the same semantics; a change to one makes wizard budgets and dispatch-time checks disagree. |
| 30 | `app/evals.py:1709` | The exemplar branch re-implements `feedback_log.promote_deliverable` and reaches into `lessons` privates (`_knowledge_root`, `_git`). Its `{today}-eval-{cid}.md` name also **silently overwrites** a same-day re-promotion of the same case. |
| 31 | `app/server.py:2715` | `meeting_summarize` / `meeting_requirements` are ~40-line near-identical twins, plus **four** hand-rolled `meeting_meta` upsert variants — including an insert race where two concurrent requests both see "no row" and one 500s on the PK. |
| 32 | `app/hermes_dispatch.py:724` | `publish_session_effort` does a second full locked read-modify-write of `session-keys.json` immediately after `publish_session_key`'s — double the file churn per dispatch, and a racing plugin read between the two writes sees the key without the effort. |
| 33 | `app/server.py:2626` | `meetings_list` does `SELECT *` — pulling full summary/requirements blobs (up to 20 k chars each) — just to compute two booleans, on a **5 s poll** while a meeting is live. |
| 34 | `app/static/app.js:344` | Bulk actions fetch `/api/tasks` **twice**: the click handler refetches manually *and* the `tasks_bulk_updated` WS broadcast triggers a second identical refetch. |
| 35 | `app/server.py:711` | `create_task` re-validates the routed model against `db.task_models_for(uid)` although `routing.select_model_for_task` only ever returns models from that exact set — a dead branch plus a redundant registry query per task create. |
| 36 | `app/server.py:2670` | The new blocking helpers (`_meeting_llm_turn`, `_task_branch_ctx` (shells out to git), `_github_ctx`) were **not** registered in `check_async_blocking.py` — eroding the B7 event-loop enforcement the repo convention depends on. |
| 37 | `app/scripts/verify_phase_c_e2e.py:21` | Dead boilerplate copied between gates (unused `httpx` import + `BASE` constant; `verify_stop_e2e.py:41` imports `worktree` unused) — and a **third** copy of worker.py's `.env` loader. A tiny `scripts/_gate_common.py` would stop the copy-paste. |

---

# Refuted (1)

**`app/feedback_log.py:242` — chain-adoption defeats the Origin dedupe.** The claim was that when
user C adopts user B's *adopted copy*, the `Origin:` bullet records B's copy key rather than the
root entry's, breaking dedupe. **The verifier refuted it**, and inspection agrees: `adopt_entry`
copies `entry["raw"]`, which for an adopted copy **already contains the original
`- Origin: <root-key>` bullet**; `parse_entries` reads the *first* `Origin` field, so the root key
survives the chain and the dedupe still fires. No action needed.

---

# Recommended fix order

1. **#2** (stub leak) and **#1** (LIKE wildcards) — one can corrupt every future deliverable, the
   other can destroy an unrelated project. Both are cheap.
2. **#3** (XSS) — cheap mitigation now, event-binding fix after.
3. **#4, #5, #6** — isolation breach, irreversible data loss, and the silently broken rework loop.
4. **#7, #8** — the stop feature does not yet fully do what it promises.
5. **#9, #10, #16** — one-line clamps that restore the cost contract (all three are holes in the
   mode-coherence/session-effort work).
6. **#11–#25** — the medium-severity correctness set (several are one-liners: #18, #21, #25).
7. **#26–#37** — cleanup, ideally as one "kill the duplicate definitions" pass (#26–#29 are all the
   same disease: the same concept declared in 3–4 places and already drifting).

All findings except the refuted one carry a CONFIRMED (or, in P3, PLAUSIBLE) verdict from an
independent verifier agent instructed to refute them; #1, #2 and #3 were additionally re-checked by
hand against the code while writing this report.
