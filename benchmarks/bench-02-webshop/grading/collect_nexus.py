#!/usr/bin/env python3
"""Collect the Nexus arm of Bench-02 (wizard-created work may be a WORKFLOW).

Run with the Nexus venv:

    ~/nexus-agent-os/.venv/bin/python collect_nexus.py list
        -> shows the newest workflows and standalone tasks so you can spot
           the webshop run (the wizard names things itself).

    ~/nexus-agent-os/.venv/bin/python collect_nexus.py <wf-id|task-id> [dest]
        -> prints status/timing/cost ledger and copies every workspace to
           dest (default ~/benchmarks/bench-02/nexus).
"""
import json
import os
import shutil
import sqlite3
import sys

NEXUS = os.path.expanduser("~/nexus-agent-os")
sys.path.insert(0, NEXUS)
import database  # noqa: E402

WORKSPACES = os.path.join(NEXUS, "workspaces")


def connect():
    con = sqlite3.connect(os.path.join(NEXUS, "nexus.db"))
    con.row_factory = sqlite3.Row
    return con


def list_recent(con):
    print("--- newest workflows ---")
    for r in con.execute(
            "SELECT id, name, status, datetime(created_at,'unixepoch','localtime') AS c "
            "FROM workflows ORDER BY created_at DESC LIMIT 6"):
        n = con.execute("SELECT COUNT(*) FROM tasks WHERE workflow_id=?", (r["id"],)).fetchone()[0]
        print(f"  {r['id']}  [{r['status']}] {n} tasks  {r['c']}  {r['name'][:70]}")
    print("--- newest standalone tasks (no workflow) ---")
    for r in con.execute(
            "SELECT id, title, status, datetime(created_at,'unixepoch','localtime') AS c "
            "FROM tasks WHERE workflow_id IS NULL ORDER BY created_at DESC LIMIT 6"):
        print(f"  {r['id']}  [{r['status']}]  {r['c']}  {r['title'][:70]}")


def copy_ws(src, dest_sub):
    if src and os.path.isdir(src):
        shutil.copytree(src, dest_sub, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules",
                                                      ".venv", "venv", ".git"))
        print(f"copied {src} -> {dest_sub}")
    else:
        print(f"  (no workspace dir at {src!r})")


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    con = connect()
    if sys.argv[1] == "list":
        list_recent(con)
        return
    ident = sys.argv[1]
    dest = os.path.expanduser(sys.argv[2] if len(sys.argv) > 2 else "~/benchmarks/bench-02/nexus")
    os.makedirs(dest, exist_ok=True)

    if ident.startswith("wf-"):
        wf = con.execute("SELECT * FROM workflows WHERE id=?", (ident,)).fetchone()
        if not wf:
            print(f"no workflow {ident}")
            sys.exit(1)
        tasks = con.execute(
            "SELECT id, title, status, model, workspace_path, created_at, completed_at "
            "FROM tasks WHERE workflow_id=? ORDER BY created_at", (ident,)).fetchall()
        print(f"--- workflow {ident}: {wf['name']} [{wf['status']}] ---")
        t0 = min((t["created_at"] for t in tasks if t["created_at"]), default=None)
        t1 = max((t["completed_at"] for t in tasks if t["completed_at"]), default=None)
        if t0 and t1:
            print(f"wall-clock (first task created -> last completed): {(t1 - t0) / 60:.1f} min")
        for t in tasks:
            print(f"  {t['id']} [{t['status']}] {t['title'][:60]}")
            copy_ws(t["workspace_path"], os.path.join(dest, t["id"]))
        copy_ws(os.path.join(WORKSPACES, f"workflow-{ident}"), os.path.join(dest, f"workflow-{ident}"))
        print("--- workflow cost ledger (API-equivalent USD) ---")
        print(json.dumps(database.workflow_cost_ledger(ident), indent=2))
    else:
        t = con.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone()
        if not t:
            print(f"no task {ident}")
            sys.exit(1)
        t = dict(t)
        print(json.dumps({k: t.get(k) for k in
                          ("id", "title", "status", "workspace_path", "created_at",
                           "completed_at", "model")}, indent=2, default=str))
        copy_ws(t.get("workspace_path"), dest)
        print("--- task cost ledger (API-equivalent USD) ---")
        print(json.dumps(database.task_cost_ledger(ident), indent=2))


if __name__ == "__main__":
    main()
