from __future__ import annotations

import json

from flask import render_template
from bs4 import BeautifulSoup

from apps.problems import blueprint
from shared.models import (
    get_problem,
    get_problem_submissions,
    get_solution,
    get_solution_results,
    load_code,
)

from shared.db import query as raw_query


def _sanitize_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script"):
        tag.decompose()
    return str(soup)


@blueprint.route("/")
def index():
    return render_template("problems/index.html")


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    saved_data = load_code(problem["id"])
    saved = saved_data["code"]
    last_ran = saved_data["last_ran"]
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
    raw_desc = problem.get("description_html") or ""
    problem["description_html"] = _sanitize_html(raw_desc)
    submissions = get_problem_submissions(problem["id"])
    base_code = problem.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
    return render_template("problems/detail.html", problem=problem, saved_code=saved, last_ran=last_ran, submissions=submissions, base_code=base_code)


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
