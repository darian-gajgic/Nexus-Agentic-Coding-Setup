#!/usr/bin/env python3
"""Collect the Nexus arm of Bench-01: find the newest 'Bench-01*' task, print
its status/timing, copy its workspace to ~/benchmarks/bench-01/nexus, and
print the C3 cost ledger (API-equivalent USD).

Run with the Nexus venv (database import needs it):

    ~/nexus-agent-os/.venv/bin/python collect_nexus.py
"""
import json
import os
import shutil
import sqlite3
import sys

NEXUS = os.path.expanduser("~/nexus-agent-os")
DEST = os.path.expanduser("~/benchmarks/bench-01/nexus")
sys.path.insert(0, NEXUS)
import database  # noqa: E402  (resolves nexus.db relative to its own file)

con = sqlite3.connect(os.path.join(NEXUS, "nexus.db"))
con.row_factory = sqlite3.Row
row = con.execute(
    "SELECT * FROM tasks WHERE title LIKE 'Bench-01%' "
    "ORDER BY created_at DESC LIMIT 1").fetchone()
if row is None:
    print("No task with title 'Bench-01*' found — create it in the dashboard first.")
    sys.exit(1)

t = dict(row)
info = {k: t.get(k) for k in
        ("id", "title", "status", "workspace_path", "created_at", "completed_at",
         "model", "critic_verdict", "critic_round", "super_result")
        if k in t}
print("--- task ---")
print(json.dumps(info, indent=2, default=str))

ws = t.get("workspace_path")
if ws and os.path.isdir(ws):
    os.makedirs(DEST, exist_ok=True)
    shutil.copytree(ws, DEST, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    print(f"copied {ws} -> {DEST}")
else:
    print(f"WARNING workspace_path missing or not a directory: {ws!r}")

print("--- cost ledger (API-equivalent USD) ---")
print(json.dumps(database.task_cost_ledger(t["id"]), indent=2))
