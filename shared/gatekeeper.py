from __future__ import annotations

import os

import requests
from cachetools import TTLCache
from flask import g, redirect, request
from itsdangerous import URLSafeTimedSerializer

GATEKEEPER_INTERNAL = os.environ["GATEKEEPER_INTERNAL"]

# Read-only API endpoints that must work for anonymous visitors on the
# public app. Everything else (including /api/re-run and /api/queue-status)
# requires a valid gatekeeper ticket.
PUBLIC_API_PATHS = ("/api/stats", "/api/solved", "/api/images/")

ticket_cache = TTLCache(maxsize=128, ttl=300)
ticket_serializer = URLSafeTimedSerializer(os.environ["SECRET_KEY"], salt="ticket")


def _gatekeeper_url():
    host = request.host.split(":")[0]
    parts = host.split(".")
    if len(parts) >= 3:
        apex = ".".join(parts[-2:])
        scheme = request.scheme
        port = ""
        if ":" in request.host:
            port = ":" + request.host.split(":")[1]
        return f"{scheme}://gatekeeper.{apex}{port}"
    return f"{request.scheme}://localhost:7000"


def gatekeeper_check():
    if request.path.startswith("/static/"):
        return
    if any(request.path.startswith(p) for p in PUBLIC_API_PATHS):
        return

    token = request.cookies.get("gatekeeper_token")
    if not token:
        return redirect(f"{_gatekeeper_url()}/?redirect={request.url}")

    cached = ticket_cache.get(token)
    if cached:
        g.ticket = cached
        return

    try:
        resp = requests.get(
            f"{GATEKEEPER_INTERNAL}/api/verify?token={token}", timeout=5
        )
        data = resp.json()
        if data.get("valid"):
            payload = ticket_serializer.loads(data["ticket"], max_age=300)
            ticket_cache[token] = payload
            g.ticket = payload
            return
    except Exception:
        pass

    return redirect(f"{_gatekeeper_url()}/?redirect={request.url}")
