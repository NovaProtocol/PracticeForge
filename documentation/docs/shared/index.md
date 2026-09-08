# Shared

Cross-sector library imported via `PYTHONPATH=/app/shared` in every app image.

## Packages

| File | Purpose |
|---|---|
| `config.py` | `Settings(BaseSettings)` + `get_config()` (`pydantic-settings`, `DEPLOYMENT_TYPE`→`DEBUG`, `db_url`/`async_db_url` aiomysql, no `SECRET_KEY` — no sessions) |
| `db.py` | SQLAlchemy engine/session, PyMySQL shim (`%s`→`:pN`) |
| `sqlalchemy_models.py` | Declarative models |
| `models.py` | Query helpers (`get_problem`, `get_solution`, …) |
| `startup.py` | `Base.metadata.create_all()` |
| `wrapper.py` | `build_wrapper()` / `parse_output()` — sandbox wrapper generation |
| `proto/executor.proto` | gRPC contract |
| `proto_gen/` | Generated stubs |
| `grpc_client.py` | Shared gRPC client helpers |
| `templates/base.html` | Base layout |
| `static/` | `css/` + `js/` |

## DB Layer (`db.py`)

- Dual engine: `get_engine()` (sync `mysql+pymysql`, `pool_pre_ping`/`pool_recycle=300`) for executor/startup + `get_async_engine()`/`get_async_sessionmaker()`/`get_db()` (`create_async_engine` `mysql+aiomysql` / `sqlite+aiosqlite` for tests, `pool_pre_ping`, `async_sessionmaker`) for FastAPI — `lifespan` warms async engine.
- `query`/`query_one`/`execute` (sync) + `async_query`/`async_query_one`/`async_execute` keep PyMySQL `%s` placeholders — `_convert()` rewrites to `:pN` for SQLAlchemy `text()`; routes use `run_in_threadpool` bridge for sync `shared/models.py`.
- `pool_pre_ping=True` on both engines.

## Models (`sqlalchemy_models.py`)

See [Models & DB](models.md).

## Wrapper (`wrapper.py`)

Used by both `executor/bwrap_executor.py` and `utilities/scraper/ai.py` so validation and execution are identical. Generates a Python script that execs user code, sets `HIDDEN`, calls `Solution.<method>(**input)`, matches `got` vs `expected` with `1e-9` numeric tolerance, emits `__SOLVER_RESULT__`.

## gRPC

Proto in `shared/proto/executor.proto`, stubs in `shared/proto_gen/`, client in `shared/grpc_client.py`. See [Executor gRPC](../executor/sandbox.md).

## Errors & Observability

- `shared/middleware.py` `RequestIDMiddleware` — binds `request_id` into `structlog.contextvars`, echoes `X-Request-ID` (exposed via `Access-Control-Expose-Headers`), installed first so even 401s correlate.
- `shared/errors.py` `install_error_handlers` — `StarletteHTTPException`/`RequestValidationError`/`grpc.aio.AioRpcError`/`Exception` → `{error:{code,message,request_id}}` (`details` on validation, `503 UPSTREAM_UNAVAILABLE` on gRPC — no fallback) + `structlog` JSON to stdout (`docker compose logs` / `scripts/docker.sh logs`).
- `shared/static/js/error.js` — `window.onerror` + `unhandledrejection` + `apiFetch(url,opts)` wrapper that `console.error({message,stack,url,method,status,request_id,body,timestamp})` + short toast (`message [request_id]`); loaded by `shared/templates/base.html` (`<script src="/static/js/error.js">`).

## Templates & Static

`templates/base.html` is the site layout; solver's `ChoiceLoader` (`apps/templating.py` `Jinja2Templates` + `ChoiceLoader([solver_private/templates, shared/templates])` + `url_for` shim) merges it without requiring the Docker copy on host. Static lives in `shared/static/` and is copied to `/app/static` in images.
