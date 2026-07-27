from __future__ import annotations

import json

from flask import render_template, request

from apps.problems import blueprint
from shared.models import (
    get_problem,
    get_problems_with_status,
    get_solution,
    get_solution_results,
    load_code,
)

from shared.db import query as raw_query


@blueprint.route("/")
def index():
    return render_template("problems/index.html")


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    return render_template("problems/detail.html", contest_id=contest_id, problem_index=index)


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
    best = raw_query(
        """SELECT MIN(timing_ms) AS best_timing, MIN(memory_kb) AS best_memory
           FROM solutions WHERE problem_id = %s AND verdict = 'Accepted'""",
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
