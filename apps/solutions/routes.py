from __future__ import annotations

from flask import render_template

from apps.models import get_solution, get_solutions
from apps.solutions import blueprint


@blueprint.route("/solutions/")
def index():
    solutions = get_solutions()
    return render_template("solutions/index.html", solutions=solutions)


@blueprint.route("/solution/<int:solution_id>/")
def detail(solution_id: int):
    solution = get_solution(solution_id)
    if not solution:
        return render_template("404.html"), 404
    return render_template("solutions/detail.html", solution=solution)
