from __future__ import annotations

import re

from flask import render_template
from bs4 import BeautifulSoup

from apps.problems import blueprint
from shared.models import get_problems_with_status, get_all_tags, get_problem, load_code, get_solutions_for_problem


def _sanitize_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script"):
        tag.decompose()
    for tag in soup.find_all("style"):
        tag.decompose()
    result = str(soup)
    result = re.sub(r'<script\b[^>]*>', '', result, flags=re.IGNORECASE)
    result = re.sub(r'</script>', '', result, flags=re.IGNORECASE)
    result = re.sub(r'<style\b[^>]*>', '', result, flags=re.IGNORECASE)
    result = re.sub(r'</style>', '', result, flags=re.IGNORECASE)
    return result


@blueprint.route("/")
def summary():
    problems = get_problems_with_status()
    completed = [p for p in problems if p["completion"] == "completed"]
    total = len(problems)
    solved = len(completed)
    return render_template("public/summary.html", solved=solved, total=total, completed=completed[:5])


@blueprint.route("/problems/")
def index():
    problems = get_problems_with_status()
    all_tags = get_all_tags()
    return render_template("public/index.html", problems=problems, all_tags=all_tags)


@blueprint.route("/problem/<int:contest_id>/<index>/")
def detail(contest_id: int, index: str):
    problem = get_problem(contest_id, index)
    if not problem:
        return render_template("404.html"), 404
    raw_desc = problem.get("description_html") or ""
    problem["description_html"] = _sanitize_html(raw_desc)
    saved = load_code(problem["id"])
    problem_solutions = get_solutions_for_problem(problem["id"])
    return render_template("public/detail.html", problem=problem, saved_code=saved, solutions=problem_solutions)
