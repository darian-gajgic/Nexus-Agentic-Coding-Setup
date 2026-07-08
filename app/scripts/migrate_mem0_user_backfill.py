#!/usr/bin/env python3
"""One-time Block-1 backfill: hand the LEGACY (untagged) mem0 memories to the
owner user — the memory-side mirror of the tasks/workflows u_owner backfill.

WHY: the galaxy / /api/memory rule is "untagged = shared/global", so the
pre-multi-user backlog (memories extracted before Block 1 existed — all of
them the operator's) was visible to EVERY user. Tagging them user=u_owner
makes a new user's memory view start empty. New memories already tag
correctly via the mem0-client provider + session scopes.

Also writes "default_user": <owner> into ~/.hermes/client-scopes.json so
UNMAPPED Hermes sessions (the operator's local CLI — Nexus publishes a scope
for every session it creates) keep reading these now-owner-tagged rows via
the mem0-client fallback instead of losing them all.

Run:   .venv/bin/python scripts/migrate_mem0_user_backfill.py [--dry-run]
Undo:  .venv/bin/python scripts/migrate_mem0_user_backfill.py --undo logs/mem0-user-backfill-<ts>.json

Idempotent: a second run finds 0 untagged points and changes nothing.
"""
import argparse
import json
import os
import sys
import time
import urllib.request

QDRANT = os.environ.get("MEM0_QDRANT_URL", "http://localhost:6333")
COLL = "mem0"
SCOPES_FILE = os.path.expanduser("~/.hermes/client-scopes.json")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
UNTAGGED = {"must": [{"is_empty": {"key": "user"}}]}


def _req(path: str, body: dict | None = None):
    req = urllib.request.Request(
        f"{QDRANT}/collections/{COLL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["result"]


def count(flt: dict | None = None) -> int:
    return _req("/points/count", {"exact": True, **({"filter": flt} if flt else {})})["count"]


def scroll_untagged_ids() -> list:
    ids, offset = [], None
    while True:
        body = {"limit": 256, "with_payload": False, "with_vector": False,
                "filter": UNTAGGED}
        if offset:
            body["offset"] = offset
        res = _req("/points/scroll", body)
        ids += [p["id"] for p in res["points"]]
        offset = res.get("next_page_offset")
        if not offset:
            return ids


def set_default_user(owner: str | None):
    """Write (or remove, owner=None) the scopes-file fallback for unmapped
    sessions; publish_session_scope preserves this key on rewrite."""
    data = {}
    if os.path.isfile(SCOPES_FILE):
        with open(SCOPES_FILE) as f:
            data = json.load(f)
    if owner:
        data["default_user"] = owner
    else:
        data.pop("default_user", None)
    with open(SCOPES_FILE, "w") as f:
        json.dump(data, f, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--owner", default="u_owner", help="nexus user id to assign (default u_owner)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    ap.add_argument("--undo", metavar="FILE", help="revert a previous run from its log file")
    args = ap.parse_args()

    total = count()
    if args.undo:
        rec = json.load(open(args.undo))
        ids = rec["migrated_ids"]
        print(f"UNDO: removing the 'user' tag from {len(ids)} points ({args.undo})")
        for i in range(0, len(ids), 256):
            # ?wait=true: apply synchronously so the count below is accurate
            _req("/points/payload/delete?wait=true", {"keys": ["user"], "points": ids[i:i + 256]})
        set_default_user(None)
        print(f"done — untagged now: {count(UNTAGGED)} / {total}; default_user removed")
        return

    untagged = count(UNTAGGED)
    print(f"qdrant {QDRANT} · collection '{COLL}': {total} points, "
          f"{untagged} untagged (legacy), {total - untagged} already user-tagged")
    if untagged == 0:
        print("nothing to migrate — already backfilled")
        return
    ids = scroll_untagged_ids()
    if len(ids) != untagged:
        sys.exit(f"ABORT: scroll found {len(ids)} untagged ids but count says {untagged}")
    if args.dry_run:
        print(f"DRY RUN: would tag {len(ids)} points user={args.owner!r}, "
              f"write undo log, and set default_user in {SCOPES_FILE}")
        return

    os.makedirs(LOG_DIR, exist_ok=True)
    undo_file = os.path.join(LOG_DIR, f"mem0-user-backfill-{time.strftime('%Y%m%d_%H%M%S')}.json")
    with open(undo_file, "w") as f:
        json.dump({"owner": args.owner, "collection": COLL, "ts": time.time(),
                   "migrated_ids": ids}, f)
    print(f"undo log: {undo_file}")

    for i in range(0, len(ids), 256):
        # ?wait=true: apply synchronously so the count below is accurate
        _req("/points/payload?wait=true", {"payload": {"user": args.owner}, "points": ids[i:i + 256]})
    left = count(UNTAGGED)
    print(f"tagged {len(ids)} points user={args.owner!r} — untagged now: {left}")
    set_default_user(args.owner)
    print(f"default_user={args.owner!r} written to {SCOPES_FILE}")
    if left != 0:
        sys.exit("WARNING: untagged points remain (added mid-run?) — rerun to catch them")


if __name__ == "__main__":
    main()
