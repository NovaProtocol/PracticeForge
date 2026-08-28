from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from shared.config import ProductionConfig
from shared.startup import run as run_startup

_ERROR_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    429: "Too Many Requests",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}

def _error_response(code: int, title: str, message: str):
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"error": title, "code": code}), code
    return render_template("error.html", code=code, title=title, message=message), code


def create_app() -> Flask:
    run_startup()

    root = Path(__file__).resolve().parent.parent
    app_templates = Path(__file__).resolve().parent / "templates"
    shared_templates = root / "shared" / "templates"
    app = Flask(__name__, template_folder=str(app_templates))
    # shared/templates (base.html) is merged into /app/templates only in the
    # Docker image; add it as a second loader so host runs resolve it too.
    app.jinja_loader = ChoiceLoader(
        [
            FileSystemLoader(str(app_templates)),
            FileSystemLoader(str(shared_templates)),
        ]
    )
    app.config.from_object(ProductionConfig)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    from apps.api.routes import blueprint as api_blueprint
    from apps.problems.routes import blueprint as problems_blueprint
    from apps.solutions.routes import blueprint as solutions_blueprint

    app.register_blueprint(problems_blueprint)
    app.register_blueprint(solutions_blueprint)
    app.register_blueprint(api_blueprint)

    @app.route("/health")
    def health():
        """Health probe."""
        return {"status": "ok"}

    @app.errorhandler(HTTPException)
    def _handle_http(e: HTTPException):
        code = e.code or 500
        title = _ERROR_TITLES.get(code, e.name or "Error")
        msg = e.description if code != 404 else "The page you're looking for doesn't exist."
        if code not in _ERROR_TITLES:
            code = 500
            title = "Internal Server Error"
            msg = "Something went wrong."
        return _error_response(code, title, msg)

    @app.errorhandler(Exception)
    def _handle_exc(e: Exception):
        if isinstance(e, HTTPException):
            return _handle_http(e)
        return _error_response(500, "Internal Server Error", "Something went wrong.")

    return app
