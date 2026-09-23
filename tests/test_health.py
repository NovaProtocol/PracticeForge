"""Light smoke tests for the solver app.

Verifies create_app() imports cleanly and that the /404 route renders with
base.html resolved from shared/templates. In the Docker image, the build
merges shared/templates into the app's template dir; host runs rely on the
ChoiceLoader fallback, which is what these tests pin down.
"""

import pytest

pytest.importorskip("fastapi")


@pytest.fixture()
def app(monkeypatch):
    # run_startup() calls get_engine(), which needs real MYSQL_* env vars;
    # the health page itself never touches the database, so stub it out.
    monkeypatch.setattr("shared.startup.run", lambda: None)
    from solver_private.app import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_create_app_registers_routes(app):
    paths = set(app.openapi()["paths"])
    assert "/solutions/" in paths
    assert "/api/problems" in paths
    assert "/api/tags" in paths


def test_404_renders_with_base_template(client):
    resp = client.get("/404")
    assert resp.status_code == 404
    html = resp.text
    assert "Not Found" in html
    # Both markers come from base.html (title + footer/nav), proving the
    # shared template was resolved.
    assert "PracticeForge" in html
