from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from apps.templating import templates
from shared.models import get_solution, get_solutions

router = APIRouter(tags=["solutions"])


@router.get("/solutions/", response_class=HTMLResponse)
async def index(request: Request):
    solutions = await run_in_threadpool(get_solutions)
    return templates.TemplateResponse(request, "solutions/index.html", {"solutions": solutions})


@router.get("/solution/{solution_id}/", response_class=HTMLResponse)
async def detail(request: Request, solution_id: int):
    solution = await run_in_threadpool(get_solution, solution_id)
    if not solution:
        return templates.TemplateResponse(request, "404.html", {}, status_code=404)
    return templates.TemplateResponse(request, "solutions/detail.html", {"solution": solution})
