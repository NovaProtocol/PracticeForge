from __future__ import annotations

from flask import jsonify, render_template, request

from apps.problems import blueprint
from shared.models import (
    create_run,
    get_all_tags,
    get_all_test_cases,
    get_problem,
    get_problem_stats,
    get_problem_submissions,
    get_problems_with_status,
    get_run_status,
    load_code,
    queue_full_submission,
    queue_test_cases,
    save_code,
)


@blueprint.route("/")
def index():
    problems = get_problems_with_status()
    all_tags = get_all_tags()
    return render_template("problems/index.html", problems=problems, all_tags=all_tags)


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    saved = load_code(problem["id"])
    submissions = get_problem_submissions(problem["id"])
    stats = get_problem_stats(problem["id"])
    return render_template("problems/detail.html", problem=problem, saved_code=saved, submissions=submissions, stats=stats)


@blueprint.route("/problem/<int:contest_id>/<index>/run", methods=["POST"])
def run(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    run_id = create_run(problem["id"], code)
    total = queue_test_cases(run_id, problem["id"], code)
    return jsonify({"run_id": run_id, "total": total, "status": "queued"})


@blueprint.route("/problem/<int:contest_id>/<index>/submit", methods=["POST"])
def submit(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    run_id = request.form.get("run_id", "")
    solution_id = queue_full_submission(problem["id"], code, run_id)
    return jsonify({"solution_id": solution_id, "status": "accepted"})


@blueprint.route("/problem/<int:contest_id>/<index>/save", methods=["POST"])
def save(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    save_code(problem["id"], code)
    return jsonify({"status": "ok"})
