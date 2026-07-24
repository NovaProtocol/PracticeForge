from __future__ import annotations

from flask import jsonify, request

from apps.api import blueprint
from apps.models import get_solved, get_stats, get_solution, get_test_cases, queue_execution


@blueprint.route("/stats")
def stats():
    return jsonify(get_stats())


@blueprint.route("/solved")
def solved():
    return jsonify(get_solved())


@blueprint.route("/re-run/<int:solution_id>", methods=["POST"])
def re_run(solution_id: int):
    solution = get_solution(solution_id)
    if not solution:
        return jsonify({"error": "not found"}), 404
    queue_execution(solution_id)
    return jsonify({"status": "queued", "solution_id": solution_id})
