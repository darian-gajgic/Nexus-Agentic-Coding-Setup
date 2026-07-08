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
| Dispatch: empty-reply→QuotaError stalls the whole fleet; slot cap on wrong model; resume drops the task brief | Audit re-hunt | **189/454 executor-resumes; 30 overload events** | **B4** |
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
| Watchdog: no restart circuit-breaker; "stuck" removes lane from monitoring | F073/F074 | **B6** |
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

---

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
Read ~/Nexus-Agentic-Coding-Setup/STABILITY-AUDIT-2026-07-08.md section 3.7, section 4, and the "Dispatch engine & JARVIS brain (deep re-hunt)" section. This is real-money, concurrency-sensitive code — be careful and precise.

Fix in app/hermes_dispatch.py:
1. slots_in_use() (~line 227): count live dispatches by the EFFECTIVE run-model the session actually uses (resolved/fallback model), not the raw tasks.model column — otherwise the per-model concurrency cap is applied to the wrong pool and can cause more 429s.
2. Resume path (~line 1034): when a worker died before a session was really established, send the FULL brief (title + description) instead of the bare "continue" stub. Only send "continue" when there is genuine prior session/transcript context.
3. _finalize_result (~line 796): an empty/short reply with no deliverable.md must NOT be blanket-raised as QuotaError. In repo mode, a non-empty changes.diff = success. Only raise QuotaError on an actual rate-limit signature.
4. on_event telemetry (~line 746): wrap the streaming db.execute telemetry writes in try/except so a transient SQLite error can't abort the stream.
5. Add structured logging capturing WHY a worker dies (CUDA OOM / Hermes timeout / QuotaError / other) so "executor died" isn't the only signal.

Fix in app/jarvis_brain.py:
6. Move the ~/knowledge file reads off the event loop (run_in_threadpool), and honor the per-user knowledge overlay (users/<uid>/...) instead of always the owner's canonical files.

HARD RULES:
- No behavior change beyond these fixes. Do not alter the budget/quota policy numbers.
- Do NOT edit .venv, workspaces/, .worktrees/, nexus.db, setup/, or anything outside app/ source.
- Run: cd ~/Nexus-Agentic-Coding-Setup/app && bash scripts/verify.sh — must print ALL CHECKS PASSED.
- Show me the FULL diff + one-line summary per item, then STOP. Do not commit until I say "commit".
```
**Commit message:** `fix(dispatch): correct slot accounting, resume brief, quota misclassification + why-died logging`
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
- F073/F074 (app/watchdog.py ~120/~144): add a restart circuit-breaker (backoff + max-restarts→retire); stop removing "stuck" lanes from monitoring — heal or retire them explicitly.
- F118 (~5735): fix the memory3d node "user" attribute reading the wrong payload key.
- F004 (app/scheduler.py ~100) — DECISION NEEDED: right now a scheduled job only writes a label + logs; it never runs. Change _trigger so a fired job actually creates+enqueues a task (so scheduled jobs do real work). If you believe it should stay notify-only, DO NOT change it — tell me and STOP for that item.
- F010/F036 (~1610-1663): serialize the per-user jarvis_session.json read-modify-write (a lock or atomic replace) so concurrent turns don't lose messages.

Frontend (app/static/):
- F021 (app.js ~4519): the POST body sets workflow_id twice — delete the duplicate key so a task created in a focused project keeps its project.
- F024 (memory3d.js ~223): guard the no-similarity-links case so the galaxy doesn't render blank.
- F132 (app.js ~6635): in jarvisStreamChat, check res.ok/status and surface the real error instead of always "provider overloaded".
- F022 (app.js ~1254): re-set the drag handlers (dragId) after the kanban search re-render.
- F129 (app.js ~1108): re-render the project filter after loadWorkflows() on first kanban visit.

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
   - Mark lipsync.py + the /api/jarvis/talk and /api/jarvis/lipsync endpoints clearly as RETIRED (comment), and remove the dead _tool_glm / _tool_supermemory scanners from tools_hub.py.
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
git add -A && git commit -m "chore: remove stale probe worktree + move db backups out of the tree" || true
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
