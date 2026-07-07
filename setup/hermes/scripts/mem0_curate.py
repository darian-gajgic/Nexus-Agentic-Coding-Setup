#!/usr/bin/env python3
"""Curated memory writer/deleter for specialist agents.

Adds or deletes a lesson in a specialist's private memory scope (mem0 agent_id),
going through the mem0 backend so the lesson is embedded (nomic-embed-text) and
stored in qdrant exactly like recalled memories. Human-curated (called from the
nexus Specialists tab), so writes are deliberate — not the append-all log.

Usage:
  mem0_curate.py add    --agent-id <name> --text "<lesson>"
  mem0_curate.py delete --id <memory-id>

Prints a JSON result line. Run with the Hermes venv python.
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))


def _provider(agent_id=None):
    from plugins.memory.mem0 import Mem0MemoryProvider
    p = Mem0MemoryProvider()
    kwargs = {"session_id": "nexus-curate"}
    if agent_id:
        kwargs["agent_id"] = agent_id
    p.initialize(**kwargs)
    if p._backend is None:
        raise RuntimeError("mem0 backend not initialized (is qdrant running?)")
    return p


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--agent-id", required=True)
    a.add_argument("--text", required=True)
    a.add_argument("--source", default="curated")  # provenance: curated | reflection-approved
    d = sub.add_parser("delete")
    d.add_argument("--id", required=True)
    args = ap.parse_args()
    try:
        if args.cmd == "add":
            text = args.text.strip()
            if not text:
                print(json.dumps({"ok": False, "error": "empty text"})); return
            p = _provider(args.agent_id)
            res = p._backend.add(
                [{"role": "user", "content": text}],
                user_id=p._user_id,
                agent_id=p._agent_id,          # the specialist scope
                infer=False,                    # store the curated lesson verbatim
                metadata={"channel": "nexus", "attributed_to": "user", "source": args.source,
                          "trust": "human-approved"},
            )
            rid = None
            results = res.get("results") if isinstance(res, dict) else res
            if results:
                rid = results[0].get("id")
            print(json.dumps({"ok": True, "id": rid, "agent_id": p._agent_id}))
        elif args.cmd == "delete":
            p = _provider()
            p._backend.delete(args.id)
            print(json.dumps({"ok": True, "id": args.id}))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)[:200]}))


if __name__ == "__main__":
    main()
