from __future__ import annotations

from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from starlette.templating import Jinja2Templates

from shared.config import shared_static_dir, shared_templates_dir


def _build_env() -> Environment:
    app_root = Path(__file__).resolve().parent.parent
    app_templates = app_root / "templates"
    shared_templates = Path(shared_templates_dir())
    # also include app sub-templates (problems/solutions)
    candidates = []
    # blueprint template roots so "problems/index.html" resolves
    for sub in ("apps/problems/templates", "apps/solutions/templates"):
        p = app_root / sub
        if p.exists():
            candidates.append(str(p))
    # solver_private/templates
    if app_templates.exists():
        candidates.append(str(app_templates))
    # shared/templates
    if shared_templates.exists():
        candidates.append(str(shared_templates))
    # fallback repo layout
    if not candidates:
        candidates = [str(app_templates), str(shared_templates)]
    loader = ChoiceLoader([FileSystemLoader(c) for c in candidates])
    env = Environment(loader=loader, autoescape=select_autoescape(["html", "xml"]))

    def _url_for(endpoint: str, **values):
        # Flask-style endpoint shims used in templates
        if endpoint in ("problems_blueprint.index", "problems.index", "index"):
            return "/"
        if endpoint in ("solutions_blueprint.index", "solutions.index"):
            return "/solutions/"
        if endpoint in ("problems_blueprint.detail", "problems.detail", "detail"):
            cid = values.get("contest_id", "")
            idx = values.get("index", values.get("problem_index", ""))
            if cid and idx:
                return f"/problem/{cid}/{idx}/"
            return "/"
        # generic fallback
        return "/" + endpoint.replace(".", "/")

    env.globals["url_for"] = _url_for
    return env


_env = _build_env()
templates = Jinja2Templates(env=_env)
