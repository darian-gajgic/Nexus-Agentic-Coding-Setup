#!/usr/bin/env python3
"""One-time migration to the real-agents world (SPEC-REAL-AGENTS.md §4).

What it does — everything reported, NOTHING deleted without an archive copy:
  1. Snapshot backup: nexus.db.bak-migration-<ts>
  2. Archive sim-era activity + metrics rows to nexus_archive_<date>.db, then delete
  3. Retire the SelfHealTest zombie (terminal 'retired' status — watchdog-proof)
  4. Delete the 7 seeded demo agents (fake tokens, no real process) — archived first
  5. Delete the 12 seeded demo kanban tasks — archived first
  6. Flip settings dispatch.enabled -> 1 (real dispatch becomes the default)

Run with the server STOPPED or running (WAL handles it), from the repo root:
    .venv/bin/python scripts/migrate_real_agents.py
Idempotent: re-running skips what's already done.
"""
import shutil
import sqlite3
import time
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "nexus.db"

SEED_AGENTS = ["agent-alpha", "agent-beta", "agent-gamma", "agent-delta",
               "agent-epsilon", "agent-zeta", "agent-eta"]
SEED_TASKS = [f"task-{n:03d}" for n in range(1, 13)]
ZOMBIE = "agent-9693f66f"  # SelfHealTest


def main():
    assert DB.exists(), f"{DB} not found — run from the repo"
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / f"nexus.db.bak-migration-{stamp}"
    shutil.copy2(DB, bak)
    print(f"[1] backup: {bak.name}")

    conn = sqlite3.connect(str(DB), timeout=15)
    conn.row_factory = sqlite3.Row
    arch_path = ROOT / f"nexus_archive_{stamp}.db"
    arch = sqlite3.connect(str(arch_path))

    # 2. archive + purge sim-era activity/metrics (real events resume from here)
    for table, ddl in [
        ("activity", "CREATE TABLE IF NOT EXISTS activity (id INTEGER, ts REAL, level TEXT, source TEXT, message TEXT)"),
        ("metrics", "CREATE TABLE IF NOT EXISTS metrics (id INTEGER, agent_id TEXT, ts REAL, cpu REAL, memory_mb REAL, tasks_per_min REAL)"),
    ]:
        arch.execute(ddl)
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        if rows:
            cols = rows[0].keys()
            arch.executemany(
                f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                [tuple(r) for r in rows])
        conn.execute(f"DELETE FROM {table}")
        print(f"[2] archived + purged {len(rows)} {table} rows")

    # 3. retire the zombie properly (terminal lifecycle state)
    z = conn.execute("SELECT id, name, status, restart_count FROM agents WHERE id=?",
                     (ZOMBIE,)).fetchone()
    if z:
        conn.execute("UPDATE agents SET status='retired', pid=NULL, current_task='' WHERE id=?",
                     (ZOMBIE,))
        print(f"[3] retired zombie {z['name']} ({ZOMBIE}) — was '{z['status']}', "
              f"restart_count={z['restart_count']} (kept as history)")
    else:
        print(f"[3] zombie {ZOMBIE} not present (ok)")

    # 4+5. archive + delete seeded demo agents/tasks
    arch.execute("CREATE TABLE IF NOT EXISTS seed_agents_json (id TEXT, row_json TEXT)")
    arch.execute("CREATE TABLE IF NOT EXISTS seed_tasks_json (id TEXT, row_json TEXT)")
    import json as _json
    gone_a, gone_t = [], []
    for aid in SEED_AGENTS:
        r = conn.execute("SELECT * FROM agents WHERE id=? AND pid IS NULL", (aid,)).fetchone()
        if r:
            arch.execute("INSERT INTO seed_agents_json VALUES (?,?)",
                         (aid, _json.dumps(dict(r))))
            conn.execute("DELETE FROM agents WHERE id=?", (aid,))
            gone_a.append(aid)
    for tid in SEED_TASKS:
        r = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
        if r:
            arch.execute("INSERT INTO seed_tasks_json VALUES (?,?)",
                         (tid, _json.dumps(dict(r))))
            conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
            gone_t.append(tid)
    print(f"[4] deleted {len(gone_a)} seed demo agents (archived): {', '.join(gone_a) or '—'}")
    print(f"[5] deleted {len(gone_t)} seed demo tasks (archived): {', '.join(gone_t) or '—'}")

    # 6. real dispatch becomes the default
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('dispatch.enabled', '1')")
    print("[6] dispatch.enabled = 1 (real dispatch ON)")

    conn.execute(
        "INSERT INTO activity (ts, level, source, message) VALUES (?,?,?,?)",
        (time.time(), "info", "system",
         f"Migration to real agents complete: sim data archived to {arch_path.name}"))
    conn.commit()
    arch.commit()
    arch.close()
    conn.close()
    print(f"\nDONE. Archive: {arch_path.name} | Backup: {bak.name}")
    print("Note: seeded demo PROGRAMS were intentionally kept (harmless catalog rows,")
    print("referenced nowhere critical) — delete via the UI if you want them gone.")


if __name__ == "__main__":
    main()
