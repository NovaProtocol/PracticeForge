from __future__ import annotations

from flask import jsonify

from apps.api import blueprint
from shared.models import get_solved, get_stats, re_run_solution


@blueprint.route("/stats")
def stats():
    return jsonify(get_stats())


@blueprint.route("/solved")
def solved():
    return jsonify(get_solved())


@blueprint.route("/re-run/<int:solution_id>", methods=["POST"])
def re_run(solution_id: int):
    run_id = re_run_solution(solution_id)
    if not run_id:
        return jsonify({"error": "solution not found or not accepted"}), 404
    return jsonify({"run_id": run_id, "status": "queued"})
