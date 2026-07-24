from __future__ import annotations

from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from shared.config import ProductionConfig
from shared.gatekeeper import gatekeeper_check


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(ProductionConfig)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    from apps.api.routes import blueprint as api_blueprint
    from apps.problems.routes import blueprint as problems_blueprint
    app.register_blueprint(api_blueprint)
    app.register_blueprint(problems_blueprint)

    app.before_request(gatekeeper_check)

    return app
