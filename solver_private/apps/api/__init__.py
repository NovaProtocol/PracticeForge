import os

from flask import Blueprint, jsonify, request

blueprint = Blueprint(
    "api_blueprint",
    __name__,
    url_prefix="/api",
)

# Write methods (POST/PUT/DELETE) are allowed when the request either
#   a) comes from a browser on an allowed origin (the editor uses sendBeacon
#      and fetch, which cannot carry custom headers), or
#   b) carries a matching X-API-Token header (used by the scraper).
# Set API_TOKEN in env for machine-to-machine clients. Requests from other
# origins (e.g. a malicious site trying to hit the LAN editor) are rejected.
_API_TOKEN = os.environ.get("API_TOKEN", "")
_ALLOWED_ORIGINS = tuple(
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://debian.local:7031,http://debian.local:7030,http://localhost:7031,http://localhost:7030",
    ).split(",")
    if o.strip()
)


@blueprint.before_request
def _require_write_auth():
    if request.method not in ("POST", "PUT", "DELETE"):
        return
    if _API_TOKEN and request.headers.get("X-API-Token", "") == _API_TOKEN:
        return
    origin = request.headers.get("Origin", "") or request.headers.get("Referer", "")
    if origin and any(origin.startswith(o) for o in _ALLOWED_ORIGINS):
        return
    return jsonify({"error": "unauthorized"}), 401
