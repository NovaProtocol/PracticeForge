from __future__ import annotations

import json
import subprocess
import tempfile
import time
import os

from flask import jsonify, render_template, request

from apps.problems import blueprint
from shared.db import execute as db_execute, query as db_query, query_one as db_query_one
from shared.models import (
    get_all_tags,
    get_problem,
    get_problem_submissions,
    get_problems_with_status,
    get_solution,
    get_solution_results,
    load_code,
    save_code,
    save_last_ran,
)


def _queue_execution(problem_id: int, code: str, method_name: str, exec_type: str, test_cases_json: str = "[]") -> int:
    from shared.db import execute as db_execute, query_one
    db_execute(
        """INSERT INTO execution_queue (problem_id, code, method_name, test_cases_json, exec_type, status)
           VALUES (%s, %s, %s, %s, %s, 'queued')""",
        (problem_id, code, method_name, test_cases_json, exec_type),
    )
    return query_one("SELECT LAST_INSERT_ID() AS id")["id"]


def _get_queue_status(queue_id: int) -> dict | None:
    from shared.db import query_one as db_query_one
    return db_query_one(
        "SELECT id, status, result, error, timing_ms, memory_kb, solution_id FROM execution_queue WHERE id = %s",
        (queue_id,),
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
    saved_data = load_code(problem["id"])
    saved = saved_data["code"]
    last_ran = saved_data["last_ran"]
    # Use AI-generated examples from examples_json column instead of test_cases table
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
    submissions = get_problem_submissions(problem["id"])
    base_code = problem.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
    return render_template("problems/detail.html", problem=problem, saved_code=saved, last_ran=last_ran, submissions=submissions, base_code=base_code)


@blueprint.route("/problem/<int:contest_id>/<index>/run", methods=["POST"])
def run(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    method_name = problem.get("method_name") or "run"
    test_cases = request.form.get("testcases", "[]")
    save_last_ran(problem["id"], code)
    qid = _queue_execution(problem["id"], code, method_name, "run", test_cases)
    return jsonify({"queue_id": qid, "status": "queued"})


@blueprint.route("/problem/<int:contest_id>/<index>/submit", methods=["POST"])
def submit(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    method_name = problem.get("method_name") or "run"
    save_last_ran(problem["id"], code)
    qid = _queue_execution(problem["id"], code, method_name, "submit")
    return jsonify({"queue_id": qid, "status": "queued"})


@blueprint.route("/api/queue-status/<int:queue_id>")
def queue_status(queue_id: int):
    q = _get_queue_status(queue_id)
    if not q:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "queue_id": q["id"],
        "status": q["status"],
        "result": q["result"] or "",
        "error": q["error"] or "",
        "timing_ms": q["timing_ms"],
        "memory_kb": q["memory_kb"],
        "solution_id": q["solution_id"],
    })


@blueprint.route("/problem/<int:contest_id>/<index>/solution/<int:solution_id>")
def solution_view(contest_id: int, index: str, solution_id: int):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    solution = get_solution(solution_id)
    if not solution or solution["problem_id"] != problem["id"]:
        return render_template("404.html"), 404
    raw = get_solution_results(solution_id)
    tc_data = {}
    if raw["result"] and raw["result"] != "{}":
        try:
            tc_data = json.loads(raw["result"])
        except (json.JSONDecodeError, TypeError):
            pass
    from shared.db import query as raw_query
    best = raw_query(
        """SELECT MIN(timing_ms) AS best_timing, MIN(memory_kb) AS best_memory
           FROM solutions
           WHERE problem_id = %s AND verdict = 'Accepted'""",
        (problem["id"],),
    )
    best_timing = best[0]["best_timing"] if best and best[0] else None
    best_memory = best[0]["best_memory"] if best and best[0] else None
    return render_template(
        "problems/solution.html",
        problem=problem,
        solution=solution,
        tc_data=tc_data,
        results_stdout=raw["stdout"],
        best_timing=best_timing,
        best_memory=best_memory,
    )


@blueprint.route("/problem/<int:contest_id>/<index>/save", methods=["POST"])
def save(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    save_code(problem["id"], code)
    return jsonify({"status": "ok"})
