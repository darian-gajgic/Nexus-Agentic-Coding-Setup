"""mem0-client — client-isolated Mem0 memory provider (remediation M3).

Subclasses the bundled mem0 provider (bundled names win collisions, so this
ships under its own name and is activated via config `memory.provider:
mem0-client`). Two guarantees:

  WRITE: memories extracted from a client-tagged session are stamped with
  metadata.client. The session→client map is published by Nexus to
  ~/.hermes/client-scopes.json when it dispatches a client-tagged task
  (same bridge-file pattern as model-efforts.json; mtime-cached).

  READ: every retrieval path (turn prefetch, mem0_search, mem0_list) is
  post-filtered — a session sees UNTAGGED (global) memories plus its OWN
  client's, never another client's. Sessions with no client tag see only
  untagged memories, so client facts can never bleed into personal chats.

Global craft learning stays on its dedicated channel: specialist lessons
(reflection → human review), which generalize before they bind.

Delete this directory + revert the config key to `mem0` to fall back.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from plugins.memory.mem0 import Mem0MemoryProvider

logger = logging.getLogger(__name__)

_SCOPES_FILE = os.path.expanduser("~/.hermes/client-scopes.json")
_scope_cache: dict = {"mtime": 0.0, "map": {}}


def _session_client_map() -> dict:
    try:
        mtime = os.stat(_SCOPES_FILE).st_mtime
        if mtime != _scope_cache["mtime"]:
            with open(_SCOPES_FILE) as f:
                data = json.load(f)
            _scope_cache["map"] = {
                str(k): str(v) for k, v in (data.get("sessions") or {}).items() if v}
            _scope_cache["mtime"] = mtime
    except FileNotFoundError:
        _scope_cache["map"] = {}
    except Exception as e:
        logger.warning("mem0-client: scope map unreadable (%s) — keeping last", e)
    return _scope_cache["map"]


class _FilteringBackend:
    """Wraps the real backend so EVERY read path enforces client isolation.
    Rows tagged with a client other than the current session's are dropped;
    untagged rows are global and always pass."""

    def __init__(self, inner, current_client):
        self._inner = inner
        self._current_client = current_client  # callable -> str | None

    def _row_ok(self, row) -> bool:
        if not isinstance(row, dict):
            return True
        md = row.get("metadata") or {}
        tag = md.get("client") if isinstance(md, dict) else None
        return not tag or tag == self._current_client()

    def search(self, *args, **kwargs):
        rows = self._inner.search(*args, **kwargs) or []
        return [r for r in rows if self._row_ok(r)]

    def get_all(self, *args, **kwargs):
        out = self._inner.get_all(*args, **kwargs)
        if isinstance(out, dict):
            rows = [r for r in (out.get("results") or []) if self._row_ok(r)]
            return {"results": rows, "count": len(rows)}
        return out

    def __getattr__(self, name):  # add/update/delete/… pass through
        return getattr(self._inner, name)


class ClientScopedMem0Provider(Mem0MemoryProvider):

    def __init__(self):
        super().__init__()
        self._m3_session_id = ""

    @property
    def name(self) -> str:
        return "mem0-client"

    # ── session tracking (every hook that carries a session_id) ──
    def initialize(self, session_id: str, **kwargs) -> None:
        result = super().initialize(session_id, **kwargs)
        self._m3_session_id = session_id or ""
        if self._backend is not None and not isinstance(self._backend, _FilteringBackend):
            self._backend = _FilteringBackend(self._backend, self._client_now)
        return result

    def on_session_switch(self, new_session_id: str, **kwargs) -> None:
        self._m3_session_id = new_session_id or self._m3_session_id
        parent = getattr(super(), "on_session_switch", None)
        if callable(parent):
            return parent(new_session_id, **kwargs)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if session_id:
            self._m3_session_id = session_id
        return super().prefetch(query, session_id=session_id)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        if session_id:
            self._m3_session_id = session_id
        return super().sync_turn(user_content, assistant_content, session_id=session_id)

    # ── the two scoping chokepoints ──
    def _client_now(self):
        return _session_client_map().get(self._m3_session_id)

    def _write_metadata(self):
        md = dict(super()._write_metadata() or {})
        client = self._client_now()
        if client:
            md["client"] = client
        return md

    def system_prompt_block(self) -> str:
        block = super().system_prompt_block()
        client = self._client_now()
        if client:
            block += (f"\nCLIENT CONTEXT: this session works for client '{client}'. "
                      "Memory recall is isolated to global knowledge plus this "
                      "client's own memories; other clients' data is invisible.")
        return block


def register(ctx) -> None:
    ctx.register_memory_provider(ClientScopedMem0Provider())
