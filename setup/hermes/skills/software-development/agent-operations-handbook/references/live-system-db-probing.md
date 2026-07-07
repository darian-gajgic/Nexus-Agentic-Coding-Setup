# Probing a Live System's Database

Diagnostic techniques for health-probing a live multi-agent / dispatched-session
system by reading its own SQLite database — whether you are outside the system
(curl/terminal) or inside it (you ARE a dispatched agent and must prove that).

## 1. Prove liveness from inside a dispatched session — the 3-signal method

When you are a dispatched agent executing inside a live system and the task is
an E2E / health probe, you must prove "I AM this specific dispatch" — not just
assert it. Use three independent signals; one could be stale, two is strong,
three (especially #3) is definitive:

1. **The dispatch/session row** — `state` is active (`streaming` / `running`),
   `ended_at` is NULL, `error` is NULL, and `heartbeat_at` is advancing (age
   <2s). This proves the dispatch exists and is live, but not that it is YOU.
2. **The activity / audit log** — your tool calls are recorded under the
   dispatch id / agent id / task id, with timestamps advancing in lockstep
   with your real execution (e.g. `[task-X] tool terminal done`,
   `tool write_file done`). This ties the dispatch to your tool-call sequence.
3. **The agent's `current_task` / working-buffer field** — this echoes your
   live LLM stream text. At capture it will contain a verbatim fragment of
   the prose you are actively composing THIS turn. This is impossible to fake
   or stale-cache — it is the session's own working buffer, populated only by
   what you are generating right now. This is the smoking gun.

Quote the captured fragment directly in the deliverable as evidence.

## 2. SQLite WAL read/write race — don't conclude "missing" from one empty SELECT

When a worker process holds the database write lock (e.g. during an active SSE
stream / dispatch), a concurrent reader on a SEPARATE connection may see stale
or EMPTY rows — even rows that demonstrably exist in other tables.

**Symptom:** `SELECT * FROM tasks WHERE id = 'task-XXXX'` returns 0 rows while
the dispatches table, activity log, and agent `current_task` all confirm the
task is live and claimed. This is NOT data loss and NOT a missing task — it is
a WAL read/write race. The `tasks` row is updated atomically by the worker when
the dispatch finalizes (commits).

**Rule:** never conclude "task is missing" or "task doesn't exist" from a
single empty SELECT issued during active writes. Cross-reference the
dispatches table, the activity log, and agent state. If those agree the task
is live, the empty `tasks` read is the race, not the truth. Note it in the
deliverable as expected behavior so the next probe doesn't re-investigate it.

(Origin: Nexus Agent OS "agentic e2e probe" tasks — the `tasks` row is
invisible for the entire duration of the streaming dispatch and only appears
at finalize. Two consecutive probes hit this; both initially read it as a
potential data-loss bug before confirming the WAL race.)

## 3. PRAGMA table_info FIRST — never guess column names

When probing an unfamiliar SQLite database, run `PRAGMA table_info(table)` to
get the real column names BEFORE writing SELECTs. Also enumerate tables first:

```sql
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
```

Guessing column names burns iterations — schemas drift across versions and the
naming convention is not predictable (`assigned_to` vs `assignee_id`,
`heartbeat` vs `heartbeat_at` vs `last_heartbeat`, `dispatch_config` table that
doesn't exist vs a `settings` key-value table). Write the PRAGMA result, then
build SELECTs from the confirmed columns. Use `SELECT *` on a single row when
exploring so you see the actual data alongside the column names.

Write probe scripts to a `.py` file and execute the file (see SKILL.md Section
10 — inline `-c` / `-e` flags are blocked by the terminal scanner). Make probe
scripts resilient: build column lists dynamically, and wrap optional-column
queries in try/except so one wrong name doesn't abort the whole probe.

## 4. Canonical gates are the primary evidence

For a health probe, the system's own test / verify gates are the strongest
evidence — they exercise the real contract end-to-end. Run them and report
exact pass/fail counts (e.g. "30/30 API checks", "107/107 static checks").
Supplement with live-state reads (dispatch rows, activity logs, heartbeat
ages, config / quota settings) for the "is it alive right now" leg. A probe
deliverable should have BOTH legs: the gate results (contract integrity) and
the live-state evidence (runtime liveness).

## 5. Scan the recent-dispatches ledger for fault signatures

Before declaring a system fully healthy, scan the recent dispatches (last
10-15) for `state=failed` rows and read their `error` strings. A system can
pass all gates and stream live while an intermittent finalize-path fault
silently marks completed-work dispatches as `failed`. Correlate the error
signature (e.g. `'NoneType' object has no attribute 'get'`) against the code
path (finalize / post-stream bookkeeping vs the happy path). If the deliverable
was written but the dispatch landed `failed`, the fault is in finalization,
not execution — flag it for hardening even though it doesn't block the current
probe.
