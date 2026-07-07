#!/usr/bin/env python3
"""One-off migration: recreate the 'mem0' Qdrant collection with the v3 hybrid-search
schema (bm25 sparse slot) and re-import all existing memories.

Safety: exports every point to JSON AND takes a Qdrant server-side snapshot before
deleting anything. Restore path if something goes wrong:
  POST http://localhost:6333/collections/mem0/snapshots/{snap}/recover
Run with the hermes venv python while the gateway is STOPPED.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

QDRANT = "http://localhost:6333"
COLL = "mem0"
BACKUP_DIR = Path.home() / ".hermes" / "mem0-migration-20260706"

MEM0_CFG = {  # mirrors ~/.hermes/mem0.json (oss section)
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.1:8b",
            "ollama_base_url": "http://localhost:11434",
            "temperature": 0.1,
            "max_tokens": 2000,
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text",
            "ollama_base_url": "http://localhost:11434",
            "embedding_dims": 768,
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {"url": QDRANT, "collection_name": COLL, "embedding_model_dims": 768},
    },
}


def q(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{QDRANT}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    BACKUP_DIR.mkdir(mode=0o700, exist_ok=True)

    # 1. Export every point (paged scroll)
    points, offset = [], None
    while True:
        body = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        res = q("POST", f"/collections/{COLL}/points/scroll", body)["result"]
        points.extend(res["points"])
        offset = res.get("next_page_offset")
        if offset is None:
            break
    export_file = BACKUP_DIR / "export.json"
    export_file.write_text(json.dumps(points, indent=1))
    export_file.chmod(0o600)
    print(f"[1/6] exported {len(points)} points -> {export_file}")

    # 2. Server-side snapshot (second backup, restorable in place)
    snap = q("POST", f"/collections/{COLL}/snapshots")["result"]["name"]
    print(f"[2/6] qdrant snapshot created: {snap}")

    # 3. Delete the old (dense-only) collection
    q("DELETE", f"/collections/{COLL}")
    print("[3/6] old collection deleted")

    # 4. Let mem0 recreate it fresh (2.0.11 creates the hybrid schema)
    from mem0 import Memory
    m = Memory.from_config({"llm": MEM0_CFG["llm"], "embedder": MEM0_CFG["embedder"],
                            "vector_store": MEM0_CFG["vector_store"]})
    # force collection creation with a probe write, then remove the probe
    probe = m.add("migration probe", user_id="migration-probe", infer=False)
    for r in (probe.get("results") or []):
        m.delete(r["id"])
    info = q("GET", f"/collections/{COLL}")["result"]
    sparse = (info.get("config", {}).get("params", {}) or {}).get("sparse_vectors")
    print(f"[4/6] fresh collection created; sparse_vectors slot: {list(sparse) if sparse else 'MISSING'}")
    if not sparse:
        print("ABORT: new collection has no sparse slot — restore the snapshot:")
        print(f"  curl -X POST {QDRANT}/collections/{COLL}/snapshots/{snap}/recover"
              f" -H 'Content-Type: application/json' -d '{{\"location\": \"file://{snap}\"}}'")
        return 2

    # 5. Re-import with original scopes; keep provenance in metadata
    ok = fail = 0
    for p in points:
        pl = p["payload"]
        data = pl.get("data") or pl.get("memory")
        if not data:
            continue
        if pl.get("user_id") == "migration-probe":
            continue
        meta = {k: pl[k] for k in ("channel", "attributed_to") if pl.get(k)}
        if pl.get("created_at"):
            meta["migrated_created_at"] = str(pl["created_at"])
        try:
            m.add(data, user_id=pl.get("user_id") or "hermes-user",
                  agent_id=pl.get("agent_id") or "hermes",
                  metadata=meta or None, infer=False)
            ok += 1
        except Exception as e:  # keep going; export file preserves everything
            fail += 1
            print(f"  re-import failed for {str(p['id'])[:13]}: {e}")
        if (ok + fail) % 50 == 0:
            print(f"  ... {ok + fail}/{len(points)}")
    print(f"[5/6] re-imported ok={ok} fail={fail}")

    # 6. Verify count
    time.sleep(1)
    n = q("POST", f"/collections/{COLL}/points/count", {"exact": True})["result"]["count"]
    print(f"[6/6] final count in new collection: {n} (source had {len(points)})")
    print(f"snapshot kept for rollback: {snap}; export kept at {export_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
