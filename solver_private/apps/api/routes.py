from __future__ import annotations

import base64
import contextlib
import json
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from shared.db import execute, query, query_one
from shared.models import (
    create_file,
    create_image,
    delete_file,
    delete_image,
    get_all_tags,
    get_editorial,
    get_image,
    get_problem,
    get_problem_submissions,
    get_problems_summary,
    get_solution,
    get_solution_results,
    get_solutions,
    list_files,
    load_code,
    rename_file,
    save_code,
    save_last_ran,
    upsert_problem,
)

router = APIRouter(prefix="/api", tags=["api"])

_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}

async def _require_write_auth(request: Request, x_api_token: str | None = Header(default=None, alias="X-API-Token")):
    if request.method not in ("POST", "PUT", "DELETE"):
        return
    import os
    api_token = os.environ.get("API_TOKEN", "")
    if api_token and x_api_token == api_token:
        return
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if origin:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        host = request.headers.get("host", "")
        if parsed.scheme in ("http", "https") and parsed.netloc == host:
            return
    # allow if no token configured (dev) — match Flask fallback that returned 401 only when token set
    if not api_token:
        return
    from fastapi import HTTPException
    raise HTTPException(status_code=401, detail="unauthorized")


# -- Problems --

@router.get("/problems")
async def list_problems():
    return await run_in_threadpool(get_problems_summary)


@router.get("/problems/{contest_id}/{index}")
async def get_problem_api(contest_id: int, index: str):
    problem = await run_in_threadpool(get_problem, contest_id, index)
    if not problem:
        return JSONResponse({"error": "not found"}, status_code=404)
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
    return problem


@router.post("/problems/upload", dependencies=[Depends(_require_write_auth)])
async def upload_problem(request: Request):
    data = await request.json()
    if not data or "contest_id" not in data or "problem_index" not in data or "title" not in data:
        return JSONResponse({"error": "missing required fields: contest_id, problem_index, title"}, status_code=400)
    try:
        pid = await run_in_threadpool(upsert_problem, data)
        return {"status": "ok", "id": pid}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/problems/exists/{contest_id}/{index}")
async def problem_exists(contest_id: int, index: str):
    row = await run_in_threadpool(query_one, "SELECT id FROM problems WHERE contest_id = %s AND problem_index = %s", (contest_id, index))
    return {"exists": row is not None, "id": row["id"] if row else None}


@router.get("/tags")
async def list_tags():
    return await run_in_threadpool(get_all_tags)


@router.get("/submissions/{problem_id}")
async def problem_submissions(problem_id: int):
    return await run_in_threadpool(get_problem_submissions, problem_id)


@router.get("/editorial/{problem_id}")
async def editorial(problem_id: int):
    content = await run_in_threadpool(get_editorial, problem_id)
    if content is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return content


@router.get("/solutions")
async def list_solutions():
    return await run_in_threadpool(get_solutions)


@router.get("/solutions/{solution_id}")
async def get_solution_api(solution_id: int):
    solution = await run_in_threadpool(get_solution, solution_id)
    if not solution:
        return JSONResponse({"error": "not found"}, status_code=404)
    raw = await run_in_threadpool(get_solution_results, solution_id)
    tc_data = {}
    if raw["result"] and raw["result"] != "{}":
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            tc_data = json.loads(raw["result"])
    return {"solution": solution, "test_results": tc_data, "stdout": raw["stdout"] or ""}


def _queue_execution(problem_id: int, code: str, method_name: str, exec_type: str, test_cases_json: str = "[]") -> int:
    try:
        from shared.grpc_client import enqueue_via_grpc
        qid = enqueue_via_grpc(problem_id, code, method_name, test_cases_json, exec_type)
        if qid is not None:
            return int(qid)
    except Exception:
        pass
    return execute("INSERT INTO execution_queue (problem_id, code, method_name, test_cases_json, exec_type, status) VALUES (%s, %s, %s, %s, %s, 'queued')", (problem_id, code, method_name, test_cases_json, exec_type))


@router.post("/run/{contest_id}/{index}", dependencies=[Depends(_require_write_auth)])
async def run_code(contest_id: int, index: str, request: Request):
    problem = await run_in_threadpool(get_problem, contest_id, index)
    if not problem:
        return JSONResponse({"error": "not found"}, status_code=404)
    form = await request.form()
    code = str(form.get("code", ""))
    filename = str(form.get("filename", "main.py"))
    method_name = problem.get("method_name") or "run"
    raw_tcs = str(form.get("testcases", "[]"))
    await run_in_threadpool(save_last_ran, problem["id"], code, filename)
    qid = await run_in_threadpool(_queue_execution, problem["id"], code, method_name, "run", raw_tcs)
    return {"queue_id": qid, "status": "queued"}


@router.post("/brute-force/{contest_id}/{index}", dependencies=[Depends(_require_write_auth)])
async def brute_force(contest_id: int, index: str, request: Request):
    try:
        problem = await run_in_threadpool(get_problem, contest_id, index)
        if not problem:
            return JSONResponse({"error": "not found"}, status_code=404)
        form = await request.form()
        code = str(form.get("code", ""))
        filename = str(form.get("filename", "main.py"))
        method_name = problem.get("method_name") or "run"
        await run_in_threadpool(save_last_ran, problem["id"], code, filename)
        qid = await run_in_threadpool(_queue_execution, problem["id"], code, method_name, "brute_force")
        return {"queue_id": qid, "status": "queued"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/submit/{contest_id}/{index}", dependencies=[Depends(_require_write_auth)])
async def submit_code(contest_id: int, index: str, request: Request):
    try:
        problem = await run_in_threadpool(get_problem, contest_id, index)
        if not problem:
            return JSONResponse({"error": "not found"}, status_code=404)
        form = await request.form()
        code = str(form.get("code", ""))
        filename = str(form.get("filename", "main.py"))
        method_name = problem.get("method_name") or "run"
        await run_in_threadpool(save_last_ran, problem["id"], code, filename)
        qid = await run_in_threadpool(_queue_execution, problem["id"], code, method_name, "submit_brute")
        return {"queue_id": qid, "status": "queued"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/format", dependencies=[Depends(_require_write_auth)])
async def format_code(request: Request):
    form = await request.form()
    code = str(form.get("code", ""))
    try:
        import black
        mode = black.Mode(target_versions={black.TargetVersion.PY39}, line_length=120)
        formatted = black.format_str(code, mode=mode)
        return {"formatted": formatted}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/re-run/{solution_id}", dependencies=[Depends(_require_write_auth)])
async def re_run(solution_id: int):
    solution = await run_in_threadpool(get_solution, solution_id)
    if not solution or solution["verdict"] != "Accepted":
        return JSONResponse({"error": "not found or not accepted"}, status_code=404)
    problem = await run_in_threadpool(query_one, "SELECT method_name, examples_json FROM problems WHERE id = %s", (solution["problem_id"],))
    method_name = "run"
    test_cases_json = "[]"
    if problem:
        if problem.get("method_name"):
            method_name = problem["method_name"]
        raw = problem.get("examples_json")
        examples = []
        if isinstance(raw, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                examples = json.loads(raw)
        elif isinstance(raw, list):
            examples = raw
        test_cases_json = json.dumps([{"input": dict(ex.get("input") or {}), "output": ex.get("output"), **({"hidden": ex["hidden"]} if "hidden" in ex else {})} for ex in examples if isinstance(ex, dict)])
    qid = await run_in_threadpool(_queue_execution, solution["problem_id"], solution["code"], method_name, "run", test_cases_json)
    return {"queue_id": qid, "status": "queued"}


@router.get("/queue-status/{queue_id}")
async def queue_status(queue_id: int):
    try:
        from shared.grpc_client import get_status_via_grpc
        g = await run_in_threadpool(get_status_via_grpc, queue_id)
        if g is not None and g.get("queue_id"):
            return g
    except Exception:
        pass
    q = await run_in_threadpool(query_one, "SELECT id, status, result, stdout, error, timing_ms, memory_kb, solution_id FROM execution_queue WHERE id = %s", (queue_id,))
    if not q:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"queue_id": q["id"], "status": q["status"], "result": q["result"] or "", "stdout": q["stdout"] or "", "error": q["error"] or "", "timing_ms": q["timing_ms"], "memory_kb": q["memory_kb"], "solution_id": q["solution_id"]}


@router.get("/files/{problem_id}")
async def files_list(problem_id: int, request: Request):
    include_inactive = request.query_params.get("include_inactive", "").lower() in ("true", "1")
    if include_inactive:
        rows = await run_in_threadpool(query, "SELECT filename, code, last_ran, active FROM auto_saves WHERE problem_id = %s ORDER BY filename", (problem_id,))
        return rows if rows else []
    return await run_in_threadpool(list_files, problem_id)


@router.post("/files/{problem_id}", dependencies=[Depends(_require_write_auth)])
async def files_create(problem_id: int, request: Request):
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)
    filename = str(data.get("filename", "main.py"))
    code = str(data.get("code", ""))
    await run_in_threadpool(create_file, problem_id, filename, code)
    return {"status": "ok", "filename": filename}


@router.put("/files/{problem_id}/{filename:path}", dependencies=[Depends(_require_write_auth)])
async def files_save(problem_id: int, filename: str, request: Request):
    form = await request.form()
    code = str(form.get("code", ""))
    await run_in_threadpool(save_code, problem_id, code, filename)
    return {"status": "ok"}


@router.delete("/files/{problem_id}/{filename:path}", dependencies=[Depends(_require_write_auth)])
async def files_delete(problem_id: int, filename: str):
    await run_in_threadpool(delete_file, problem_id, filename)
    return {"status": "ok"}


@router.post("/files/{problem_id}/{old_filename:path}/rename", dependencies=[Depends(_require_write_auth)])
async def files_rename(problem_id: int, old_filename: str, request: Request):
    try:
        data = await request.json()
    except Exception:
        form = await request.form()
        data = dict(form)
    new_filename = str(data.get("filename", "main.py"))
    await run_in_threadpool(rename_file, problem_id, old_filename, new_filename)
    return {"status": "ok"}


@router.post("/save/{contest_id}/{index}", dependencies=[Depends(_require_write_auth)])
async def save_code_api(contest_id: int, index: str, request: Request):
    problem = await run_in_threadpool(get_problem, contest_id, index)
    if not problem:
        return JSONResponse({"error": "not found"}, status_code=404)
    # handle both form and text/plain (sendBeacon)
    content_type = request.headers.get("content-type", "")
    if "text/plain" in content_type:
        body = (await request.body()).decode()
        parsed = parse_qs(body)
        code = parsed.get("code", [""])[0]
        filename = parsed.get("filename", ["main.py"])[0]
    else:
        form = await request.form()
        code = str(form.get("code", ""))
        filename = str(form.get("filename", "main.py"))
    await run_in_threadpool(save_code, problem["id"], code, filename)
    return {"status": "ok"}


@router.get("/auto-save/{problem_id}")
async def auto_save_get(problem_id: int, request: Request):
    filename = request.query_params.get("filename", "main.py")
    data = await run_in_threadpool(load_code, problem_id, filename)
    return {"code": data["code"] or "", "last_ran": data["last_ran"] or ""}


@router.get("/images/{filename:path}")
async def image_get(filename: str):
    row = await run_in_threadpool(get_image, filename)
    if not row:
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(content=row["data"], media_type=row["content_type"] or "image/png", headers={"X-Content-Type-Options": "nosniff"})


@router.post("/images", dependencies=[Depends(_require_write_auth)])
async def image_upload(request: Request):
    data = await request.json()
    if not data or not data.get("filename") or not data.get("data"):
        return JSONResponse({"error": "missing filename or data"}, status_code=400)
    content_type = data.get("content_type", "image/png")
    if content_type not in _ALLOWED_IMAGE_TYPES:
        return JSONResponse({"error": "unsupported content type"}, status_code=400)
    try:
        raw = base64.b64decode(data["data"])
    except Exception as e:
        return JSONResponse({"error": f"invalid base64: {e}"}, status_code=400)
    await run_in_threadpool(create_image, data["filename"], raw, data.get("content_type", "image/png"))
    return {"status": "ok", "filename": data["filename"]}


@router.delete("/images/{filename:path}", dependencies=[Depends(_require_write_auth)])
async def image_delete(filename: str):
    await run_in_threadpool(delete_image, filename)
    return {"status": "deleted"}


@router.get("/images/exists/{filename:path}")
async def image_exists_api(filename: str):
    from shared.models import image_exists
    exists = await run_in_threadpool(image_exists, filename)
    return {"exists": exists}
