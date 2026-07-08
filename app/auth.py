"""NEXUS Agent OS — Authentication & user identity (Block 1 multi-user).

Design (docs/SPEC-MULTIUSER.md):
- ALWAYS exactly one resolved user per request. A default `u_owner` user is
  seeded at migration and owns all pre-multiuser rows, so every query in the
  app is uniformly user-scoped — there is no unscoped code path.
- Login is required only when >= 2 active users exist (or settings
  `auth.force=1`). With 0/1 users every request auto-resolves to the sole
  active user: the single-operator machine behaves exactly as before.
- Sessions: random 256-bit token in an HttpOnly cookie; the DB stores only
  its sha256 (DB theft does not yield live sessions). 30-day sliding expiry.
- Passwords: scrypt (stdlib, memory-hard), constant-time verify.
- The ASGI middleware in server.py resolves the user once per request into
  a contextvar; endpoints call auth.current_user() / current_user_id().
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from contextvars import ContextVar

import database as db

COOKIE_NAME = "nexus_session"
SESSION_TTL = 30 * 24 * 3600          # 30 days
SESSION_RENEW_BELOW = 15 * 24 * 3600  # sliding: extend when < 15 days left
SESSION_LAST_SEEN_THROTTLE = 60       # only rewrite last_seen when this stale (keep the hot path read-only)
DEFAULT_USER_ID = "u_owner"

# Paths reachable without a session even when login is required.
# Static assets + the SPA shell are code, not data; all data flows via /api.
PUBLIC_PATHS = ("/api/auth/login", "/api/auth/state")
PUBLIC_PREFIXES = ("/static/",)
PUBLIC_EXACT = ("/", "/favicon.ico")

_request_user: ContextVar[dict | None] = ContextVar("nexus_request_user", default=None)

# Per-boot service token for IN-PROCESS engines (loop engine) that call the
# local HTTP API from background threads: they present it together with the
# acting user's id (the owning task's user), so internal automation stays
# user-scoped instead of bypassing isolation. Never persisted, never leaves
# the process; a restart rotates it.
INTERNAL_TOKEN = secrets.token_urlsafe(32)
INTERNAL_HEADER = "x-nexus-internal"
INTERNAL_USER_HEADER = "x-nexus-user"


def internal_token_valid(presented: str) -> bool:
    return bool(presented) and hmac.compare_digest(presented, INTERNAL_TOKEN)

# Login rate-limit: key -> list of failure timestamps (in-memory; resets on
# restart, which is fine — it only throttles brute force).
_login_failures: dict[str, list[float]] = {}
_RL_MAX_FAILURES = 5
_RL_WINDOW = 15 * 60


# ── password hashing (scrypt, stdlib) ──────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    n, r, p = 16384, 8, 1
    h = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                           n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(h.hex(), hash_hex)
    except Exception:
        return False


# ── user helpers ───────────────────────────────────────────────────────────

def get_user(user_id: str) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE id=? AND active=1", (user_id,))


def get_user_by_username(username: str) -> dict | None:
    return db.query_one("SELECT * FROM users WHERE username=? AND active=1",
                        ((username or "").strip().lower(),))


def public_user(u: dict | None) -> dict | None:
    """Strip secrets before a user row leaves the server."""
    if not u:
        return None
    return {"id": u["id"], "username": u["username"],
            "display_name": u.get("display_name") or u["username"],
            "role": u.get("role") or "member",
            "has_password": bool(u.get("password_hash")),
            "active": bool(u.get("active", 1)),
            "created_at": u.get("created_at")}


def active_users() -> list[dict]:
    return db.query_all("SELECT * FROM users WHERE active=1 ORDER BY created_at")


# Hot-path micro-cache: auth_required()/sole_user() run on EVERY request
# (the UI polls every 3s); a 2s TTL keeps them at ~zero queries without
# meaningfully delaying an auth flip (adding user #2 bites within 2s).
_auth_cache: dict = {"ts": 0.0, "required": False, "sole": None}
_AUTH_CACHE_TTL = 2.0


def _refresh_auth_cache():
    now = time.time()
    if now - _auth_cache["ts"] < _AUTH_CACHE_TTL:
        return
    forced = db.get_setting("auth.force", "0") == "1"
    rows = active_users()
    _auth_cache["required"] = forced or len(rows) >= 2
    _auth_cache["sole"] = (rows[0] if len(rows) == 1 else
                           next((r for r in rows if r["id"] == DEFAULT_USER_ID),
                                rows[0] if rows else None))
    _auth_cache["ts"] = now


def auth_required() -> bool:
    """Login is needed only once a second user exists (or when forced)."""
    _refresh_auth_cache()
    return _auth_cache["required"]


def sole_user() -> dict | None:
    """The auto-identity used while login is off (0/1 users configured)."""
    _refresh_auth_cache()
    return _auth_cache["sole"]


# ── sessions ───────────────────────────────────────────────────────────────

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: str, ua: str = "") -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    db.execute("INSERT INTO auth_sessions (token_hash, user_id, created_at, "
               "expires_at, last_seen, ua) VALUES (?,?,?,?,?,?)",
               (_token_hash(token), user_id, now, now + SESSION_TTL, now, ua[:200]))
    return token


def resolve_session(token: str) -> dict | None:
    """token -> active user dict, with sliding renewal. None if invalid."""
    if not token:
        return None
    now = time.time()
    row = db.query_one(
        "SELECT s.token_hash, s.expires_at, s.last_seen AS _last_seen, u.* FROM auth_sessions s "
        "JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash=? AND s.expires_at > ? AND u.active=1",
        (_token_hash(token), now))
    if not row:
        return None
    if row["expires_at"] - now < SESSION_RENEW_BELOW:
        db.execute("UPDATE auth_sessions SET expires_at=?, last_seen=? WHERE token_hash=?",
                   (now + SESSION_TTL, now, row["token_hash"]))
    elif now - (row["_last_seen"] or 0) > SESSION_LAST_SEEN_THROTTLE:
        # Throttle: keep the per-request path read-only unless last_seen is
        # actually stale — a blocking SQLite write per request stalls the loop.
        db.execute("UPDATE auth_sessions SET last_seen=? WHERE token_hash=?",
                   (now, row["token_hash"]))
    row.pop("token_hash", None)
    row.pop("expires_at", None)
    row.pop("_last_seen", None)
    return row


def destroy_session(token: str):
    if token:
        db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_token_hash(token),))


def prune_sessions():
    db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (time.time(),))


# ── login (with brute-force throttle) ──────────────────────────────────────

def _rl_key(username: str, ip: str) -> str:
    return f"{(username or '').lower()}|{ip or '?'}"


def login_throttled(username: str, ip: str) -> bool:
    now = time.time()
    hits = [t for t in _login_failures.get(_rl_key(username, ip), []) if now - t < _RL_WINDOW]
    _login_failures[_rl_key(username, ip)] = hits
    return len(hits) >= _RL_MAX_FAILURES


def record_login_failure(username: str, ip: str):
    _login_failures.setdefault(_rl_key(username, ip), []).append(time.time())
    if len(_login_failures) > 1000:  # bound the dict
        _login_failures.clear()


def try_login(username: str, password: str, ip: str = "") -> dict | None:
    """Returns the user on success, None on any failure (generic upstream)."""
    if login_throttled(username, ip):
        return None
    u = get_user_by_username(username)
    if not u or not u.get("password_hash"):
        # Constant-ish time: burn a hash anyway so absent users don't
        # answer faster than wrong passwords.
        verify_password(password or "", hash_password("x"))
        record_login_failure(username, ip)
        return None
    if not verify_password(password or "", u["password_hash"]):
        record_login_failure(username, ip)
        return None
    _login_failures.pop(_rl_key(username, ip), None)
    return u


# ── per-request identity (set by the ASGI middleware) ──────────────────────

def set_request_user(user: dict | None):
    _request_user.set(user)


def current_user() -> dict | None:
    """The request's resolved user. Outside a request (background/direct
    calls) this falls back to the sole user — but ONLY while login is off;
    once multi-user, an unresolved identity must never default to someone."""
    u = _request_user.get()
    if u is not None:
        return u
    if not auth_required():
        return sole_user()
    return None


def current_user_id() -> str:
    u = current_user()
    return u["id"] if u else DEFAULT_USER_ID


def is_admin() -> bool:
    u = current_user()
    return bool(u and (u.get("role") or "member") == "admin")


# ── user management ────────────────────────────────────────────────────────

def create_user(username: str, display_name: str, password: str,
                role: str = "member") -> tuple[dict | None, str]:
    """Returns (user, "") or (None, error)."""
    username = (username or "").strip().lower()
    if not username or not username.replace("-", "").replace("_", "").isalnum():
        return None, "username must be alphanumeric (dashes/underscores ok)"
    if len(username) > 32:
        return None, "username too long"
    if not password or len(password) < 8:
        return None, "password must be at least 8 characters"
    if role not in ("admin", "member"):
        return None, "role must be admin or member"
    if db.query_one("SELECT id FROM users WHERE username=?", (username,)):
        return None, "username already exists"
    uid = "u_" + uuid.uuid4().hex[:10]
    db.execute("INSERT INTO users (id, username, display_name, password_hash, "
               "role, active, created_at) VALUES (?,?,?,?,?,1,?)",
               (uid, username, (display_name or username).strip()[:60],
                hash_password(password), role, time.time()))
    invalidate_auth_cache()
    return get_user(uid), ""


def invalidate_auth_cache():
    _auth_cache["ts"] = 0.0


def seed_default_user():
    """Idempotent: guarantee the default owner exists (migration + fresh DBs)."""
    if not db.query_one("SELECT id FROM users WHERE id=?", (DEFAULT_USER_ID,)):
        db.execute("INSERT INTO users (id, username, display_name, password_hash, "
                   "role, active, created_at) VALUES (?,?,?,?,?,1,?)",
                   (DEFAULT_USER_ID, "owner", "Operator", "", "admin", time.time()))
