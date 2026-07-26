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
    get_sample_cases,
    get_sample_cases_json,
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
    problem["sample_cases"] = get_sample_cases_json(problem["id"]) or get_sample_cases(problem["id"])
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


@blueprint.route("/problem/test")
def test_panel():
    problems = db_query(
        "SELECT id, contest_id, problem_index, title, status, last_scraped_at, regeneration_count, is_interactive FROM problems ORDER BY id"
    )
    return render_template("problems/test.html", problems=problems)


def _build_test_wrapper(code: str, examples: list[dict]) -> str:
    lines = [
        "import json, sys, traceback",
        code,
        "solution = Solution()",
        "results = []",
    ]
    for ex in examples:
        inp = ex.get("input", "")
        expected = ex.get("output", "")
        lines.append("try:")
        lines.append("    _inp = " + json.dumps(inp))
        lines.append("    _exp = " + json.dumps(expected))
        lines.append("    _got = solution.run(_inp)")
        lines.append("    _got_str = str(_got) if not isinstance(_got, str) else _got")
        lines.append("    _passed = _got_str.strip() == _exp.strip()")
        lines.append("    results.append({'input': _inp, 'expected': _exp, 'got': _got_str, 'passed': _passed})")
        lines.append("except Exception as _e:")
        lines.append("    results.append({'input': " + json.dumps(inp) + ", 'expected': " + json.dumps(expected) + ", 'got': repr(_e), 'passed': False, 'error': traceback.format_exc()})")
    lines.append("print('__SOLVER_RESULT__')")
    lines.append("print(json.dumps(results))")
    return "\n".join(lines)


def _run_code(wrapper_code: str, timeout: int = 15) -> dict:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(wrapper_code)
        tmp.close()
        os.chmod(tmp.name, 0o644)
        start = time.perf_counter()
        r = subprocess.run(
            ["python3", tmp.name],
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        stdout = r.stdout.strip()
        results_json = "[]"
        marker = "__SOLVER_RESULT__"
        if marker in stdout:
            parts = stdout.split(marker + "\n", 1)
            if len(parts) > 1:
                results_json = parts[1].strip()
        return {
            "returncode": r.returncode,
            "stdout": stdout,
            "stderr": r.stderr.strip(),
            "results_json": results_json,
            "timing_ms": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Time Limit Exceeded", "results_json": "[]", "timing_ms": timeout * 1000}
    except Exception as e:
        return {"returncode": -2, "stdout": "", "stderr": str(e), "results_json": "[]", "timing_ms": 0}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@blueprint.route("/api/test/<int:problem_id>", methods=["POST"])
def test_single(problem_id: int):
    row = db_query_one("SELECT id, examples_json, ai_base_code, base_code, status, title FROM problems WHERE id = %s", (problem_id,))
    if not row:
        return jsonify({"error": "not found"}), 404

    examples = []
    if row.get("examples_json"):
        try:
            examples = json.loads(row["examples_json"]) if isinstance(row["examples_json"], str) else row["examples_json"]
        except (json.JSONDecodeError, TypeError):
            pass

    if not examples:
        return jsonify({"error": "no examples", "problem_id": problem_id, "title": row["title"], "status": row["status"]}), 200

    code = row.get("ai_base_code") or row.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
    wrapper = _build_test_wrapper(code, examples)
    result = _run_code(wrapper)

    tc_results = []
    try:
        tc_results = json.loads(result["results_json"])
    except (json.JSONDecodeError, TypeError):
        tc_results = [{"input": "", "expected": "", "got": "", "passed": False, "error": result["stderr"] or result["stdout"]}]

    passed = sum(1 for t in tc_results if t.get("passed"))
    total = len(tc_results)

    return jsonify({
        "problem_id": problem_id,
        "title": row["title"],
        "status": row["status"],
        "passed": passed,
        "total": total,
        "all_passed": passed == total and total > 0,
        "results": tc_results,
        "timing_ms": result["timing_ms"],
        "stderr": result["stderr"],
    })


@blueprint.route("/api/test-all", methods=["POST"])
def test_all():
    rows = db_query(
        "SELECT id, examples_json, ai_base_code, base_code, status, title FROM problems WHERE status = 'ready' AND is_interactive = FALSE AND examples_json IS NOT NULL"
    )
    all_results = []
    for row in rows:
        examples = []
        if row.get("examples_json"):
            try:
                examples = json.loads(row["examples_json"]) if isinstance(row["examples_json"], str) else row["examples_json"]
            except (json.JSONDecodeError, TypeError):
                pass
        if not examples:
            all_results.append({"problem_id": row["id"], "title": row["title"], "passed": 0, "total": 0, "all_passed": False, "error": "no examples"})
            continue
        code = row.get("ai_base_code") or row.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
        wrapper = _build_test_wrapper(code, examples)
        result = _run_code(wrapper)
        tc_results = []
        try:
            tc_results = json.loads(result["results_json"])
        except (json.JSONDecodeError, TypeError):
            tc_results = [{"input": "", "expected": "", "got": "", "passed": False, "error": result["stderr"] or result["stdout"]}]
        passed = sum(1 for t in tc_results if t.get("passed"))
        total = len(tc_results)
        all_results.append({
            "problem_id": row["id"],
            "title": row["title"],
            "passed": passed,
            "total": total,
            "all_passed": passed == total and total > 0,
            "results": tc_results,
            "timing_ms": result["timing_ms"],
        })
    return jsonify({"results": all_results})


@blueprint.route("/api/test-and-fix", methods=["POST"])
def test_and_fix():
    rows = db_query(
        "SELECT id, examples_json, ai_base_code, base_code, status, title FROM problems WHERE status = 'ready' AND is_interactive = FALSE AND examples_json IS NOT NULL"
    )
    all_results = []
    for row in rows:
        examples = []
        if row.get("examples_json"):
            try:
                examples = json.loads(row["examples_json"]) if isinstance(row["examples_json"], str) else row["examples_json"]
            except (json.JSONDecodeError, TypeError):
                pass
        if not examples:
            all_results.append({"problem_id": row["id"], "title": row["title"], "passed": 0, "total": 0, "all_passed": False, "error": "no examples"})
            continue
        code = row.get("ai_base_code") or row.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
        wrapper = _build_test_wrapper(code, examples)
        result = _run_code(wrapper)
        tc_results = []
        try:
            tc_results = json.loads(result["results_json"])
        except (json.JSONDecodeError, TypeError):
            tc_results = [{"input": "", "expected": "", "got": "", "passed": False, "error": result["stderr"] or result["stdout"]}]
        passed = sum(1 for t in tc_results if t.get("passed"))
        total = len(tc_results)
        all_passed = passed == total and total > 0
        if not all_passed:
            failed_info = {
                "failed_count": total - passed,
                "results": tc_results,
            }
            db_execute(
                "UPDATE problems SET status = 'need-regeneration', regeneration_feedback = %s, regeneration_count = regeneration_count + 1 WHERE id = %s",
                (json.dumps(failed_info), row["id"]),
            )
        all_results.append({
            "problem_id": row["id"],
            "title": row["title"],
            "passed": passed,
            "total": total,
            "all_passed": all_passed,
            "fixed": not all_passed,
            "results": tc_results,
            "timing_ms": result["timing_ms"],
        })
    return jsonify({"results": all_results})
