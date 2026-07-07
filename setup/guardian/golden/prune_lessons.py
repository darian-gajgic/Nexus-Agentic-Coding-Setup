#!/usr/bin/env python3
"""Prune stale specialist lessons — soft-archive the old + never-retrieved ones.

Bulletproof by design: NOTHING is deleted. A lesson older than ARCHIVE_AGE_DAYS
that has never been retrieved (per the usage log the mem0 provider writes) is
ARCHIVED — its qdrant agent_id is moved to '<role>__archived', so it leaves
active retrieval but is fully preserved and one-click restorable from the nexus
Specialists tab. This bounds long-term growth and retires dead weight without
ever losing a lesson. Runs on the hermes-prune.timer. Fail-soft throughout.

Test override: PRUNE_AGE_DAYS=0 archives all unused lessons regardless of age.
"""
import os
import re
import json
import datetime
import urllib.request
from pathlib import Path

AGENTS = Path(os.path.expanduser("~/.hermes/agents"))
USAGE_LOG = AGENTS / ".lesson_usage.jsonl"
USAGE_STATE = AGENTS / ".lesson_usage_state.json"
ARCHIVE_AGE_DAYS = int(os.environ.get("PRUNE_AGE_DAYS", "60"))
ARCHIVE_SUFFIX = "__archived"


def _cfg():
    try:
        return json.loads(open(os.path.expanduser("~/.hermes/mem0.json")).read())
    except Exception:
        return {}


def _qurl():
    return (_cfg().get("oss", {}).get("vector_store", {}).get("config", {}) or {}).get("url", "http://localhost:6333")


def _user():
    return _cfg().get("user_id", "hermes-user")


def _post(path, body):
    req = urllib.request.Request(f"{_qurl()}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=12).read())


def _fold_usage():
    """Merge the raw usage log into the aggregate state. The log is RENAMED
    before reading — usage events appended by the mem0 provider while we fold
    land in a fresh file instead of being wiped by a read-then-truncate.
    Returns {lesson_id: {count, last_used}}."""
    state = {}
    try:
        state = json.loads(USAGE_STATE.read_text()) if USAGE_STATE.exists() else {}
    except Exception:
        state = {}
    folding = USAGE_LOG.with_suffix(".folding")
    # A leftover .folding (crash between fold and unlink) is processed as-is
    # this run — renaming over it would silently drop that batch. The live
    # log then simply waits for the next run.
    if not folding.exists() and USAGE_LOG.exists():
        try:
            USAGE_LOG.rename(folding)
        except Exception:
            return state
    if folding.exists():
        try:
            for line in folding.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                ts = e.get("ts")
                for i in e.get("ids", []):
                    s = state.setdefault(i, {"count": 0, "last_used": None})
                    s["count"] += 1
                    if ts and (not s["last_used"] or ts > s["last_used"]):
                        s["last_used"] = ts
            USAGE_STATE.write_text(json.dumps(state))
            folding.unlink()  # folded into state — remove the renamed batch
        except Exception:
            pass
    return state


def _specialist_ids():
    ids = []
    if not AGENTS.is_dir():
        return ids
    for f in AGENTS.glob("*.md"):
        try:
            txt = f.read_text()
            m = re.search(r"^mem0_agent_id:\s*(.+)$", txt, re.M)
            n = re.search(r"^name:\s*(.+)$", txt, re.M)
            ids.append((m.group(1) if m else (n.group(1) if n else f.stem)).strip())
        except Exception:
            pass
    return ids


def _lessons(agent_id):
    try:
        pts = (_post("/collections/mem0/points/scroll", {
            "limit": 1000, "with_payload": True,
            "filter": {"must": [{"key": "user_id", "match": {"value": _user()}},
                                {"key": "agent_id", "match": {"value": agent_id}}]}}).get("result") or {}).get("points", [])
        return [{"id": p.get("id"), "created_at": (p.get("payload") or {}).get("created_at")} for p in pts]
    except Exception:
        return []


def _archive(point_id, agent_id):
    try:
        _post("/collections/mem0/points/payload",
              {"payload": {"agent_id": agent_id + ARCHIVE_SUFFIX}, "points": [point_id]})
        return True
    except Exception:
        return False


def main():
    usage = _fold_usage()
    now = datetime.datetime.now(datetime.timezone.utc)
    archived = []
    for aid in _specialist_ids():
        for L in _lessons(aid):
            retrieved = usage.get(L["id"], {}).get("count", 0) > 0
            ca = L.get("created_at")
            try:
                age = (now - datetime.datetime.fromisoformat(ca.replace("Z", "+00:00"))).days if ca else 999
            except Exception:
                age = 999
            if (not retrieved) and age >= ARCHIVE_AGE_DAYS:
                if _archive(L["id"], aid):
                    archived.append((aid, L["id"], age))
    print(f"prune: archived {len(archived)} stale (old + never-retrieved) lesson(s); they are recoverable in nexus")
    for aid, lid, age in archived:
        print(f"  - {aid} {lid[:8]} ({age}d, 0 retrievals)")


if __name__ == "__main__":
    main()
