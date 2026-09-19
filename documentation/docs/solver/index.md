# Solver Private

FastAPI app serving problems, solutions, editor, and execution API. Runs on `solver_private:8000` behind the Caddy gate (`:7031`, `127.0.0.1:7031:7031`).

## Layout

```
solver_private/
 app.py # create_app() factory, lifespan, RequestIDMiddleware+structlog, Jinja ChoiceLoader
 apps/
 problems/routes.py # APIRouter `/` — list, detail, editor, console (HTMLResponse)
 solutions/routes.py # APIRouter `/solutions` — list, detail, re-run
 api/routes.py # APIRouter `/api` — REST API used by scraper + browser + gRPC client
 apps/templating.py # Jinja2 Environment + ChoiceLoader, Flask url_for shim
 wsgi.py # granian target `wsgi:app` (create_app())
 run.py # dev uvicorn factory=True --reload
 templates/404.html # themed 404, bypasses gate via Caddy handle /404
 Dockerfile # python:3.14-slim, granian asgi 1 worker, USER appuser
```

## App Factory

`app.py:create_app()` (a `FastAPI` factory):

- `lifespan` → `run_startup()` (`Base.metadata.create_all(get_engine())`) + warm `get_async_engine()` (aiomysql)
- `_build_templates()` / `apps/templating.py` — `ChoiceLoader([apps/problems/templates, apps/solutions/templates, solver_templates, shared/templates])` so host runs resolve `base.html` and blueprint pages like `problems/index.html` without the Docker `COPY shared/templates → /app/templates` layer; `url_for` shim for legacy templates
- `RequestIDMiddleware` first (so even 401s echo `X-Request-ID`), `StaticFiles` at `/static`, `include_router` x3 (`problems`, `solutions`, `api`)
- `install_error_handlers` (`shared/errors.py`) — `{error:{code,message,request_id}}` + `structlog` JSON + `X-Request-ID` (see Errors below)
- `/health` → `{"status":"ok"}` (async engine `SELECT 1`, `503 degraded` on DB failure), `/404` → themed `404.html`

## Blueprints

| Router (`APIRouter`) | Prefix | Purpose |
|---|---|---|
| `problems` (`apps/problems/routes.py`) | `/` | Problem index, detail with description/editor/console tabs, per-file autosave — `HTMLResponse` via `apps.templating.templates` |
| `solutions` (`apps/solutions/routes.py`) | `/solutions` | Solution history, detail, re-run on examples |
| `api` (`apps/api/routes.py`) | `/api` | Machine API: problems, solutions, files, images, execution queue — `run_in_threadpool` bridge for sync `shared/models.py` |

## Errors

`shared/errors.py` + `shared/middleware.py` + `shared/static/js/error.js`:

- **Server:** `RequestIDMiddleware` binds `request_id` into `structlog.contextvars`, echoes `X-Request-ID`; `install_error_handlers` maps `StarletteHTTPException`/`RequestValidationError`/`grpc.aio.AioRpcError`/`Exception` to `{error:{code,message,request_id}}` (`details` on validation, `503 UPSTREAM_UNAVAILABLE` on gRPC failure — no fallback) and `structlog` JSON to container stdout (`docker compose logs` / `scripts/docker.sh logs`).
- **Browser:** `/static/js/error.js` (`window.onerror` + `unhandledrejection` + `apiFetch` wrapper) logs `console.error({message,stack,url,method,status,request_id,body,timestamp})` + short toast (`message [request_id]`); loaded by `shared/templates/base.html`.

## gRPC Client

`solver_private/grpc_client.py` (and `shared/grpc_client.py`) dials the executor:

```python
import grpc
from shared.proto_gen import executor_pb2, executor_pb2_grpc

async with grpc.aio.insecure_channel("solver_executor:50051") as ch:
 stub = executor_pb2_grpc.ExecutorServiceStub(ch)
 resp = await stub.EnqueueExecution(executor_pb2.EnqueueRequest(...))
```

The HTTP routes always insert the `execution_queue` row; the gRPC call is a low-latency notify (best-effort — if the channel is unavailable the executor's 1s poll still picks up the row).

## Configuration

`shared/config.py`: `Settings(BaseSettings)` (`pydantic-settings`) — env via compose interpolation, no `.env` file. No `SECRET_KEY`/`JWT`: SolveSpace has no sessions, so there is nothing to sign. `get_config()` (`@lru_cache`) + `db_url`/`async_db_url` (`+pymysql` → `+aiomysql`, `sqlite` → `aiosqlite` for tests). `shared/db.py` exposes `get_engine()` (sync, `pool_pre_ping`) + `get_async_engine()`/`get_db()` (`create_async_engine` aiomysql, `async_sessionmaker`, `lifespan` warmup).

## Static & Templates

- `shared/templates/base.html` — top-level layout
- `shared/static/css/*` + `shared/static/js/*` — base, editor, console, description, etc.
- In Docker: `COPY shared/templates /app/templates` + `COPY shared/static /app/static`; on host the `ChoiceLoader` fallback finds them.
