import os
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request

blueprint = Blueprint(
    "api_blueprint",
    __name__,
    url_prefix="/api",
)

# Write methods (POST/PUT/DELETE) are allowed when the request either
#   a) comes from a browser on the same host (the editor uses sendBeacon
#      and fetch, which cannot carry custom headers), or
#   b) carries a matching X-API-Token header (used by the scraper).
# This protects cookie-authenticated browsers against cross-site requests
# (CSRF / DNS rebinding) while working on any hostname — tunnel or LAN.
_API_TOKEN = os.environ.get("API_TOKEN", "")


@blueprint.before_request
def _require_write_auth():
    if request.method not in ("POST", "PUT", "DELETE"):
        return
    if _API_TOKEN and request.headers.get("X-API-Token", "") == _API_TOKEN:
        return
    origin = request.headers.get("Origin", "") or request.headers.get("Referer", "")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme in ("http", "https") and parsed.netloc == request.host:
            return
    return jsonify({"error": "unauthorized"}), 401
