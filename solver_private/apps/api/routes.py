from __future__ import annotations

from flask import jsonify, request

from apps.api import blueprint
from shared.models import (
    create_custom_test_case,
    delete_custom_test_case,
    dislike_problem,
    get_editorial,
    get_problem_stats,
    get_problem_submissions,
    get_run_status,
    get_submission_status,
    like_problem,
    load_code,
)


@blueprint.route("/run-status/<run_id>")
def run_status(run_id: str):
    status = get_run_status(run_id)
    if not status:
        return jsonify({"error": "not found"}), 404
    return jsonify(status)


@blueprint.route("/submission-status/<int:solution_id>")
def submission_status(solution_id: int):
    status = get_submission_status(solution_id)
    if not status:
        return jsonify({"error": "not found"}), 404
    return jsonify(status)


@blueprint.route("/auto-save/<int:problem_id>")
def auto_save_get(problem_id: int):
    code = load_code(problem_id)
    return jsonify({"code": code or ""})


@blueprint.route("/problem-stats/<int:problem_id>")
def problem_stats(problem_id):
    return jsonify(get_problem_stats(problem_id))


@blueprint.route("/problem/<int:problem_id>/like", methods=["POST"])
def problem_like(problem_id):
    return jsonify(like_problem(problem_id))


@blueprint.route("/problem/<int:problem_id>/dislike", methods=["POST"])
def problem_dislike(problem_id):
    return jsonify(dislike_problem(problem_id))


@blueprint.route("/problem-submissions/<int:problem_id>")
def problem_submissions(problem_id):
    return jsonify(get_problem_submissions(problem_id))


@blueprint.route("/editorial/<int:problem_id>")
def editorial(problem_id):
    content = get_editorial(problem_id)
    if content is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(content)


@blueprint.route("/test-cases/<int:problem_id>", methods=["POST"])
def add_test_case(problem_id):
    data = request.get_json() or request.form
    tc_id = create_custom_test_case(problem_id, data.get("input", ""), data.get("expected_output", ""))
    return jsonify({"id": tc_id, "status": "created"}), 201


@blueprint.route("/test-cases/<int:tc_id>", methods=["DELETE"])
def remove_test_case(tc_id):
    delete_custom_test_case(tc_id)
    return jsonify({"status": "deleted"})
