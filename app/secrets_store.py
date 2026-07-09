"""NEXUS Agent OS — encrypted credential store (Settings v2).

First at-rest crypto in the codebase: user-added provider API keys are
Fernet-encrypted with a machine-local key file (secret.key, 0600, gitignored
runtime data like cert.key). System default keys stay where they already live
(~/.hermes/.env, the Claude CLI's own auth) — a missing credential row means
"use the machine default", so a fresh install works with zero rows and adding
a row only ever NARROWS whose calls use which key.

Contract: no API path ever returns a stored plaintext. Reads outside this
module get metadata + a 4-char hint; only the execution paths (dispatch
session-key bridge, judge subprocess env) call resolve_key().
"""
import os
import re
import time
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

import database as db

BASE_DIR = Path(__file__).parent
KEY_FILE = BASE_DIR / "secret.key"

_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")

_fernet: Fernet | None = None


def _load_fernet() -> Fernet:
    """Machine master key, created race-safely on first use (server and worker
    processes may initialize concurrently — O_EXCL makes exactly one win)."""
    global _fernet
    if _fernet is not None:
        return _fernet
    if not KEY_FILE.exists():
        key = Fernet.generate_key()
        try:
            fd = os.open(str(KEY_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
        except FileExistsError:
            pass  # another process won the race — use its key
    _fernet = Fernet(KEY_FILE.read_bytes().strip())
    return _fernet


def encrypt(value: str) -> str:
    return _load_fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str | None:
    try:
        return _load_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return None


def valid_provider(provider: str) -> bool:
    return bool(_PROVIDER_RE.match(provider or ""))


def _hint(value: str) -> str:
    return value[-4:] if len(value) >= 8 else ""


def _public(row: dict) -> dict:
    """Metadata view — enc_value NEVER leaves this module through here."""
    return {"id": row["id"], "user_id": row["user_id"], "provider": row["provider"],
            "label": row["label"], "hint": row["hint"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "global": row["user_id"] is None}


def set_credential(user_id: str | None, provider: str, value: str,
                   label: str = "", created_by: str | None = None) -> dict:
    """Upsert one credential per (scope, provider). user_id=None = global row
    (machine default override, admin-managed)."""
    now = time.time()
    existing = db.query_one(
        "SELECT * FROM credentials WHERE provider=? AND user_id IS ?",
        (provider, user_id))
    if existing:
        db.execute("UPDATE credentials SET enc_value=?, hint=?, label=?, updated_at=? WHERE id=?",
                   (encrypt(value), _hint(value), label or existing["label"], now, existing["id"]))
        return _public(db.query_one("SELECT * FROM credentials WHERE id=?", (existing["id"],)))
    cid = f"cred-{uuid.uuid4().hex[:10]}"
    db.execute(
        "INSERT INTO credentials (id, user_id, provider, label, enc_value, hint, "
        "created_at, updated_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, user_id, provider, label, encrypt(value), _hint(value), now, now, created_by))
    return _public(db.query_one("SELECT * FROM credentials WHERE id=?", (cid,)))


def list_credentials(user_id: str) -> list[dict]:
    """The caller's own rows + the global rows (metadata only)."""
    rows = db.query_all(
        "SELECT * FROM credentials WHERE user_id=? OR user_id IS NULL "
        "ORDER BY user_id IS NULL, provider", (user_id,))
    return [_public(r) for r in rows]


def get_credential(cred_id: str) -> dict | None:
    row = db.query_one("SELECT * FROM credentials WHERE id=?", (cred_id,))
    return _public(row) if row else None


def delete_credential(cred_id: str):
    db.execute("UPDATE user_models SET credential_id=NULL WHERE credential_id=?", (cred_id,))
    db.execute("DELETE FROM credentials WHERE id=?", (cred_id,))


# ── Machine default keys (~/.hermes/.env) — admin-visible/rotatable ──
# Fixed provider→env allowlist: the endpoint must never accept arbitrary env
# var names (that would be an env-injection surface). anthropic is deliberately
# absent — its default is the Claude CLI's subscription auth, not an env key.

ENV_FILE = os.path.expanduser("~/.hermes/.env")

DEFAULT_PROVIDERS = {
    "zai": {"env": "GLM_API_KEY",
            "label": "Z.AI / GLM — tasks, JARVIS, wizards",
            "restart": "hermes-gateway"},
    "brave": {"env": "BRAVE_SEARCH_API_KEY",
              "label": "Brave Search — Hermes web search",
              "restart": "hermes-gateway"},
    "langfuse_public": {"env": "HERMES_LANGFUSE_PUBLIC_KEY",
                        "label": "Langfuse public key — Observability tab",
                        "restart": None},
    "langfuse_secret": {"env": "HERMES_LANGFUSE_SECRET_KEY",
                        "label": "Langfuse secret key — Observability tab",
                        "restart": None},
}


def default_key_status() -> list[dict]:
    """Masked view of the machine default keys (set/not-set + hint). Values
    come from THIS process's environment (main.py loads ~/.hermes/.env at
    boot and set_default_key updates os.environ live) — the file itself is
    never echoed anywhere."""
    out = []
    for prov, meta in DEFAULT_PROVIDERS.items():
        val = os.environ.get(meta["env"], "")
        out.append({"provider": prov, "env": meta["env"], "label": meta["label"],
                    "set": bool(val), "hint": _hint(val) if val else "",
                    "restart": meta["restart"]})
    out.append({"provider": "anthropic", "env": None,
                "label": "Anthropic — frontier judge (cjudge/cspec/creview)",
                "set": True, "hint": "",
                "managed": "Claude CLI subscription auth (rotate via `claude` login); "
                           "per-user keys above override it for the judge",
                "restart": None})
    return out


def set_default_key(provider: str, value: str, env_file: str | None = None) -> dict:
    """Rotate a machine default key: anchored in-place rewrite of ~/.hermes/.env
    (uncommented or `# [disabled…]`-commented existing line replaced, else
    appended), atomic 0600 write, live os.environ update. Returns the masked
    status row. Raises ValueError for unknown providers — the allowlist above
    is the whole attack surface."""
    meta = DEFAULT_PROVIDERS.get(provider)
    if not meta:
        raise ValueError(f"'{provider}' has no machine default managed here")
    env, path = meta["env"], (env_file or ENV_FILE)
    lines: list[str] = []
    if os.path.isfile(path):
        with open(path) as f:
            lines = f.read().splitlines()
    pat = re.compile(rf"^\s*(#[^=\n]*?)?\b{re.escape(env)}=")
    out: list[str] = []
    replaced = False
    for ln in lines:
        if not pat.match(ln):
            out.append(ln)
        elif not replaced:
            out.append(f"{env}={value}")
            replaced = True
        elif ln.lstrip().startswith("#"):
            out.append(ln)  # extra commented copies are inert — keep them
        # else: drop duplicate ACTIVE lines — dotenv last-wins would revert the rotation
    lines = out
    if not replaced:
        lines.append(f"{env}={value}")
    tmp = f"{path}.tmp-{uuid.uuid4().hex[:6]}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    os.environ[env] = value  # live for THIS process (hints, langfuse proxy)
    return {"provider": provider, "env": env, "set": True, "hint": _hint(value),
            "restart": meta["restart"]}


def resolve_key(user_id: str | None, provider: str,
                credential_id: str | None = None) -> str | None:
    """Plaintext resolution for EXECUTION paths only (never HTTP responses).
    Chain: explicit credential ref → the user's provider row → the global
    provider row → None (= keep using the machine's env/CLI default)."""
    if credential_id:
        row = db.query_one("SELECT * FROM credentials WHERE id=?", (credential_id,))
        if row and row["user_id"] in (user_id, None):
            return decrypt(row["enc_value"])
        return None
    if user_id:
        row = db.query_one(
            "SELECT * FROM credentials WHERE provider=? AND user_id=?", (provider, user_id))
        if row:
            return decrypt(row["enc_value"])
    row = db.query_one(
        "SELECT * FROM credentials WHERE provider=? AND user_id IS NULL", (provider,))
    return decrypt(row["enc_value"]) if row else None
