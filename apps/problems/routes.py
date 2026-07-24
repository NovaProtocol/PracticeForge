from __future__ import annotations

from flask import render_template, request

from apps.models import (
    create_solution,
    get_problem,
    get_problems,
    get_sample_cases,
    get_test_cases,
    queue_execution,
)
from apps.problems import blueprint


@blueprint.route("/")
def index():
    problems = get_problems()
    return render_template("problems/index.html", problems=problems)


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    samples = get_sample_cases(problem["id"])
    return render_template("problems/detail.html", problem=problem, samples=samples)


@blueprint.route("/problem/<int:contest_id>/<index>/submit", methods=["POST"])
def submit(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    code = request.form.get("code", "")
    submission_id = create_solution(problem["id"], code)
    queue_execution(submission_id)
    return render_template("problems/queued.html", submission_id=submission_id)
