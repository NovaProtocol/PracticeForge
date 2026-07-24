from __future__ import annotations

import json
import os
import resource
import subprocess
import tempfile
import time

from flask import jsonify, render_template, request

from apps.problems import blueprint
from shared.models import (
    create_solution,
    get_all_tags,
    get_all_test_cases,
    get_problem,
    get_problem_submissions,
    get_problems_with_status,
    get_sample_cases,
    get_sample_cases_json,
    load_code,
    save_code,
)


def _run_code(user_code: str, method_name: str, args_json: str, expected_json: str, timeout: int = 10) -> dict:
    wrapper = (
        "import json\n"
        "from typing import List, Optional, Dict, Tuple, Set\n"
        + user_code + "\n"
        "solution = Solution()\n"
        "method = getattr(solution, " + json.dumps(method_name) + ")\n"
        "args = json.loads(" + json.dumps(args_json) + ")\n"
        "result = method(*args)\n"
        "print(json.dumps(result))\n"
    )
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(wrapper)
        tmp.close()
        start = time.perf_counter()
        r = subprocess.run(
            ["python3", tmp.name],
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed = int((time.perf_counter() - start) * 1000)
        try:
            mem = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem = 0
        got = r.stdout.strip()
        expected = expected_json.strip()
        return {
            "passed": r.returncode == 0 and got == expected,
            "got": got,
            "error": r.stderr.strip(),
            "timing_ms": elapsed,
            "memory_kb": mem,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "got": "Time Limit Exceeded", "error": "", "timing_ms": timeout * 1000, "memory_kb": 0}
    except Exception as e:
        return {"passed": False, "got": "", "error": str(e), "timing_ms": 0, "memory_kb": 0}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _normalize_tc(tc: dict, method_name: str) -> tuple:
    """Normalize a test case row to (method_name, args_json, expected_json)."""
    if tc.get("args") is not None:
        return method_name, tc["args"], tc["expected"]
    return method_name, json.dumps([tc.get("input", "")]), json.dumps(tc.get("expected_output", ""))


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
    problem["sample_cases"] = get_sample_cases_json(problem["id"]) or get_sample_cases(problem["id"])
    submissions = get_problem_submissions(problem["id"])
    base_code = problem.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
    return render_template("problems/detail.html", problem=problem, saved_code=saved, submissions=submissions, base_code=base_code)


@blueprint.route("/problem/<int:contest_id>/<index>/run", methods=["POST"])
def run(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    test_cases = json.loads(request.form.get("testcases", "[]"))
    if not test_cases:
        return jsonify({"error": "no test cases", "passed": 0, "total": 0, "results": []})

    method_name = problem.get("method_name") or "run"
    results = []
    passed = 0
    total_timing = 0
    for tc in test_cases:
        mn, args_json, expected_json = _normalize_tc(tc, method_name)
        r = _run_code(code, mn, args_json, expected_json)
        if r["passed"]:
            passed += 1
        total_timing += r["timing_ms"]
        results.append({
            "passed": r["passed"],
            "input": tc.get("input", ""),
            "expected": tc.get("expected", ""),
            "got": r["got"],
            "error": r["error"],
            "timing_ms": r["timing_ms"],
            "memory_kb": r["memory_kb"],
        })

    return jsonify({
        "passed": passed,
        "total": len(test_cases),
        "verdict": "Accepted" if passed == len(test_cases) else "Wrong Answer",
        "results": results,
        "timing_ms": int(total_timing / max(len(test_cases), 1)),
    })


@blueprint.route("/problem/<int:contest_id>/<index>/submit", methods=["POST"])
def submit(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    method_name = problem.get("method_name") or "run"
    all_cases = get_all_test_cases(problem["id"])

    results = []
    passed = 0
    total_timing = 0
    max_memory = 0
    for tc in all_cases:
        mn, args_json, expected_json = _normalize_tc(tc, method_name)
        r = _run_code(code, mn, args_json, expected_json, timeout=30)
        if r["passed"]:
            passed += 1
        total_timing += r["timing_ms"]
        max_memory = max(max_memory, r["memory_kb"])
        results.append({
            "passed": r["passed"],
            "input": tc.get("input", ""),
            "expected": tc.get("expected", ""),
            "got": r["got"],
            "error": r["error"],
            "timing_ms": r["timing_ms"],
            "memory_kb": r["memory_kb"],
        })

    total = len(all_cases)
    verdict = "Accepted" if passed == total else "Wrong Answer"
    avg_timing = int(total_timing / max(total, 1))
    solution_id = create_solution(problem["id"], code, verdict, passed, total, avg_timing, max_memory)

    return jsonify({
        "solution_id": solution_id,
        "verdict": verdict,
        "passed": passed,
        "total": total,
        "results": results,
        "timing_ms": avg_timing,
        "memory_kb": max_memory,
    })


@blueprint.route("/problem/<int:contest_id>/<index>/save", methods=["POST"])
def save(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "not found"}), 404
    code = request.form.get("code", "")
    save_code(problem["id"], code)
    return jsonify({"status": "ok"})
