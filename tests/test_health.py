"""Light smoke tests for the solver Flask app.

Verifies create_app() imports cleanly and that the /404 route renders with
base.html resolved from shared/templates. In the Docker image, the build
merges shared/templates into the app's template dir; host runs rely on the
ChoiceLoader fallback, which is what these tests pin down.
"""

import pytest

pytest.importorskip("flask")


@pytest.fixture()
def app(monkeypatch):
    # run_startup() calls get_engine(), which needs real MYSQL_* env vars;
    # the health page itself never touches the database, so stub it out.
    monkeypatch.setattr("shared.startup.run", lambda: None)
    from solver_private.app import create_app

    return create_app()


@pytest.fixture()
def client(app):
    return app.test_client()


def test_create_app_registers_blueprints(app):
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert "problems_blueprint.index" in endpoints
    assert "solutions_blueprint.index" in endpoints
    assert endpoints & {"api_blueprint.list_problems", "api_blueprint.list_tags"}


def test_404_renders_with_base_template(client):
    resp = client.get("/404")
    assert resp.status_code == 404
    html = resp.get_data(as_text=True)
    assert "Not Found" in html
    # Both markers come from base.html (title + footer/nav), proving the
    # shared template was resolved.
    assert "SolveSpace" in html
