from __future__ import annotations

import os

import requests
from cachetools import TTLCache
from flask import g, redirect, request
from itsdangerous import URLSafeTimedSerializer

GATEKEEPER_INTERNAL = os.environ["GATEKEEPER_INTERNAL"]

# Machine-to-machine clients (the scraper) authenticate with this header and
# bypass the browser ticket flow entirely. Empty when API_TOKEN is not set.
_API_TOKEN = os.environ.get("API_TOKEN", "")

ticket_cache = TTLCache(maxsize=128, ttl=300)
ticket_serializer = URLSafeTimedSerializer(os.environ["SECRET_KEY"], salt="ticket")


def _gatekeeper_url():
    host = request.host.split(":")[0]
    parts = host.split(".")
    if len(parts) >= 3 and not all(p.isdigit() for p in parts):
        apex = ".".join(parts[-2:])
        scheme = request.scheme
        port = ""
        if ":" in request.host:
            port = ":" + request.host.split(":")[1]
        return f"{scheme}://gatekeeper.{apex}{port}"
    # LAN hosts (e.g. debian.local) and IP addresses — the gatekeeper service
    # publishes :7000 on the host.
    return f"{request.scheme}://{host}:7000"


def gatekeeper_check():
    if request.path.startswith("/static/"):
        return
    if _API_TOKEN and request.headers.get("X-API-Token", "") == _API_TOKEN:
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
