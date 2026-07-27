from __future__ import annotations

from flask import render_template

from apps.solutions import blueprint
from shared.models import get_solution


@blueprint.route("/solutions/")
def index():
    return render_template("solutions/index.html")


@blueprint.route("/solution/<int:solution_id>/")
def detail(solution_id: int):
    solution = get_solution(solution_id)
    if not solution:
        return render_template("404.html"), 404
    return render_template("solutions/detail.html", solution=solution)
