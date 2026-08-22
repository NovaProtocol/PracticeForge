# Solver Private

Flask app serving problems, solutions, editor, and execution API. Runs on `solver_private:7030` behind the Caddy gate (`:7031`).

## Layout

```
solver_private/
  app.py                # create_app() factory, ChoiceLoader for shared/templates
  apps/
    problems/routes.py  # list, detail, editor, console
    solutions/routes.py # list, detail, re-run
    api/routes.py       # REST API used by scraper + browser + gRPC client
  templates/404.html    # themed 404, bypasses gate via Caddy handle /404
  Dockerfile            # python:3.14-slim, gunicorn gthread, USER appuser
```

## App Factory

`app.py:create_app()`:

- `run_startup()` → `Base.metadata.create_all(get_engine())`
- `Flask(template_folder=solver_private/templates)` with `ChoiceLoader([solver_templates, shared/templates])` so host runs resolve `base.html` without the Docker `COPY shared/templates → /app/templates` layer
- `app.config.from_object(ProductionConfig)` + `ProxyFix(x_for=1, x_proto=1)`
- Registers `problems_blueprint`, `solutions_blueprint`, `api_blueprint`
- `/health` → `{"status":"ok"}` (public), `/404` → themed page, `@app.errorhandler(404)` → same template

## Blueprints

| Blueprint | Prefix | Purpose |
|---|---|---|
| `problems` | `/` | Problem index, detail with description/editor/console tabs, per-file autosave |
| `solutions` | `/solutions` | Solution history, detail, re-run on examples |
| `api` | `/api` | Machine API: problems, solutions, files, images, execution queue |

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

`shared/config.py`: `BaseConfig` / `ProductionConfig` (house style — env via compose interpolation, no `.env` file). The factory reads `ProductionConfig` directly; dev runs set `DEPLOYMENT_TYPE=DEBUG` but the config class is still `ProductionConfig` with `DEBUG=False` (behavior switch is in the executor's poll logging, not the solver).

## Static & Templates

- `shared/templates/base.html` — top-level layout
- `shared/static/css/*` + `shared/static/js/*` — base, editor, console, description, etc.
- In Docker: `COPY shared/templates /app/templates` + `COPY shared/static /app/static`; on host the `ChoiceLoader` fallback finds them.
