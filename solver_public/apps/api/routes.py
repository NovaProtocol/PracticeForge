from __future__ import annotations

import os
import resource
import subprocess
import tempfile
import time as time_module

from flask import jsonify

from apps.api import blueprint
from shared.models import get_solved, get_stats, get_solution, get_test_cases, create_solution


def _run_code(code: str, stdin_data: str, timeout: int = 30) -> dict:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    try:
        tmp.write(code)
        tmp.close()
        start = time_module.perf_counter()
        r = subprocess.run(
            ["python3", tmp.name],
            input=stdin_data, capture_output=True, text=True, timeout=timeout,
        )
        elapsed = int((time_module.perf_counter() - start) * 1000)
        try:
            mem = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem = 0
        return {"passed": r.returncode == 0, "got": r.stdout.strip(), "error": r.stderr.strip(), "timing_ms": elapsed, "memory_kb": mem}
    except subprocess.TimeoutExpired:
        return {"passed": False, "got": "Time Limit Exceeded", "error": "", "timing_ms": timeout * 1000, "memory_kb": 0}
    except Exception as e:
        return {"passed": False, "got": "", "error": str(e), "timing_ms": 0, "memory_kb": 0}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


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
    test_cases = get_test_cases(solution["problem_id"])
    passed = 0
    total_timing = 0
    max_memory = 0
    for tc in test_cases:
        r = _run_code(solution["code"], tc["input"])
        if r["passed"] and r["got"] == tc["expected_output"].strip():
            passed += 1
        total_timing += r["timing_ms"]
        max_memory = max(max_memory, r["memory_kb"])
    total = len(test_cases)
    verdict = "Accepted" if passed == total else "Wrong Answer"
    new_id = create_solution(solution["problem_id"], solution["code"], verdict, passed, total,
                              int(total_timing / max(total, 1)), max_memory)
    return jsonify({"solution_id": new_id, "verdict": verdict, "passed": passed, "total": total})
