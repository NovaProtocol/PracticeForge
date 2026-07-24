from __future__ import annotations

from flask import jsonify, request

from apps.api import blueprint
from shared.models import (
    create_custom_test_case,
    delete_custom_test_case,
    get_editorial,
    get_problem_submissions,
    load_code,
)


@blueprint.route("/sample-cases/<int:problem_id>")
def sample_cases(problem_id: int):
    from shared.models import get_sample_cases_json
    cases = get_sample_cases_json(problem_id)
    return jsonify(cases)


@blueprint.route("/submissions/<int:problem_id>")
def problem_submissions(problem_id: int):
    return jsonify(get_problem_submissions(problem_id))


@blueprint.route("/editorial/<int:problem_id>")
def editorial(problem_id: int):
    content = get_editorial(problem_id)
    if content is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(content)


@blueprint.route("/test-cases/<int:problem_id>", methods=["POST"])
def add_test_case(problem_id: int):
    data = request.get_json() or request.form
    tc_id = create_custom_test_case(problem_id, data.get("input", ""), data.get("expected_output", ""))
    return jsonify({"id": tc_id, "status": "created"}), 201


@blueprint.route("/test-cases/<int:tc_id>", methods=["DELETE"])
def remove_test_case(tc_id: int):
    delete_custom_test_case(tc_id)
    return jsonify({"status": "deleted"})


@blueprint.route("/queue-status/<int:queue_id>")
def queue_status(queue_id: int):
    from shared.db import query_one
    q = query_one("SELECT id, status, result, stdout, error, timing_ms, memory_kb, solution_id FROM execution_queue WHERE id = %s", (queue_id,))
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
        "solution_id": q["solution_id"],
    })


@blueprint.route("/auto-save/<int:problem_id>")
def auto_save_get(problem_id: int):
    data = load_code(problem_id)
    return jsonify({"code": data["code"] or "", "last_ran": data["last_ran"] or ""})
