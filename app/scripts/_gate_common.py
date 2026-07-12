"""Shared bootstrap helpers for the runtime verify gates.

Keep this tiny: gates import it straight off scripts/ (sys.path[0] when a gate
runs, the same mechanism _gate_auth relies on).
"""
import os


def load_env():
    """~/.hermes/.env then ./.env (relative to CWD — call AFTER any chdir).
    setdefault only, never overrides the live environment. Same loader as
    worker.py — hermes_dispatch.create_session needs API_SERVER_KEY."""
    for p in [os.path.expanduser("~/.hermes/.env"), ".env"]:
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def preclean_probe_user(db, auth, username: str):
    """Idempotent pre-clean of a fixed-name probe user. A gate run that died
    before its `finally` leaves the row behind; auth.create_user then returns
    'username already exists' and the assert hard-locks the gate until someone
    deletes the row by hand — while a live probe admin/member sits in the auth
    table. Mirrors the gates' finally-block deletes, up front."""
    for stale in db.query_all("SELECT id FROM users WHERE username=?", (username,)):
        db.execute("DELETE FROM auth_sessions WHERE user_id=?", (stale["id"],))
        db.execute("DELETE FROM activity WHERE user_id=?", (stale["id"],))
        db.execute("DELETE FROM tasks WHERE user_id=?", (stale["id"],))
        db.execute("DELETE FROM users WHERE id=?", (stale["id"],))
    auth.invalidate_auth_cache()
