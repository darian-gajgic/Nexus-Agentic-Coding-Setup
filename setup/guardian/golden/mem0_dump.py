#!/usr/bin/env python3
"""Dump all local mem0 memories as JSON — for the NEXUS Memory tab.

Reads ~/.hermes/mem0.json (the OSS/local config: llama3.1:8b + nomic-embed + local
qdrant) and lists every stored memory. Run with the hermes venv python (has mem0).
Output: {"count": N, "memories": [{id, memory, created_at, updated_at, metadata}], "user_id": ...}
Never fails hard — on error prints {"count":0,"memories":[],"error":...}.
"""
import json, os, sys
from pathlib import Path


def main():
    try:
        cfg = json.loads((Path.home() / ".hermes" / "mem0.json").read_text())
        oss = cfg["oss"]
        uid = cfg.get("user_id", "hermes-user")
        vs = dict(oss["vector_store"])
        vc = dict(vs.get("config", {}))
        if "path" in vc:
            vc["path"] = os.path.expanduser(vc["path"])
        dims = (oss.get("embedder", {}).get("config", {}) or {}).get("embedding_dims")
        if dims:
            vc["embedding_model_dims"] = dims
        vs["config"] = vc
        config = {"vector_store": vs, "llm": oss["llm"], "embedder": oss["embedder"], "version": "v1.1"}

        from mem0 import Memory
        m = Memory.from_config(config)
        # installed mem0 prefers filters= over top-level user_id; try both
        try:
            res = m.get_all(filters={"user_id": uid})
        except TypeError:
            res = m.get_all(user_id=uid)
        items = res.get("results", res) if isinstance(res, dict) else res
        out = []
        for x in items:
            if not isinstance(x, dict):
                continue
            out.append({
                "id": x.get("id"),
                "memory": x.get("memory") or x.get("text") or x.get("data"),
                "created_at": x.get("created_at"),
                "updated_at": x.get("updated_at"),
                "metadata": x.get("metadata") or {},
            })
        out.sort(key=lambda r: (r.get("updated_at") or r.get("created_at") or ""), reverse=True)
        print(json.dumps({"count": len(out), "user_id": uid, "memories": out}))
    except Exception as e:
        print(json.dumps({"count": 0, "memories": [], "error": str(e)[:200]}))


if __name__ == "__main__":
    main()
