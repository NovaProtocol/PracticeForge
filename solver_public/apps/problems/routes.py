from __future__ import annotations

from flask import render_template

from apps.problems import blueprint
from shared.models import get_problems_with_status, get_all_tags, get_problem, load_code, get_solutions_for_problem


@blueprint.route("/")
def summary():
    problems = get_problems_with_status()
    completed = [p for p in problems if p["completion"] == "completed"]
    total = len(problems)
    solved = len(completed)
    return render_template("public/summary.html", solved=solved, total=total, completed=completed[:5])


@blueprint.route("/problems/")
def index():
    problems = get_problems_with_status()
    all_tags = get_all_tags()
    return render_template("public/index.html", problems=problems, all_tags=all_tags)


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    saved = load_code(problem["id"])
    problem_solutions = get_solutions_for_problem(problem["id"])
    return render_template("public/detail.html", problem=problem, saved_code=saved, solutions=problem_solutions)
