from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

try:
    import structlog.contextvars as _ctx  # type: ignore

    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Bind request_id into structlog contextvars and echo X-Request-ID.

    Reads the inbound X-Request-ID
    or generates uuid4().hex, binds via structlog.contextvars, echoes on
    response and exposes via CORS. Installed first so 401s carry request_id.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        if _HAS_STRUCTLOG:
            try:
                _ctx.bind_contextvars(request_id=request_id)
            except Exception:
                pass
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            existing = response.headers.get("Access-Control-Expose-Headers", "")
            expose = "X-Request-ID"
            if existing:
                parts = {p.strip() for p in existing.split(",") if p.strip()}
                parts.add(expose)
                response.headers["Access-Control-Expose-Headers"] = ", ".join(sorted(parts))
            else:
                response.headers["Access-Control-Expose-Headers"] = expose
            return response
        finally:
            if _HAS_STRUCTLOG:
                try:
                    _ctx.unbind_contextvars("request_id")
                except Exception:
                    pass


# Production cache lifespans, in seconds. Tuning one is a one-line edit here
# plus a redeploy; they are deliberately not env vars.
_STATIC_MAX_AGE = 86400
_HTML_MAX_AGE = 300
_API_MAX_AGE = 0
_MISC_MAX_AGE = 3600

# Debug value: forbids any cache from storing the response at all, so gated
# bytes never rest on shared infrastructure while developing.
_NO_STORE = "no-store"

# Path classes. Anything unmatched falls through to the short HTML lifespan.
_STATIC_PREFIX = "/static/"
_API_PREFIXES = ("/api/", "/customer/api/", "/staff/api/", "/developer/api/", "/webhook/")
_MISC_PATHS = frozenset({"/health", "/api/health"})


def _public_max_age(seconds: int) -> str:
    return f"public, max-age={seconds}"


def _cache_control_for(path: str) -> str:
    if path.startswith(_STATIC_PREFIX):
        return _public_max_age(_STATIC_MAX_AGE)
    if path.startswith(_API_PREFIXES):
        # API responses are per-visitor and frequently gated. Never let a shared
        # cache hold them, whatever the deployment type.
        return "private, no-store"
    if path in _MISC_PATHS:
        return _public_max_age(_MISC_MAX_AGE)
    return f"private, max-age={_HTML_MAX_AGE}"


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Set Cache-Control per deployment type, without overriding a route's own.

    A response that already carries a ``Cache-Control`` header keeps it, so a
    route that sets its own policy is never overridden here. Only when none is
    present is one filled in: ``no-store`` in debug, the path class's lifespan
    otherwise.

    The invariant that makes keeping a header safe:

        A response may be ``public``-cacheable only when the path is ungated
        (the gate resolved ``action == "none"``) **and** the upstream chose
        that header itself.

    This service is not the gate, so it cannot know whether a path was gated and
    it does not demote. On a stack behind GateKeeper the gateway applies that
    demotion before the response reaches a shared cache.
    """

    def __init__(self, app, is_debug: bool) -> None:
        super().__init__(app)
        self.is_debug = is_debug

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if "Cache-Control" in response.headers:
            return response
        if self.is_debug:
            response.headers["Cache-Control"] = _NO_STORE
        else:
            response.headers["Cache-Control"] = _cache_control_for(request.url.path)
        return response
