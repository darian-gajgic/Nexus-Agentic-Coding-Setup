# NEXUS Agent OS — Stabilization Runbook (foolproof, step-by-step)

**Companion to `STABILITY-AUDIT-2026-07-08.md`.** This merges the deep code audit (86 verified defects) with the two runtime recon briefs (frequency data + integration/housekeeping items) into ONE ordered plan, then tells you *exactly* what to do — which folder, which model, which effort, which prompt, how to verify, and how to undo — so you can execute it with maximum success and minimum risk.

Follow it top to bottom. Do **one batch at a time**. Do not skip the PREP.

---

## 0. Rules that keep you safe (read once)

1. **The running app only changes when you restart it.** Editing files does NOT affect the live service until `systemctl --user restart nexus`. So a half-finished edit can't hurt the running system — the restart is the only "deploy".
2. **`app/` IS the live tree** (`~/nexus-agent-os` is a symlink to it). You edit it directly on `main` — that is the project's endorsed flow. **Do not create git worktrees or `git checkout` other branches** for this — the `.venv` and `nexus.db` live in `app/` and only work there, and a branch switch would swap the running code.
3. **Every commit is gated** by `scripts/verify.sh` (251 checks) via the pre-commit hook. Broken code literally cannot be committed.
4. **One batch = one commit = one restart = one smoke test.** If a batch is bad after restart, you revert exactly that one commit. Clean and reversible.
5. **You (the human) own the deploy gate.** Claude Code writes the code, runs `verify.sh`, and shows you the diff — then STOPS. *You* review, say "commit", restart, and eyeball it in the browser.
6. **Multi-user is live** (there's a real user, `ariana`). A restart briefly interrupts anyone using it — do this when the system is quiet.
7. **No `sudo` is needed** for any code fix or restart (`systemctl --user` is your own service). Only the optional Timeshift snapshot needs sudo.

---

## 1. The merged, re-ranked backlog

Ranked by **impact × how often it actually fires** (runtime evidence from the recon briefs, which I re-verified against the live system). Each row says which batch fixes it.

### P0 — fixes the instability you feel (do first)

| Item | Source | Runtime evidence (verified) | Batch |
|---|---|---|---|
| `/api/stats` `psutil(interval=0.5)` freezes the loop every 3 s | Audit F013 | dashboard polls it every 3 s → ~17 % idle stall | **B1** |
| `health_full` runs `systemctl` on the loop, polled every 3 s | Audit F045 | Agentic tab poll | **B1** |
| Auth middleware writes SQLite on the loop **every request** | Audit F048/F028 | every authenticated call | **B1** |
| `jarvis_tts_ws` leaks a coroutine + blocks graceful shutdown | Audit F011 | **16 "graceful shutdown exceeded" tracebacks** in the journal | **B2** |
| SSE chat stream has no client-disconnect handling | Audit §3.2 | the aiohttp mid-request drops both briefs saw | **B2** |
| JARVIS TTS onclose wedges "speaking"; hardcoded `wss://`; dup sockets | Audit F063/F130 + research | JARVIS "stuck" symptom | **B2** |
| ~12 more blocking sites (git/gh/qdrant/copytree/mem0) on the loop | Audit F006/F007/F014/F015/F018/F012/F001/F002/F003 + cluster | pervasive lag (invisible to logs) | **B3** |
| Dispatch: empty-reply→QuotaError stalls the whole fleet; slot cap counts the wrong model **on every overload-fallback** (verified — the frequent path, not the narrow NULL-model one); resume drops the task brief | Audit re-hunt | **189/454 executor-resumes; 30 overload events** | **B4** |
| STT retries CUDA again before CPU; vision OOM guard too narrow; no cross-process GPU lock | Audit §3.6 | **10 CUDA-OOM events, 600 s degradations** | **B5** |
| Vision worker timeout leaks reader thread + desyncs protocol | Audit F025/F068 | vision "black camera" / hang symptoms | **B5** |

### P1 — correctness, data-integrity, isolation, broken features

| Item | Source | Batch |
|---|---|---|
| `replan/apply` non-atomic → can lose tasks | F017 | **B6** |
| Tasks created in a focused project lose the project (`workflow_id` sent twice) | F021 | **B6** |
| Memory galaxy crashes to blank when memories have no links | F024 | **B6** |
| Verifier verdict parsed by substring → can invert PASS/FAIL | F033 | **B6** |
| Briefing counts ALL users' approvals; shared-fleet reads ungated | F042/F041 | **B6** |
| Inline HTML/SVG workspace files → stored XSS | F008/F106 | **B6** |
| Cron scheduler never executes the job (inert) | F004 | **B6** (decision) |
| Chat mislabels auth/server errors as "provider overloaded" | F132 | **B6** |
| Watchdog: **no restart circuit-breaker** (F073, real). The "stuck removes lane from monitoring" (F074) only bites if `watchdog.restart_on_stuck=0` — default is on, so a stuck lane is restarted, not parked → F074 is low-priority | F073/F074 | **B6** |
| Kanban drag breaks after search; first-visit project filter empty; memory3d user always empty | F022/F129/F118 | **B6** |
| `jarvis_session.json` unlocked read-modify-write race | F010/F036 | **B6** |
| JARVIS brain: blocking `~/knowledge` reads on loop; ignores per-user overlay | Audit re-hunt | **B4** |

### P2 + Housekeeping — cheap, low-risk, do last

| Item | Source | Batch |
|---|---|---|
| ~30 P2 one-liners (LIKE escaping, filename collision, Chart.js destroy, missing-dir guard, upload size, env dup line, …) | Audit §6 | **B7** |
| Doc drift: `setup/CLAUDE.md` says "5 core-mods", there are **6** (document `session-model-api-server`) | Recon R1/R2 D1 | **B7** |
| Stale artifacts: remove `app/.worktrees/nexus-b2probe*`; move `nexus.db.bak-*` out of the tree; mark `lipsync.py`/`/talk`/`/lipsync` RETIRED; drop `tools_hub` stale scanners (`_tool_glm`, `_tool_supermemory`) | Recon R1/R2 | **B7** |
| `SPEC.md` still says Wav2Lip; `verify.sh` count in docs says 52 not 251 | Recon D2/D3 | **B7** |
| `session-keys.json` non-atomic write (corrupts all keys on crash); `loop_engine` HTTPS-only self-call (latent — certs exist today); DB migrations have no version tracking | Recon R2 P4 | **B7** |
| **Regression guards**: `verify.sh` check rejecting blocking calls in `async def`; per-task dispatch resume-rate metric; "why did the worker die" logging | Merge | **B4 + B7** |

**What we deliberately do NOT chase:** the Z.AI 429 storm itself is *upstream* (provider load-shedding) — B4 fixes the app-side bugs that *amplify* it, but a real cure (rate-budgeting / second provider) is a business decision, not a code fix. And the "33 restarts" both briefs flagged is mostly normal dev-deploy cadence (I checked: 33 stops = 33 starts over 33 commits), not a crash loop — the real signal is the 16 shutdown timeouts, fixed in B2.

**Corrections folded in from a follow-up review (verified against source):** (1) the watchdog "stuck-removes-lane" concern (F074) is **config-gated** — `restart_on_stuck` defaults to on, so it's low-priority; the restart circuit-breaker (F073) is the real watchdog fix. (2) The dispatch slot-accounting mismatch is driven mainly by the **overload-fallback path** (frequent during 429 storms), not the narrow NULL-model case. (3) The Wav2Lip `/talk`+`/lipsync` endpoints are **live + reachable** (not merely dormant) and load GPU, so B7 **disables** them rather than just commenting. Everything else in the plan is unchanged.

---

## 2. Universal procedure — do this for EVERY batch

> Repo root = `~/Nexus-Agentic-Coding-Setup`. App dir = `~/Nexus-Agentic-Coding-Setup/app`.

1. **Open a fresh Claude Code session at the repo root** (fresh per batch keeps context clean):
   ```bash
   cd ~/Nexus-Agentic-Coding-Setup && claude
   ```
2. **Set the model and effort** for this batch (from the batch header):
   ```
   /model <opus|sonnet|fable>
   /effort <high|xhigh|medium>
   ```
3. **Paste the batch prompt** (verbatim, from Section 4).
4. Claude implements, runs `bash app/scripts/verify.sh`, and shows you the diff, then **stops**. **Read the diff.** If anything looks wrong or out of scope, tell it to fix; don't proceed until you're happy.
5. **(P0/P1 batches only) Review pass** — in the same session:
   ```
   /code-review high
   ```
   Tell it to fix any *real* findings, then re-show the diff.
6. **Say "commit"** — e.g. `commit the app/ changes only, message: "<the batch commit message>"`. The pre-commit hook re-runs verify.sh; if it's blocked, verify.sh failed — read the output and have Claude fix it, then retry.
7. **You deploy** (in a normal terminal, not Claude):
   ```bash
   systemctl --user restart nexus && sleep 3 && systemctl --user is-active nexus
   ```
8. **You smoke-test** — run the batch's runtime check + look in the browser (see each batch).
9. **Go / No-Go:**
   - **Good** → next batch.
   - **Bad** → undo just this batch and tell me what broke:
     ```bash
     cd ~/Nexus-Agentic-Coding-Setup && git revert --no-edit HEAD && systemctl --user restart nexus
     ```

---

## 3. PREP — one time, before Batch 1

Run these in a normal terminal:

```bash
cd ~/Nexus-Agentic-Coding-Setup

# 1. Confirm you're on main with a clean tree (untracked *.md at the root is fine)
git status

# 2. Rollback anchors
git tag pre-stability-fixes
mkdir -p ~/nexus-fix-backups && cp app/nexus.db ~/nexus-fix-backups/nexus.db.pre

# 3. Confirm a green baseline
cd app && bash scripts/verify.sh          # expect: ALL CHECKS PASSED: 251/251
systemctl --user is-active nexus          # expect: active
```

Optional extra safety net (needs sudo — first run `sudo -v` in your terminal):
```bash
sudo -n timeshift --create --comments "pre nexus stability fixes" 2>/dev/null || echo "skip timeshift"
```

---

## 4. The batches

Universal HARD RULES are baked into every prompt — do not remove them.

---

### BATCH 1 — Event-loop quick wins (kills the constant lag)
- **Model / effort:** `opus` / `high`  ·  **Review pass:** no  ·  **Frontend cache-bust:** no

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 3.1 for exact file:line and fixes.

Fix ONLY these three, surgically:
1. F013 — app/agent_manager.py get_system_stats(): change psutil.cpu_percent(interval=0.5) to interval=None, and prime it once at startup (call psutil.cpu_percent(interval=None) where the app boots or the metrics background thread starts) so the first read isn't 0.
2. F045 — app/server.py health_full (~line 3674): get the systemctl subprocess off the event loop (either make the handler a plain `def`, or wrap the subprocess in starlette.concurrency.run_in_threadpool / asyncio.create_subprocess_exec).
3. F048/F028 — app/auth.py resolve_session (~line 172) + the AuthMiddleware in app/server.py (~line 56): only write last_seen when it's older than ~60s (so most requests are read-only), and skip session resolution entirely for /static/ paths in the middleware.

HARD RULES:
- Change ONLY what these items require. No refactors, renames, unrelated cleanups, or new features. Preserve exact behavior except the bug.
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, or anything outside app/ source.
- Then run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — it must print ALL CHECKS PASSED.
- Show me the FULL diff + a one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(perf): stop /api/stats, health_full, and auth middleware from blocking the event loop`
**Smoke test (after restart):**
```bash
cd ~/Nexus-Agentic-Coding-Setup/app
# /api/stats should respond fast now (was ~0.5s). Log in via the browser first, then in the UI the dashboard should feel snappier.
.venv/bin/python scripts/verify_agentic_e2e.py   # 30 checks, should pass
```
Browser: open `https://127.0.0.1:8777`, click around the dashboard/kanban — it should no longer stutter every ~3s.

---
/code-review high/code-review high/code-review high/code-review high/code-review high
### BATCH 2 — WebSocket/SSE shutdown + JARVIS voice stability (kills the 16 shutdown timeouts)
- **Model / effort:** `opus` / `xhigh`  ·  **Review pass:** YES (`/code-review high`)  ·  **Frontend cache-bust:** YES

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 3.2 and 3.5. This fixes the 16 "graceful shutdown exceeded" tracebacks confirmed in the live journal, and JARVIS getting stuck.

Backend (app/server.py):
1. F011 — jarvis_tts_ws (~line 2542): the handler parks on `await q.get()` while a separate watcher task owns ws.receive_json(), so an idle disconnect never wakes it. Make the synth loop and the socket reader RACE a disconnect (asyncio.wait(..., return_when=FIRST_COMPLETED) or an asyncio.TaskGroup). In the finally, cancel AND await the watcher (watcher.cancel(); await asyncio.gather(watcher, return_exceptions=True)). On asyncio.CancelledError: clean up then RE-RAISE it — do NOT swallow it.
2. SSE stream — jarvis_chat_stream (~line 1953): add a `request: Request` parameter and check `if await request.is_disconnected(): return` at each yield boundary; emit a terminal `event: done\ndata: [DONE]\n\n` in a finally. Keep blocking work out of the async generator.

Frontend (app/static/app.js):
3. F063 — in the TTS websocket onclose/onerror and after {done}/{error}: always reset the speaking/animation state and drop queued PCM chunks so the avatar never gets stuck "talking".
4. F130 — guard jarvisSpeak so only ONE TTS socket is ever open (reuse/await the connecting one).
5. Hardcoded scheme (~app.js:5999): change `new WebSocket(\`wss://...\`)` to derive the scheme from location.protocol, exactly like the main socket at ~app.js:282.

HARD RULES:
- Change ONLY what these items require. No refactors/renames/new features. Preserve behavior except the bugs.
- Because you edit app/static/, bump the ?v=N cache-buster in app/static/index.html (verify.sh checks this).
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff + one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(jarvis): WS/SSE disconnect cleanup (fixes shutdown hang + stuck-speaking)`
**Smoke test (after restart):**
```bash
cd ~/Nexus-Agentic-Coding-Setup/app
.venv/bin/python scripts/verify_jarvis_v2_backend.py            # 23 checks
# Confirm the restart itself is now clean (no shutdown-timeout traceback):
systemctl --user restart nexus && sleep 3
journalctl --user -u nexus -n 80 --no-pager | grep -c "graceful shutdown exceeded"   # expect 0
```
Browser: open JARVIS, speak a sentence, then **close the tab mid-reply** — reopen; JARVIS should be idle and responsive, not wedged.



### BATCH 3 — De-block the rest of the event loop (kills the pervasive lag the logs can't see)
- **Model / effort:** `opus` / `xhigh` (use `fable` if you want maximum assurance)  ·  **Review pass:** YES  ·  **Frontend cache-bust:** no

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 3.1, the big site table. Batch 1 already fixed /api/stats, health_full, and the middleware. De-block EVERY OTHER site in that table (F006, F007, F014, F015, F018, F012, F001, F002, F003, and the rest: memory edit/merge, tools_hub scanners, project git/gh/PR, memory3d, onboarding apply, app-preview stop/log, task retry, review build, task_wizard git, list_deliverables).

The rule for each site:
- A handler with NO `await` in its body → make it a plain `def` (FastAPI runs it in a threadpool automatically).
- A handler that DOES `await` something → keep `async def` and wrap ONLY the blocking call in `await starlette.concurrency.run_in_threadpool(fn, ...)`.
- Replace `subprocess.run(..., timeout=N)` with `await asyncio.create_subprocess_exec(...)` + `await asyncio.wait_for(proc.communicate(), N)` where the handler stays async.
- NEVER convert a handler to `def` if it awaits anything — that would break it.

Do it site-by-site, keep the diff readable, group related edits.

HARD RULES:
- No behavior change beyond moving blocking work off the loop. No new features/refactors.
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff grouped by file, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(perf): move remaining blocking subprocess/qdrant/git/fs work off the event loop`
**Smoke test (after restart):**
```bash
cd ~/Nexus-Agentic-Coding-Setup/app && .venv/bin/python scripts/verify_agentic_e2e.py
```
Browser: click the **Projects, Memory, Review, Onboarding** tabs and run a **▶ Test project** — none should freeze the whole UI while they work.

---

### BATCH 4 — Dispatch engine + JARVIS brain correctness (fixes the 189 resumes / 30 overloads)
- **Model / effort:** `opus` / `xhigh` (use `fable` for max assurance — this is real-money, concurrency-critical)  ·  **Review pass:** YES  ·  **Frontend cache-bust:** no

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 3.7 and section 4 (the dispatch slot/resume/telemetry findings + the JARVIS-brain overlay finding). This is real-money, concurrency-sensitive code — be careful and precise. NOTE: items 6-7 are NOT in the audit — they were surfaced by the Batch 1-3 review passes; locate them by reading the orphan-dispatch reconciler (grep "reconcil" in app/hermes_dispatch.py) and the boot-reconcile in app/server.py startup.

Fix in app/hermes_dispatch.py:
1. slots_in_use() (~line 227): it counts by the raw t.model column, but run_task_dispatch runs on run_model = fallback_model or resolve_task_model(task) (~line 952) and NEVER updates tasks.model on a fallback (~lines 1078-1089). So EVERY overload-fallback dispatch is counted under the ORIGINAL model, not the glm-5-turbo it actually runs on — under-counting the fallback pool so it admits too many and causes MORE 429s during a storm. Fix: count by the effective run-model actually in use (e.g. persist the effective model on the dispatch row and GROUP BY that). The NULL-tasks.model case is the minor sub-case; the fallback case is the frequent one.
2. Resume path (~line 1034): when a worker died before a session was really established, send the FULL brief (title + description) instead of the bare "continue" stub. Only send "continue" when there is genuine prior session/transcript context.
3. _finalize_result (~line 796): an empty/short reply with no deliverable.md must NOT be blanket-raised as QuotaError. In repo mode, a non-empty changes.diff = success. Only raise QuotaError on an actual rate-limit signature.
4. on_event telemetry (~line 746): wrap the streaming db.execute telemetry writes in try/except so a transient SQLite error can't abort the stream.
5. Add structured logging capturing WHY a worker dies (CUDA OOM / Hermes timeout / QuotaError / other) so "executor died" isn't the only signal.
6. The orphan-dispatch reconciler wrongly RESETS tasks that are merely WAITING FOR A CONCURRENCY SLOT (not dead) — treating a slot-parked task as orphaned and resetting/re-dispatching it. Scope the reconciler so it only reclaims genuinely dead/orphaned dispatches, never ones parked waiting on the slot gate. (Surfaced by the Batch 1-3 review passes.)
7. The boot-time reconcile PREEMPTS the session-resume path — a task that should resume its existing Hermes session (harvest-or-continue) instead gets reset/re-dispatched at boot. Make boot reconcile defer to resume: if a live/harvestable session exists, resume it rather than reset. (Surfaced by the Batch 1-3 review passes; directly reduces the 189-resume churn.)

Fix in app/jarvis_brain.py:
8. Move the ~/knowledge file reads off the event loop (run_in_threadpool), and honor the per-user knowledge overlay (users/<uid>/...) — jarvis_brain.py:82 always returns the owner's canonical ~/knowledge; mirror what dispatch ALREADY does correctly at hermes_dispatch.py:568-581 (this is a JARVIS-only gap).

HARD RULES:
- No behavior change beyond these fixes. Do not alter the budget/quota policy numbers.
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, setup/, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff + one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(dispatch): slot accounting, resume brief, quota misclassification, reconciler slot-wait/resume preemption + why-died logging`
**Smoke test (after restart):**
```bash
cd ~/Nexus-Agentic-Coding-Setup/app
# NOTE: this spawns a REAL Hermes session and costs GLM tokens. GLM-dependent steps
# fail while Z.AI is load-shedding (error 1305) — that is upstream, not your fix.
.venv/bin/python scripts/verify_real_dispatch_e2e.py
```
Then create one real task in the UI and watch it dispatch → deliverable without looping.

---

### BATCH 5 — GPU / VRAM discipline (fixes the 10 CUDA-OOM degradations)
- **Model / effort:** `opus` / `high`  ·  **Review pass:** no  ·  **Frontend cache-bust:** no

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 3.6.

Fix:
1. app/voice.py STT self-heal: on the FIRST CUDA out-of-memory, go straight to the CPU model — set the GPU-block flag immediately; do NOT retry CUDA one more time (it just OOMs twice).
2. app/vision_worker.py: broaden the _is_oom detection to also treat cudaErrorInvalidDevice, cuBLAS errors, and generic CUDA alloc failures as "fall back to CPU".
3. Add a CROSS-PROCESS GPU lock (a simple file lock, e.g. via fcntl on a lockfile) so faster-whisper STT, SigLIP, SDXL, and the ollama VLM serialize their heavy GPU sections instead of colliding and OOMing.
4. app/vision.py (F025/F068, ~line 94-104): on a vision worker request timeout, kill AND respawn the worker (don't leave the reader thread blocked on stdout.readline() and the JSON-lines protocol desynced).
5. After dropping any model, call gc.collect() so VRAM is returned promptly.

HARD RULES:
- Preserve behavior except the OOM handling. No new features.
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff + one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(gpu): CPU-on-first-OOM, broaden vision OOM guard, cross-process GPU lock, respawn wedged worker`
**Smoke test (after restart):** this one is hard to force deterministically. In the browser, use JARVIS **voice input** and the **vision popup** a few times while watching a terminal running `watch -n1 nvidia-smi`. STT should degrade to CPU cleanly (no repeated OOM), and the vision worker should recover instead of hanging.

---

### BATCH 6 — P1 correctness, isolation, broken features
- **Model / effort:** `opus` / `high`  ·  **Review pass:** YES  ·  **Frontend cache-bust:** YES (it touches app.js)

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 4 (and the finding IDs below). Fix each precisely — no unrelated changes.

Backend (app/server.py + modules):
- F017 (server.py ~4925): make replan/apply atomic — validate/create all recovery tasks BEFORE the destructive archival, or wrap in one transaction, so a mid-loop failure can't leave archived-but-not-recreated tasks.
- F042 (~2467) + F041 (~2674): scope the JARVIS briefing approval count to the calling user; add the is_admin()/owner check to the ungated shared-fleet READ endpoints.
- F008 (~3192) + F106 (~2321): serve uploaded/agent-written .html and .svg workspace files as Content-Disposition: attachment / media_type text/plain (never inline text/html) — stored-XSS fix.
- F033 (app/loop_engine.py ~200): parse the verifier verdict from a structured token, not a naive substring (so "failures"/"passed" can't invert PASS/FAIL).
- F073 (app/watchdog.py ~123/~137): add a restart circuit-breaker — restart_count is incremented but never checked against a max, so a hot-crashing lane respawns forever. This is the REAL watchdog fix. (F074 "stuck removes lane from monitoring" is config-gated: with the default watchdog.restart_on_stuck=1 a stuck lane is restarted at ~line 137 and never reaches the status='stuck' dead-end at ~line 144 — just harden that else-branch, don't rewrite the healthy path.)
- F118 (~5735): fix the memory3d node "user" attribute reading the wrong payload key.
- F004 (app/scheduler.py ~100) — DECISION NEEDED: right now a scheduled job only writes a label + logs; it never runs. Change _trigger so a fired job actually creates+enqueues a task (so scheduled jobs do real work). If you believe it should stay notify-only, DO NOT change it — tell me and STOP for that item.
- F010/F036 (~1610-1663): serialize the per-user jarvis_session.json read-modify-write (a lock or atomic replace) so concurrent turns don't lose messages.

Frontend (app/static/):
- F021 (app.js ~4519): the POST body sets workflow_id twice — delete the duplicate key so a task created in a focused project keeps its project.
- F024 (memory3d.js ~223): guard the no-similarity-links case so the galaxy doesn't render blank.
- F132 (app.js ~6635): in jarvisStreamChat, check res.ok/status and surface the real error instead of always "provider overloaded".
- F022 (app.js ~1254): re-set the drag handlers (dragId) after the kanban search re-render.
- F129 (app.js ~1108): re-render the project filter after loadWorkflows() on first kanban visit.
- Dead JARVIS command-deck ▶ Test button (surfaced by the Batch 1-3 review passes): the deck's ▶ Test control is a no-op — wire it to the same testAppUI/preview path the Deliverables ▶ Test uses, or remove it if redundant. grep the command-deck render in app.js for the deck's Test handler.

HARD RULES:
- Bump ?v=N in app/static/index.html (you edit app.js). No unrelated changes.
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, setup/, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff + one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(correctness): replan atomicity, isolation gating, XSS, verdict parse, scheduler, session race + UI bugs`
**Smoke test (after restart):**
```bash
cd ~/Nexus-Agentic-Coding-Setup/app
.venv/bin/python scripts/verify_block3_e2e.py    # replan/eval (33 checks)
.venv/bin/python scripts/verify_block2_e2e.py    # review v2 (48 checks) — needs qdrant+ollama up
```
Browser: create a task inside a project (it should keep the project), open the memory galaxy, run kanban search + drag a card.

---

### BATCH 7 — P2 one-liners + housekeeping + regression guards
- **Model / effort:** `sonnet` / `medium`  ·  **Review pass:** no  ·  **Frontend cache-bust:** YES if it touches app.js/css

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 6 (the P2 table) and FIX-RUNBOOK-2026-07-08.md section 1 (P2 + Housekeeping). Apply ONLY these — all are small/low-risk. One logical change each.

A) P2 one-liners from audit §6 (fix as many as are clearly a ≤10-line change; skip any that would touch more):
   server.py:6151 escape LIKE wildcards; server.py:2440 make imagine filename unique (add a counter/uuid); static/app.js:4135 Chart.js .destroy() before re-create; tools_hub.py:259 guard missing ~/.hermes/skills dir; server.py:3390 check upload size while streaming, not after buffering; secrets_store.py:174 don't leave two active lines for one env var; app_runner.py preview log size cap; worker.py:57 bound the _slot_wait_logged dict.

B) Housekeeping (from the recon briefs):
   - Update setup/CLAUDE.md and docs/PROJECT-DOCUMENTATION.md: change "5 core-mods" to "6" and document the session-model-api-server core-mod as the keystone of model routing.
   - Update docs/SPEC.md note about Wav2Lip → Three.js particle avatar; fix the "52 checks" mention to 251.
   - Wav2Lip is NOT actually dormant: /api/jarvis/talk + /api/jarvis/lipsync (server.py ~2235-2270) are fully wired and reachable, and hitting them loads Wav2Lip onto the shared 12 GB GPU. Since the frontend no longer calls them, DISABLE the two routes (return 410 Gone, or gate behind an explicit admin-only setting) rather than just commenting lipsync.py — then fix the docs that call them "dormant". Also remove the dead _tool_glm / _tool_supermemory scanners from tools_hub.py.
   - Make ~/.hermes/session-keys.json writes atomic (write to a temp file, then os.replace).

C) Regression guard: add a check to app/scripts/verify.sh that FAILS if `subprocess.run(` or `cpu_percent(interval=<nonzero>)` appears inside an `async def` handler in app/server.py or app/agent_manager.py.

Do NOT touch app/.worktrees or the nexus.db.bak files here — I'll clean those by hand.

HARD RULES:
- Bump ?v=N in app/static/index.html if you edit app.js/css. No refactors beyond the listed items.
- Do NOT edit .venv, workspaces/, nexus.db, or anything outside app/ + setup/ + docs/.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED (with your new guard passing too).
- Show me the FULL diff + one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `chore: P2 fixes, doc drift, retire dead code, atomic session-keys, async-blocking regression guard`
**After committing this batch**, clean the two stale-artifact items by hand (they were flagged by both recon briefs):
```bash
cd ~/Nexus-Agentic-Coding-Setup
git rm -r --cached app/.worktrees/nexus-b2probe46fd7af3 2>/dev/null; rm -rf app/.worktrees/nexus-b2probe46fd7af3
mkdir -p ~/nexus-fix-backups/olddb && mv app/nexus.db.bak-* ~/nexus-fix-backups/olddb/ 2>/dev/null || true
# NOTE: the `git rm --cached` above is already staged — do NOT run `git add -A`
# (it would sweep the untracked root docs / .serena into this commit).
git commit -m "chore: remove stale probe worktree from tracking; move db backups out of the tree" || true
```

---

## 5. Final regression + sign-off

After Batch 7, in a terminal:
```bash
cd ~/Nexus-Agentic-Coding-Setup/app
systemctl --user restart nexus && sleep 3 && systemctl --user is-active nexus
bash scripts/verify.sh                                   # 251+ checks, all green
.venv/bin/python scripts/verify_agentic_e2e.py           # 30
.venv/bin/python scripts/verify_v3_ui.py                 # 24 (UI)
.venv/bin/python scripts/verify_jarvis_e2e.py            # 6 (JARVIS)
.venv/bin/python scripts/screenshot_all_tabs.py final    # screenshots all 14 tabs, fails on console errors
# Confirm the shutdown hang is gone for good:
journalctl --user -u nexus --since "10 min ago" --no-pager | grep -c "graceful shutdown exceeded"   # expect 0
```
Then do a human walkthrough: dashboard is snappy, JARVIS speaks + recovers on tab close, a project task dispatches to a deliverable, the memory galaxy renders. If all green, you're done. Delete the temp backups when you're confident: `rm -rf ~/nexus-fix-backups` (keep them a few days first).

---

## 6. Rollback playbook (if anything goes wrong)

| Situation | Command |
|---|---|
| One batch is bad right after restart | `cd ~/Nexus-Agentic-Coding-Setup && git revert --no-edit HEAD && systemctl --user restart nexus` |
| A batch several commits back is bad | `git revert --no-edit <that-commit-sha> && systemctl --user restart nexus` |
| Abort ALL fixes, back to the start | `git reset --hard pre-stability-fixes && systemctl --user restart nexus` *(discards every fix commit — last resort)* |
| Database looks corrupted | `systemctl --user stop nexus && cp ~/nexus-fix-backups/nexus.db.pre app/nexus.db && systemctl --user start nexus` |

`git revert` is preferred over `git reset` because it's non-destructive (keeps history). Never `git checkout` a different branch on this repo — it swaps the running code.

---

## 7. Process changes to keep (so this can't silently come back)

1. **Stop trusting "verify.sh green = healthy."** The whole reason this happened: static + happy-path tests can't see event-loop blocking, races, leaks, or contract drift. The async-blocking guard added in Batch 7 is step one; also turn on asyncio debug mode in dev to log slow callbacks.
2. **Run recon + frontier as a pipeline, not either/or.** Cheap-model runtime recon (logs/journal/DB — GLM's strength) to find symptoms + frequency, THEN a frontier deep-audit (root-cause code defects + fix correctness) — and feed the recon's frequency numbers into the audit to rank fixes. This exercise proved neither alone is enough.
3. **Instrument the runtime signals** the recon surfaced: dispatch resume-rate per task, "why did the worker die", VRAM headroom. Batch 4 adds the why-died logging; make the resume-rate a visible metric.
4. **The `session-model-api-server` core-mod is invisible, load-bearing coupling.** Any "models not switching / fallback not firing" investigation must first verify all 6 core-mods apply: `python setup/guardian/guardian.py` → expect `overall=OK, 6/6`.
5. **Consider extracting the JARVIS routes out of the 6,493-line `server.py`** before the next feature round — 18 of the last 33 commits touched that one file, and every JARVIS edit risks the other 180 routes. (Not part of this stabilization; a follow-up.)

---

## 8. Post-Batch-4 live-testing discoveries (2026-07-09)

Found while the operator exercised the live system after Batch 4. Two are **fixes** to schedule; one is a **feature** for the very end.

### FIX — Batch 8 (THE LAST FIX, after Batches 5-7): Tab-switch truncates the JARVIS reply ("Option C", regression from Batch 2)
Switching views/tabs mid-reply **cuts JARVIS off mid-sentence** (confirmed: "Today sits [stopped]"). Mechanism: browser closes the chat SSE → the Batch-2 `request.is_disconnected()` check returns → Nexus closes its connection to Hermes → Hermes aborts the generation (the `ClientConnectionResetError`). This is a regression the Batch-2 SSE change introduced (pre-Batch-2 the reply completed silently). Fleet tasks are unaffected (they run in a worker subprocess, not tied to the browser).
**Operator's requirement: JARVIS must KEEP TALKING across a tab switch** — not just complete server-side. So the fix is neither "complete silently" (A) nor "decouple" (B) but **C = keep the live stream + TTS + audio alive across view switches:**
- Server: remove/soften the `is_disconnected` kill for JARVIS chat so a transient disconnect never aborts the Hermes run.
- Frontend: move JARVIS's live-turn stream, TTS WebSocket, and AudioContext out of the per-view DOM into a **persistent background singleton** that survives `renderView` (view switches) and does NOT stop on `visibilitychange` (browser-tab background). The view attaches to it; it isn't destroyed when you navigate away.
Moderate frontend refactor. Also fold in **F103 (from the Batch 6 review):** after Batch 6's F041 admin gates, member accounts (e.g. ariana) now get `403` on the Agentic view's watchdog/scheduler/verify-runs/agent-memory/messages panels (correct isolation), but the frontend still *shows* those panels and errors on them. Hide the admin-only Agentic panels for non-admin users so members get a clean view instead of 403 errors. Owner/admin unaffected.

Code anchors (verified 2026-07-09): the streamed reply accumulates into a plain JS object `liveMsg` in `jarvisState.messages` (NOT DOM-bound — only `jarvisRenderFeed()` paints it), so the turn CAN keep running in the background; the ONLY thing stopping it on a view switch is `jarvisTeardown()` (app.js ~6270) calling `jarvisStopStreaming()` → `abortController.abort()` + `jTTS.ws.close()`, invoked by `switchView()` (~512). Server kill: `jarvis_chat_stream` / `event_generator` `if await request.is_disconnected(): return` (server.py ~2208). Admin signal already exists client-side (`modelState.isAdmin` ~2092; `/api/auth/state` ~137).

- **Model / effort:** `opus` / `xhigh` (subtle audio/stream-lifecycle refactor — Fable at `xhigh` equally fine)  ·  **Review pass:** YES  ·  **Frontend cache-bust:** YES

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/FIX-RUNBOOK-2026-07-08.md section 8 (the "Batch 8" entry — the mechanism, code anchors, and scope note for BOTH fixes live there; neither is in STABILITY-AUDIT). Also read app/CLAUDE.md's "Live updates" + JARVIS v2 notes. This is Batch 8 of the Nexus stabilization: TWO fixes, mostly frontend (app/static/app.js). Study the real code before editing — anchors below are from 2026-07-09; verify them.

=== FIX 1 — "Option C": JARVIS must KEEP TALKING across a view/tab switch (regression from Batch 2) ===
BUG: switching away from the JARVIS view mid-reply cuts JARVIS off mid-sentence ("Today sits [stopped]"). Traced: switchView() (~505) calls jarvisTeardown() (~6270) on leaving jarvis; teardown calls jarvisStopStreaming() → jarvisState.abortController.abort() and closes jTTS.ws — the aborted fetch closes Nexus's SSE → Nexus closes its httpx stream to Hermes → Hermes aborts. KEY FACT (verify): the streamed reply text accumulates into a plain JS object `liveMsg` in jarvisState.messages (jarvisStreamChat ~6647, reader loop ~6710 via jarvisHandleSSE) — NOT DOM-bound; only jarvisRenderFeed() paints it. So the turn CAN keep running in the background; the abort is the only thing stopping it.
REQUIRED: when the user navigates away (in-app view switch OR backgrounds the browser tab) with a turn in flight, the turn KEEPS STREAMING and JARVIS KEEPS SPEAKING; on return the feed shows the (possibly finished) reply. NOT "finish silently" — audio must continue.
IMPLEMENT (client, app.js):
1. Split jarvisTeardown into (a) jarvisViewDetach() — VISUAL-ONLY, safe on every view switch: dispose the 3D avatar (window.Jarvis3D.dispose()), stop the avatar RAF/mouth loop, stop mic CAPTURE if recording (mediaRecorder + getUserMedia tracks), stop webcam/screen capture, stop the barge-in monitor; does NOT abort the stream, close jTTS.ws, or close the AudioContext — and (b) jarvisHardStop() — the FULL stop (abort stream + jarvisStopTTS + close jTTS.ws + reset) called ONLY on explicit user Stop, on starting a NEW turn, or on logout. Change switchView (~512) to call jarvisViewDetach(), not the full teardown.
2. Keep the in-flight SSE fetch + reader loop running when detached. GUARD every DOM write in the streaming path (jarvisRenderFeed, jarvisSpeakProgress, status/domain handlers) to NO-OP when the JARVIS DOM is absent (e.g. `const feed=$('#jarvisFeed'); if(!feed) return;`) so streaming keeps updating jarvisState.messages without throwing when #content is another view.
3. Keep the TTS audio graph alive across detach: do NOT close jTTS.ws or the AudioContext on view switch; let scheduled sources finish (the jarvisState.audioContext + jTTS singletons already persist — just stop tearing them down). Audio keeps playing when a browser tab is backgrounded; only the RAF avatar animation freezes (acceptable/cosmetic).
4. On RETURN to the JARVIS view (renderJarvisView / render() jarvis branch ~333/551 — verify): re-mount the avatar, then re-render the feed from jarvisState.messages so the user sees the streamed/finished reply; still-streaming deltas paint live again; if jarvisState.audioContext is suspended, resume() it.
5. Do NOT regress: explicit Stop still hard-stops; a new turn still cancels the previous; barge-in still works within the JARVIS view.
IMPLEMENT (server, app/server.py — jarvis_chat_stream ~1954, event_generator ~2200):
6. REMOVE the `if await request.is_disconnected(): return` early-return kill (~2208) — it was Batch 2's token-saver but proactively aborts the Hermes run on a transient disconnect (the bug's root). Keep the terminal `event: done / [DONE]` on normal completion and the finally-block cleanup.

=== FIX 2 — F103: hide admin-only Agentic panels for non-admin members ===
Batch 6 admin-gated /api/verify/runs, /api/watchdog/status, /api/scheduler (list), agent memory/context, agent messages → members (e.g. ariana) get 403 and the Agentic view (viewAgentic()/bindAgentic ~551) shows errors on those panels. Owner (admin) unaffected.
IMPLEMENT: get the current user's admin status client-side (modelState.isAdmin ~2092, or /api/auth/state ~137 — verify which is reliable at agentic-render time; stash is_admin on a shared state field at auth/state load if needed). In viewAgentic(), for NON-admin users HIDE the admin-only panels (watchdog status, scheduler, verify runs, admin agent memory/messages) — render nothing or a small "Admin only" note — and SKIP their fetches in the agentic load path (~381-391) so members don't fire 403s. Approval gates + cost summary that members ARE allowed to see stay visible.

HARD RULES:
- Bump ?v=N for app.js (and any other edited static file) in app/static/index.html. No unrelated refactors. Preserve all existing JARVIS behavior except the bug.
- Do NOT edit .venv, workspaces/, nexus.db, setup/, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff + a one-line summary per numbered item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(jarvis): keep the turn streaming + speaking across view switches (Option C); hide admin-only Agentic panels for members (F103)`
**Smoke test (after restart):** in the browser, send JARVIS a multi-sentence reply, switch to Kanban mid-reply, wait, switch back — the reply should have kept streaming + speaking and be shown in full (no "[stopped]"). Then log in as the member (ariana) and open Agentic — no 403 errors, admin-only panels hidden. Plus: `.venv/bin/python scripts/verify_jarvis_e2e.py` (6 checks) still passes.
**Scope note (deliberately OUT of this batch):** removing `is_disconnected` fully fixes the *in-app view switch* (the dominant, certain cause). A genuine browser-tab-CLOSE could still let Starlette cancel the generator; bulletproofing that needs a bigger "Hermes turn in a background task decoupled from the response" change — out of scope here (diminishing returns; you're not listening after closing the tab). Revisit only if needed.

### FIX — JARVIS "can't see the camera" = VRAM exhaustion (ties to GPU)
Live test: webcam frames index fine, but the chat turn's describe (`describe_image` → qwen3-vl, ~6-7 GB) can't run because only ~3 GB VRAM is free (WisprFlow 3.3 GB + faster-whisper STT 2 GB + mem0's `llama3.1:8b` 4.9 GB + SigLIP worker fill the 12 GB card). No describe → no `[JARVIS EYES]` → JARVIS correctly says "I can't see." The vision-VLM eviction itself works (qwen3-vl not camping); the card is just full of other things. **Fixed by Batch 5 (GPU discipline: serialize + evict promptly so the VLM has room) + reducing the resident footprint** (see the feature below). "Worked before" = the card had headroom then.

### FIX — Batch 9 (THE LAST FIX, after Batch 8): edit-camera-frame edits the WRONG frame
Confirmed live (2026-07-09): describe works (JARVIS correctly saw a Red Bull can), but asking him to **edit** it ("isolate the can, send a picture") produced an image with **no can** — he edited a *different* frame than the one he described.
**Root cause — seeing and editing use different frames.** Describe uses the frame carried in the chat request (`frame_b64` → `vision.describe_image`, also ingested to the frames dir). The `jarvis-edit-camera-frame` skill independently grabs **`max(glob(frames/*.jpg), key=mtime)`** — the NEWEST on-disk frame. But the webcam streams a new frame every ~3-4 s while shared (`/vision/frame?kind=webcam` POSTs), so by edit time the newest frame is a LATER capture (can moved/gone), not the described one. Evidence: wrong output `redbull_can_transparent.png` @20:55 vs frames dir accumulating past 21:03.
**Fix:** pin the described frame. When `describe_image` runs on the turn's `frame_b64`, save THOSE exact bytes to a stable per-user pin file, and make the edit skill operate on the pin, not `max(mtime)`. Then "edit what you just saw" is deterministic and matches the describe. **This is the LAST fix, after Batch 8, before the Batch 10 feature.**
Low-priority side-notes (NOT this fix): the recurring `ClientConnectionResetError` = the tab-switch issue (Batch 8); the intermittent `mem0.memory.main: Error parsing extraction response` = the memory LLM emitting malformed JSON (that turn's memory isn't saved; not a Nexus code bug — recon S4).

Code anchors (verified 2026-07-09): `jarvis_chat_stream` in app/server.py — `frame_b64 = body.get("frame_b64")` (~2026), `raw = base64.b64decode(...)` (~2030), `frame_note = await _vision_mod.describe_image(raw, user_input)` (~2031), then `asyncio.create_task(_vision_mod.ingest_frame(uid, raw, kind, ...))` (~2032). `ingest_frame` is FIRE-AND-FORGET and DEDUPS near-identical frames (vision.py `DUP_COSINE 0.985`, ~189-200; saves `{int(ts*1000)}-{kind}.jpg` in `_frames_dir(uid)` = `workspaces/jarvis/<uid>/frames/`), so the described frame may never land on disk under a timestamp name — the pin must be written from the `raw` bytes in hand, NOT from ingest's output. The skill (`~/.hermes/skills/computer-use/jarvis-edit-camera-frame/SKILL.md`, live copy only — NOT vendored in setup/) currently selects `max(glob(...), key=os.path.getmtime)` (~line 27).

- **Model / effort:** `opus` / `high` (small surgical fix — Fable fine too)  ·  **Review pass:** YES  ·  **Frontend cache-bust:** no (no static file edited)

**Prompt:**
```
Read ~/Nexus-Agentic-Coding-Setup/FIX-RUNBOOK-2026-07-08.md section 9 (the "Batch 9" entry — root cause + code anchors live there; this is NOT in STABILITY-AUDIT). Also read app/CLAUDE.md's JARVIS vision notes. This is Batch 9, the LAST stability fix.

BUG (confirmed live): JARVIS describes the camera correctly (saw a Red Bull can), but when asked to EDIT it ("isolate the can, send a picture") he edits a DIFFERENT frame — the webcam streams a new frame every ~3-4s, so the edit skill's `max(mtime)` picks a LATER frame (can gone), not the one he described.

ROOT CAUSE: "seeing" uses the frame carried in the chat request (frame_b64 → vision.describe_image); the jarvis-edit-camera-frame skill independently grabs the NEWEST on-disk frame via max(getmtime). Two different frames.

FIX — pin the described frame so edit operates on exactly what was seen:
1. app/vision.py — add a helper e.g. `pin_looked_frame(user_id, jpeg)` that writes the given JPEG bytes to a STABLE per-user path: `_frames_dir(user_id) / ".last-looked.jpg"` (overwrite each look-turn). Return/expose that path. (Keep the frames-dir path logic in vision.py.) Use a temp-file + os.replace so a reader never sees a half-written pin. Do NOT gate it behind ingest_frame's dedup — write the pin unconditionally whenever a frame is described.
2. app/server.py jarvis_chat_stream (~2031): right AFTER `frame_note = await _vision_mod.describe_image(raw, user_input)` succeeds, call `_vision_mod.pin_looked_frame(uid, raw)` (guard it in try/except so a pin failure never breaks the turn). This uses the SAME `raw` bytes that were described — not ingest's possibly-deduped/renamed file. (Also cover the image-file describe path ~2081 if it represents "what JARVIS is looking at" — decide and note; the camera/screen frame_b64 path is the required one.)
3. The skill file (~/.hermes/skills/computer-use/jarvis-edit-camera-frame/SKILL.md — live copy, not in the repo): change the frame-selection instruction so it PREFERS the pin `workspaces/jarvis/<uid>/frames/.last-looked.jpg` if it exists (that is exactly the frame JARVIS last DESCRIBED), and only falls back to `max(glob(*-{webcam,screen}.jpg), key=getmtime)` if the pin is absent. IMPORTANT: exclude the `.last-looked.jpg` pin itself from the max(mtime) glob so the fallback can't just re-pick it under a wrong name, and update the "Where frames live" section to document the pin. Keep everything else in the skill unchanged.

HARD RULES:
- Change ONLY what the fix needs — no refactors. Preserve all other JARVIS behavior.
- App changes go in app/ (server.py, vision.py). The skill edit is the ONE deliberate exception (~/.hermes/skills/...) — it is a skill file, not a core-mod, and has no vendored copy in setup/. Do NOT touch anything else outside app/.
- Do NOT edit .venv, workspaces/, nexus.db, setup/.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED. Confirm vision.py imports cleanly under .venv.
- Show me the FULL diff of the app/ files AND the full new text of the changed skill section, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(jarvis): edit-camera-frame operates on the frame JARVIS actually described (pin last-looked frame, not newest-on-disk)`
**Note:** only the app/ files (server.py, vision.py) are committed to the repo; the skill edit is a live change under ~/.hermes/skills (no repo copy) — it takes effect immediately, no restart needed for the skill, but restart nexus for the server.py pin-write.
**Smoke test (after restart):** hold an object to the camera, tell JARVIS "look at my camera and describe it" (confirm he sees it), THEN "isolate just that object and send me the image" — the produced image must be the object he just described (not a later, empty frame). Also `.venv/bin/python scripts/verify_jarvis_v2_backend.py` (23 checks) still passes.

### FEATURE — Batch 10 (PARKED for a later session — NOT part of the stability work): one STT model for the whole machine
Goal: the standalone WisprFlow dictation tool and JARVIS's faster-whisper both load their own STT model → two whisper models in VRAM. **Consolidate so ONE STT model serves both** JARVIS voice-in AND system-wide dictation.

**Investigation (2026-07-09) — WisprFlow is more than a "simple tool":** a 991-line daemon (`~/local-wisprflow/wf_daemon.py`) + `wf_layout.py` + THREE systemd user services (`wf-daemon`, `wf-keylistener`, `wf-cleanup-llm`). It is *more* capable than Nexus voice.py: model **large-v3** (vs Nexus medium.en); **adaptive GPU↔CPU** (runs whisper on GPU when free, auto-falls to CPU/0-VRAM when a big LLM loads); an **LLM cleanup pass** (gemma3:4b on an ISOLATED ollama :11435) that punctuates/formats the raw transcript; **ydotool `type`** injection into the focused window (its working Wayland solution — note: ydotool is FINE here, it's the operator's own already-working dictation, distinct from the Hermes-cua "ydotool forbidden" rule which is about autonomous machine control); plus hotkey listener, energy-VAD auto-stop, and a meeting mode.

**Architecture — DECISION REVISED to OPTION B (operator, 2026-07-09), superseding the earlier "fully embed":** the earlier plan was to embed the daemon inside the Nexus service, but the investigation surfaced two problems — (a) Nexus restarts often (~10×/session), and embedding would make every Nexus restart KILL dictation mid-work; (b) it re-implements what WisprFlow already does well (adaptive VRAM, cleanup, Wayland injection). **OPTION B instead:** run ONE faster-whisper model (large-v3 — the better one) behind a small shared local STT endpoint; JARVIS voice-in (`voice.py`) calls it instead of loading its own model; **WisprFlow stays the resident daemon but calls the shared model instead of loading its own.** Result: one model in VRAM, both use it, dictation stays independent of Nexus restarts, and WisprFlow's adaptive-VRAM + cleanup + injection (all already working) are kept. Less code, less risk, same VRAM win.
- Sub-tasks when picked up: (1) stand up the shared STT endpoint (likely reuse Nexus's `/api/jarvis/stt` or a dedicated tiny service holding the one model); (2) point `voice.py` at it (drop the in-process faster-whisper load); (3) point WisprFlow's ASR at it (small change to `wf_daemon.py` — call the endpoint instead of loading large-v3 locally); (4) verify one model resident, both paths work, dictation survives a Nexus restart. Leave WisprFlow's files intact throughout.
- **This is a FEATURE, do it in a dedicated session — NOT part of the bugfix work.** (STT-to-CPU was rejected: too slow for responsive voice-in.)
