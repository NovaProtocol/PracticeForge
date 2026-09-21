"""Cache-Control precedence in ``shared/middleware.py``.

The middleware promises that a response which sets its own ``Cache-Control``
keeps it. It used to break that promise whenever the deployment ran in debug,
and this stack sits behind a shared cache, so an asset a route deliberately
published was pinned to ``no-store`` on every request and re-fetched every time.

The other half of the promise is the safety net: a gap is still filled in, and
the API class never becomes shared-cacheable, because those responses are
per-visitor and frequently gated.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from shared.middleware import (  # noqa: E402
    _API_MAX_AGE,
    _HTML_MAX_AGE,
    _MISC_MAX_AGE,
    _STATIC_MAX_AGE,
    CacheControlMiddleware,
    _cache_control_for,
)

UPSTREAM_CACHE = "public, max-age=300"


def build_app(
    is_debug: bool, headers: dict[str, str] | None = None, path: str = "/thing"
) -> FastAPI:
    """A minimal app whose one route answers with the headers under test."""
    app = FastAPI()

    @app.get(path)
    async def _route() -> PlainTextResponse:
        return PlainTextResponse("ok", headers=dict(headers or {}))

    app.add_middleware(CacheControlMiddleware, is_debug=is_debug)  # type: ignore[arg-type]
    return app


@pytest.mark.parametrize("is_debug", [True, False])
def test_a_route_that_sets_its_own_policy_keeps_it_in_production_only(is_debug: bool) -> None:
    """In production the upstream header wins; in debug nothing is cacheable."""
    with TestClient(build_app(is_debug, {"Cache-Control": UPSTREAM_CACHE})) as client:
        response = client.get("/thing")

    expected = "no-store" if is_debug else UPSTREAM_CACHE
    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize("is_debug", [True, False])
def test_a_route_that_sets_nothing_is_filled_in(is_debug: bool) -> None:
    with TestClient(build_app(is_debug)) as client:
        response = client.get("/thing")

    expected = "no-store" if is_debug else _cache_control_for("/thing")
    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/static/app.css", "public, max-age=86400"),
        ("/static/js/main.js", "public, max-age=86400"),
        ("/health", "public, max-age=3600"),
        ("/api/problems", "private, no-store"),
        ("/api/health", "private, no-store"),
        ("/problems/3", "private, max-age=300"),
        ("/", "private, max-age=300"),
    ],
)
def test_each_path_class_in_production(path: str, expected: str) -> None:
    """The classes are tested in order, so the API prefix wins over /api/health."""
    assert _cache_control_for(path) == expected

    with TestClient(build_app(False, path=path)) as client:
        response = client.get(path)

    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize(
    "prefix", ["/api/", "/customer/api/", "/staff/api/", "/developer/api/", "/webhook/"]
)
@pytest.mark.parametrize("is_debug", [True, False])
def test_the_api_prefixes_are_never_shared_cacheable(prefix: str, is_debug: bool) -> None:
    """Per-visitor JSON may never rest in a shared cache, in either mode."""
    path = f"{prefix}thing"
    with TestClient(build_app(is_debug, path=path)) as client:
        response = client.get(path)

    value = response.headers["Cache-Control"]
    assert value == ("no-store" if is_debug else "private, no-store")
    assert "public" not in value


def test_the_documented_lifespans_match_the_constants() -> None:
    """The caching page quotes these numbers, so a change here breaks it.

    The page is ``documentation/docs/caching.md``. This test is the tripwire
    between it and the code: change a constant and the documented table is wrong
    until it is updated too.
    """
    assert _STATIC_MAX_AGE == 86400
    assert _HTML_MAX_AGE == 300
    assert _API_MAX_AGE == 0
    assert _MISC_MAX_AGE == 3600

    assert _cache_control_for("/static/anything") == f"public, max-age={_STATIC_MAX_AGE}"
    assert _cache_control_for("/anything") == f"private, max-age={_HTML_MAX_AGE}"
    assert _cache_control_for("/health") == f"public, max-age={_MISC_MAX_AGE}"


def test_the_api_class_does_not_use_the_max_age_zero_constant() -> None:
    """``_API_MAX_AGE = 0`` sits with the lifespans but does not produce its value.

    A bare ``max-age=0`` asks for revalidation, not for a storage ban, and these
    responses must never be stored at all. The prefix branch returns the literal
    instead, so the constant is deliberately unused here.
    """
    assert _API_MAX_AGE == 0
    assert _cache_control_for("/api/thing") == "private, no-store"
