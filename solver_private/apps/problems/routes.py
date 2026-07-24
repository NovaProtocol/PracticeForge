from __future__ import annotations

import os
import subprocess
import tempfile

from flask import jsonify, render_template, request

from apps.problems import blueprint
from shared.models import (
    create_solution,
    get_problem,
    get_problems,
    get_sample_cases,
    queue_execution,
)


@blueprint.route("/")
def index():
    problems = get_problems()
    return render_template("problems/index.html", problems=problems)


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    samples = get_sample_cases(problem["id"])
    return render_template("problems/detail.html", problem=problem, samples=samples)


def _run_code(code: str, stdin_data: str, timeout: int = 10) -> dict:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(code)
        tmp.close()
        r = subprocess.run(
            ["python3", tmp.name],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "passed": r.returncode == 0,
            "got": r.stdout.strip(),
            "error": r.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "got": "Time Limit Exceeded", "error": ""}
    except Exception as e:
        return {"passed": False, "got": "", "error": str(e)}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@blueprint.route("/problem/<int:contest_id>/<index>/run", methods=["POST"])
def run(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "problem not found"}), 404

    code = request.form.get("code", "")
    samples = get_sample_cases(problem["id"])
    results = []
    passed = 0

    for tc in samples:
        r = _run_code(code, tc["input"])
        got = r["got"]
        if r["passed"] and got == tc["expected_output"].strip():
            passed += 1
            results.append({"passed": True, "input": tc["input"], "expected": tc["expected_output"], "got": got})
        elif r["error"]:
            results.append({"passed": False, "input": tc["input"], "expected": tc["expected_output"], "got": r["error"]})
        else:
            results.append({"passed": False, "input": tc["input"], "expected": tc["expected_output"], "got": got or r["error"]})

    total = len(samples)
    return jsonify({
        "passed": passed,
        "total": total,
        "verdict": "Accepted" if passed == total else "Wrong Answer",
        "results": results,
    })


@blueprint.route("/problem/<int:contest_id>/<index>/submit", methods=["POST"])
def submit(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return jsonify({"error": "problem not found"}), 404

    code = request.form.get("code", "")
    submission_id = create_solution(problem["id"], code)
    queue_execution(submission_id)

    return jsonify({"submission_id": submission_id, "status": "queued"})
