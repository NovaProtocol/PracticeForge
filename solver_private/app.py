from __future__ import annotations

from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from shared.config import ProductionConfig
from shared.startup import run as run_startup


def create_app() -> Flask:
    run_startup()

    templates = Path(__file__).resolve().parent / "templates"
    app = Flask(__name__, template_folder=str(templates))
    app.config.from_object(ProductionConfig)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    from apps.problems.routes import blueprint as problems_blueprint
    from apps.solutions.routes import blueprint as solutions_blueprint
    app.register_blueprint(problems_blueprint)
    app.register_blueprint(solutions_blueprint)

    return app
