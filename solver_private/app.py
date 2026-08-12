from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.middleware.proxy_fix import ProxyFix

from shared.config import ProductionConfig
from shared.startup import run as run_startup


def create_app() -> Flask:
    run_startup()

    root = Path(__file__).resolve().parent.parent
    app_templates = Path(__file__).resolve().parent / "templates"
    shared_templates = root / "shared" / "templates"
    app = Flask(__name__, template_folder=str(app_templates))
    # shared/templates (base.html) is merged into /app/templates only in the
    # Docker image; add it as a second loader so host runs resolve it too.
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(str(app_templates)),
        FileSystemLoader(str(shared_templates)),
    ])
    app.config.from_object(ProductionConfig)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    from apps.problems.routes import blueprint as problems_blueprint
    from apps.solutions.routes import blueprint as solutions_blueprint
    from apps.api.routes import blueprint as api_blueprint
    app.register_blueprint(problems_blueprint)
    app.register_blueprint(solutions_blueprint)
    app.register_blueprint(api_blueprint)

    @app.route("/404")
    def not_found_page():
        return render_template("404.html"), 404

    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    return app
