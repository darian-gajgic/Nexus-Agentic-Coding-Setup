"""Shared auth bootstrap for the runtime verify gates.

The gates run on the nexus machine itself against the LIVE server. While the
install is single-user, login is off and every request just works — but once
real multi-user is active (Block 1), the login wall would 401 every gate.
Same-machine trust: a process that can already read nexus.db doesn't need a
password — it mints the owner a direct session token (exactly what the
multi-user probe does) and destroys it again at exit.
"""
import atexit
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def owner_cookie() -> dict:
    """{} while login is off; {"nexus_session": <token>} when it's required."""
    import auth
    if not auth.auth_required():
        return {}
    token = auth.create_session("u_owner", "verify-gate")
    atexit.register(auth.destroy_session, token)
    return {"nexus_session": token}


def playwright_cookies(base_url: str) -> list:
    """add_cookies() payload for a Playwright context; [] while login is off."""
    return [{"name": k, "value": v, "url": base_url}
            for k, v in owner_cookie().items()]
