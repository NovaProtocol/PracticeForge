from __future__ import annotations

from flask import jsonify

from apps.api import blueprint
from shared.models import get_run_status, get_submission_status, load_code


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
