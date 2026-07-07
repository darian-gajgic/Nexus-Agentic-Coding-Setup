#!/usr/bin/env python3
"""EMERGENCY auth reset — local machine access only.

If you ever lock yourself out (forgotten passwords, a probe crashed mid-run,
…), run this ON the machine:

    .venv/bin/python scripts/auth_reset.py            # back to single-user
    .venv/bin/python scripts/auth_reset.py --keep-users  # keep users, clear pw

Default action: delete every user except the default owner, clear the owner's
password, drop all login sessions → the instance is single-user again (no
login asked). Physical/local access to nexus.db is the trust boundary here,
exactly like any other sqlite-backed local app.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import database as db  # noqa: E402


def main():
    keep_users = "--keep-users" in sys.argv
    if keep_users:
        n = db.execute("UPDATE users SET password_hash=''").rowcount
        print(f"cleared passwords for {n} user(s)")
    else:
        n = db.execute("DELETE FROM users WHERE id != 'u_owner'").rowcount
        db.execute("UPDATE users SET password_hash='' WHERE id='u_owner'")
        print(f"deleted {n} non-owner user(s); owner password cleared")
    db.execute("DELETE FROM auth_sessions")
    db.log_activity("warn", "auth", "auth_reset.py executed (local emergency reset)")
    print("all login sessions dropped — the UI is single-user again "
          "(auth cache refreshes within ~2s; no restart needed)")


if __name__ == "__main__":
    main()
