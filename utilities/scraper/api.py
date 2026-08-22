import requests

from . import log
from .config import ACCESS_CODE, API_BASE

_session = None


def get_session() -> requests.Session:
    """Authenticated session for the gated API.

    The GateKeeper forward-auth gate sits in front of every API path. Machine
    clients authenticate with the magic-link flow: one request carrying
    ?access_code= makes the gate answer 302 + Set-Cookie, the session stores
    the cookie, and every request after that passes with the cookie alone.
    """
    global _session
    if _session is None:
        s = requests.Session()
        if ACCESS_CODE:
            try:
                r = s.get(
                    f"{API_BASE}/api/problems/exists/0/0",
                    params={"access_code": ACCESS_CODE},
                    timeout=15,
                )
                log.info(f"Gate handshake: {r.status_code} (cookie set)")
            except Exception as e:
                log.error(f"Gate handshake failed: {e}")
        else:
            log.error("ACCESS_CODE not set — every request will be redirected to login")
        _session = s
    return _session
