from __future__ import annotations

import json

from flask import jsonify

from apps.api import blueprint
from shared.db import execute, query_one
from shared.models import get_solved, get_stats, get_solution


@blueprint.route("/stats")
def stats():
    return jsonify(get_stats())


@blueprint.route("/solved")
def solved():
    return jsonify(get_solved())


@blueprint.route("/re-run/<int:solution_id>", methods=["POST"])
def re_run(solution_id: int):
    solution = get_solution(solution_id)
    if not solution or solution["verdict"] != "Accepted":
        return jsonify({"error": "not found or not accepted"}), 404
    method_name = "run"
    problem = query_one("SELECT method_name FROM problems WHERE id = %s", (solution["problem_id"],))
    if problem and problem.get("method_name"):
        method_name = problem["method_name"]
    execute(
        """INSERT INTO execution_queue (problem_id, code, method_name, exec_type, status)
           VALUES (%s, %s, %s, 'run', 'queued')""",
        (solution["problem_id"], solution["code"], method_name),
    )
    qid = query_one("SELECT LAST_INSERT_ID() AS id")["id"]
    return jsonify({"queue_id": qid, "status": "queued"})


@blueprint.route("/queue-status/<int:queue_id>")
def queue_status(queue_id: int):
    q = query_one("SELECT id, status, result, stdout, error, timing_ms, memory_kb FROM execution_queue WHERE id = %s", (queue_id,))
    if not q:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "queue_id": q["id"],
        "status": q["status"],
        "result": q["result"] or "",
        "stdout": q["stdout"] or "",
        "error": q["error"] or "",
        "timing_ms": q["timing_ms"],
        "memory_kb": q["memory_kb"],
    })
