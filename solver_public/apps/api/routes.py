from __future__ import annotations

import json
import os
import resource
import subprocess
import tempfile
import time as time_module

from flask import jsonify

from apps.api import blueprint
from shared.db import query_one
from shared.models import get_solved, get_stats, get_solution, get_all_test_cases, create_solution


def _run_code(user_code: str, method_name: str, args_json: str, expected_json: str, timeout: int = 30) -> dict:
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
        start = time_module.perf_counter()
        r = subprocess.run(["python3", tmp.name], capture_output=True, text=True, timeout=timeout)
        elapsed = int((time_module.perf_counter() - start) * 1000)
        try:
            mem = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        except Exception:
            mem = 0
        got = r.stdout.strip()
        expected = expected_json.strip()
        return {"passed": r.returncode == 0 and got == expected, "got": got, "error": r.stderr.strip(), "timing_ms": elapsed, "memory_kb": mem}
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
    if tc.get("args") is not None:
        return method_name, tc["args"], tc["expected"]
    return method_name, json.dumps([tc.get("input", "")]), json.dumps(tc.get("expected_output", ""))


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
    problem = query_one("SELECT method_name FROM problems WHERE id = %s", (solution["problem_id"],))
    method_name = problem["method_name"] if problem and problem["method_name"] else "run"
    test_cases = get_all_test_cases(solution["problem_id"])
    passed = 0
    total_timing = 0
    max_memory = 0
    for tc in test_cases:
        mn, args_json, expected_json = _normalize_tc(tc, method_name)
        r = _run_code(solution["code"], mn, args_json, expected_json, timeout=30)
        if r["passed"]:
            passed += 1
        total_timing += r["timing_ms"]
        max_memory = max(max_memory, r["memory_kb"])
    total = len(test_cases)
    verdict = "Accepted" if passed == total else "Wrong Answer"
    new_id = create_solution(solution["problem_id"], solution["code"], verdict, passed, total,
                              int(total_timing / max(total, 1)), max_memory)
    return jsonify({"solution_id": new_id, "verdict": verdict, "passed": passed, "total": total})
