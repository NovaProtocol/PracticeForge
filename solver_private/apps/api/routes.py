from __future__ import annotations

import json

from flask import jsonify, request

from apps.api import blueprint
from shared.db import execute, query, query_one
from shared.models import (
    create_custom_test_case,
    create_file,
    delete_custom_test_case,
    delete_file,
    get_all_tags,
    get_editorial,
    get_problem,
    get_problem_submissions,
    get_problems_summary,
    get_solution,
    get_solution_results,
    get_solutions,
    list_files,
    load_code,
    rename_file,
    save_code,
    save_last_ran,
    upsert_problem,
)


# ── Problems ──

@blueprint.route("/problems")
def list_problems():
    return jsonify(get_problems_summary())


@blueprint.route("/problems/<int:contest_id>/<index>")
def get_problem_api(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    examples = []
    raw = problem.get("examples_json")
    if isinstance(raw, str):
        try:
            examples = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(raw, list):
        examples = raw
    constraints = []
    raw_c = problem.get("constraints_json")
    if isinstance(raw_c, str):
        try:
            constraints = json.loads(raw_c)
        except (json.JSONDecodeError, TypeError):
            pass
    elif isinstance(raw_c, list):
        constraints = raw_c
    problem["examples"] = examples
    problem["constraints"] = constraints
    return jsonify(problem)


@blueprint.route("/problems/upload", methods=["POST"])
def upload_problem():
    data = request.get_json()
    if not data or "contest_id" not in data or "problem_index" not in data or "title" not in data:
        return jsonify({"error": "missing required fields: contest_id, problem_index, title"}), 400
    try:
        pid = upsert_problem(data)
        return jsonify({"status": "ok", "id": pid})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@blueprint.route("/problems/exists/<int:contest_id>/<index>")
def problem_exists(contest_id: int, index: str):
    row = query_one(
        "SELECT id FROM problems WHERE contest_id = %s AND problem_index = %s",
        (contest_id, index),
    )
    return jsonify({"exists": row is not None, "id": row["id"] if row else None})


# ── Tags ──

@blueprint.route("/tags")
def list_tags():
    from shared.models import get_all_tags
    return jsonify(get_all_tags())


# ── Submissions / Editorial ──

@blueprint.route("/submissions/<int:problem_id>")
def problem_submissions(problem_id: int):
    return jsonify(get_problem_submissions(problem_id))


@blueprint.route("/editorial/<int:problem_id>")
def editorial(problem_id: int):
    content = get_editorial(problem_id)
    if content is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(content)


# ── Solutions ──

@blueprint.route("/solutions")
def list_solutions():
    return jsonify(get_solutions())


@blueprint.route("/solutions/<int:solution_id>")
def get_solution_api(solution_id: int):
    solution = get_solution(solution_id)
    if not solution:
        return jsonify({"error": "not found"}), 404
    raw = get_solution_results(solution_id)
    tc_data = {}
    if raw["result"] and raw["result"] != "{}":
        try:
            tc_data = json.loads(raw["result"])
        except (json.JSONDecodeError, TypeError):
            pass
    return jsonify({
        "solution": solution,
        "test_results": tc_data,
        "stdout": raw["stdout"] or "",
    })


# ── Code execution ──

def _queue_execution(problem_id: int, code: str, method_name: str, exec_type: str, test_cases_json: str = "[]") -> int:
    return execute(
        """INSERT INTO execution_queue (problem_id, code, method_name, test_cases_json, exec_type, status)
           VALUES (%s, %s, %s, %s, %s, 'queued')""",
        (problem_id, code, method_name, test_cases_json, exec_type),
    )


@blueprint.route("/run/<int:contest_id>/<index>", methods=["POST"])
def run_code(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    filename = request.form.get("filename", "main.py")
    method_name = problem.get("method_name") or "run"
    test_cases = request.form.get("testcases", "[]")
    save_last_ran(problem["id"], code, filename)
    qid = _queue_execution(problem["id"], code, method_name, "run", test_cases)
    return jsonify({"queue_id": qid, "status": "queued"})


@blueprint.route("/brute-force/<int:contest_id>/<index>", methods=["POST"])
def brute_force(contest_id: int, index: str):
    try:
        problem = get_problem(contest_id, index)
        if not problem:
            return jsonify({"error": "not found"}), 404
        code = request.form.get("code", "")
        filename = request.form.get("filename", "main.py")
        method_name = problem.get("method_name") or "run"
        save_last_ran(problem["id"], code, filename)
        qid = _queue_execution(problem["id"], code, method_name, "brute_force")
        return jsonify({"queue_id": qid, "status": "queued"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@blueprint.route("/submit/<int:contest_id>/<index>", methods=["POST"])
def submit_code(contest_id: int, index: str):
    try:
        problem = get_problem(contest_id, index)
        if not problem:
            return jsonify({"error": "not found"}), 404
        code = request.form.get("code", "")
        filename = request.form.get("filename", "main.py")
        method_name = problem.get("method_name") or "run"
        save_last_ran(problem["id"], code, filename)
        qid = _queue_execution(problem["id"], code, method_name, "submit_brute")
        return jsonify({"queue_id": qid, "status": "queued"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@blueprint.route("/format", methods=["POST"])
def format_code():
    code = request.form.get("code", "")
    try:
        import black
        mode = black.Mode(target_versions={black.TargetVersion.PY39}, line_length=120)
        formatted = black.format_str(code, mode=mode)
        return jsonify({"formatted": formatted})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@blueprint.route("/queue-status/<int:queue_id>")
def queue_status(queue_id: int):
    q = query_one(
        "SELECT id, status, result, stdout, error, timing_ms, memory_kb, solution_id FROM execution_queue WHERE id = %s",
        (queue_id,),
    )
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


# ── Code auto-save ──

@blueprint.route("/files/<int:problem_id>")
def files_list(problem_id: int):
    include_inactive = request.args.get("include_inactive", "").lower() in ("true", "1")
    if include_inactive:
        rows = query(
            "SELECT filename, code, last_ran, active FROM auto_saves WHERE problem_id = %s ORDER BY filename",
            (problem_id,),
        )
        return jsonify(rows if rows else [])
    return jsonify(list_files(problem_id))


@blueprint.route("/files/<int:problem_id>", methods=["POST"])
def files_create(problem_id: int):
    data = request.get_json() or request.form
    filename = data.get("filename", "main.py")
    code = data.get("code", "")
    create_file(problem_id, filename, code)
    return jsonify({"status": "ok", "filename": filename})


@blueprint.route("/files/<int:problem_id>/<path:filename>", methods=["PUT"])
def files_save(problem_id: int, filename: str):
    code = request.form.get("code", "")
    save_code(problem_id, code, filename)
    return jsonify({"status": "ok"})


@blueprint.route("/files/<int:problem_id>/<path:filename>", methods=["DELETE"])
def files_delete(problem_id: int, filename: str):
    delete_file(problem_id, filename)
    return jsonify({"status": "ok"})


@blueprint.route("/files/<int:problem_id>/<path:old_filename>/rename", methods=["POST"])
def files_rename(problem_id: int, old_filename: str):
    data = request.get_json() or request.form
    new_filename = data.get("filename", "main.py")
    rename_file(problem_id, old_filename, new_filename)
    return jsonify({"status": "ok"})


@blueprint.route("/save/<int:contest_id>/<index>", methods=["POST"])
def save_code_api(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    filename = request.form.get("filename", "main.py")
    save_code(problem["id"], code, filename)
    return jsonify({"status": "ok"})


@blueprint.route("/auto-save/<int:problem_id>")
def auto_save_get(problem_id: int):
    filename = request.args.get("filename", "main.py")
    data = load_code(problem_id, filename)
    return jsonify({"code": data["code"] or "", "last_ran": data["last_ran"] or ""})


# ── Test cases ──

@blueprint.route("/test-cases/<int:problem_id>", methods=["POST"])
def add_test_case(problem_id: int):
    data = request.get_json() or request.form
    tc_id = create_custom_test_case(problem_id, data.get("input", ""), data.get("expected_output", ""))
    return jsonify({"id": tc_id, "status": "created"}), 201


@blueprint.route("/test-cases/<int:tc_id>", methods=["DELETE"])
def remove_test_case(tc_id: int):
    delete_custom_test_case(tc_id)
    return jsonify({"status": "deleted"})
