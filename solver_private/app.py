from __future__ import annotations

from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from shared.config import ProductionConfig


def create_app() -> Flask:
    templates = Path(__file__).resolve().parent / "templates"
    app = Flask(__name__, template_folder=str(templates))
    app.config.from_object(ProductionConfig)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    from apps.problems import blueprint as problems_blueprint
    from apps.solutions import blueprint as solutions_blueprint
    app.register_blueprint(problems_blueprint)
    app.register_blueprint(solutions_blueprint)

    return app
