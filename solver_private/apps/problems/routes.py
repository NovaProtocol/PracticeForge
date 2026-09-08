from __future__ import annotations

import contextlib
import json
import re

from bs4 import BeautifulSoup
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from apps.templating import templates
from shared.db import query as raw_query
from shared.models import get_problem, get_problem_submissions, get_solution, get_solution_results, load_code

router = APIRouter(tags=["problems"])

_ALLOWED_TAGS = {"b","i","u","em","strong","p","br","ul","ol","li","code","pre","h1","h2","h3","h4","h5","h6","img","a","blockquote","hr"}
_ALLOWED_ATTRS = {"img": {"src", "alt", "style"}, "a": {"href", "title", "rel"}}
_SAFE_IMG_PREFIXES = ("/api/images/",)

def _sanitize_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        if tag.name not in _ALLOWED_TAGS:
            tag.decompose()
            continue
        allowed = _ALLOWED_ATTRS.get(tag.name, set())
        for attr in list(tag.attrs):
            if attr not in allowed:
                del tag[attr]
        if tag.name == "img":
            src = tag.get("src", "")
            if not isinstance(src, str) or not src.startswith(_SAFE_IMG_PREFIXES):
                tag.decompose()
    for tag in soup.find_all("a"):
        href = tag.get("href", "")
        if not isinstance(href, str) or href.lower().startswith("javascript:"):
            tag.decompose()
    result = str(soup)
    result = re.sub(r"\[image:\s*([a-zA-Z0-9_.-]+)\]", r'<img src="/api/images/\1" style="display:block;margin:0 auto;max-width:100%;border-radius:6px;">', result)
    result = re.sub(r"\n", "<br>\n", result)
    return result


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "problems/index.html", {})


@router.get("/problem/{contest_id}/{index}/", response_class=HTMLResponse)
async def detail(request: Request, contest_id: int, index: str):
    problem = await run_in_threadpool(get_problem, contest_id, index)
    if not problem:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    saved_data = await run_in_threadpool(load_code, problem["id"])
    saved = saved_data["code"]
    last_ran = saved_data["last_ran"]
    examples = []
    raw = problem.get("examples_json")
    if isinstance(raw, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            examples = json.loads(raw)
    elif isinstance(raw, list):
        examples = raw
    constraints = []
    raw_c = problem.get("constraints_json")
    if isinstance(raw_c, str):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            constraints = json.loads(raw_c)
    elif isinstance(raw_c, list):
        constraints = raw_c
    problem["examples"] = examples
    problem["constraints"] = constraints
    raw_desc = problem.get("description_html") or ""
    problem["description_html"] = _sanitize_html(raw_desc)
    submissions = await run_in_threadpool(get_problem_submissions, problem["id"])
    base_code = problem.get("base_code") or "class Solution:\n    def run(self, input: str) -> str:\n        "
    return templates.TemplateResponse(request, "problems/detail.html", {"problem": problem, "saved_code": saved, "last_ran": last_ran, "submissions": submissions, "base_code": base_code})


@router.get("/problem/{contest_id}/{index}/solution/{solution_id}", response_class=HTMLResponse)
async def solution_view(request: Request, contest_id: int, index: str, solution_id: int):
    problem = await run_in_threadpool(get_problem, contest_id, index)
    if not problem:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    solution = await run_in_threadpool(get_solution, solution_id)
    if not solution or solution["problem_id"] != problem["id"]:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    raw = await run_in_threadpool(get_solution_results, solution_id)
    tc_data = {}
    if raw["result"] and raw["result"] != "{}":
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            tc_data = json.loads(raw["result"])
    best = await run_in_threadpool(raw_query, "SELECT MIN(timing_ms) AS best_timing, MIN(memory_kb) AS best_memory FROM solutions WHERE problem_id = %s AND verdict = 'Accepted'", (problem["id"],))
    best_timing = best[0]["best_timing"] if best and best[0] else None
    best_memory = best[0]["best_memory"] if best and best[0] else None
    return templates.TemplateResponse(request, "problems/solution.html", {"problem": problem, "solution": solution, "tc_data": tc_data, "results_stdout": raw["stdout"], "best_timing": best_timing, "best_memory": best_memory})
