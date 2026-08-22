# Shared

Cross-sector library imported via `PYTHONPATH=/app/shared` in every app image.

## Packages

| File | Purpose |
|---|---|
| `config.py` | `BaseConfig` / `ProductionConfig` |
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

- Lazy engine: `get_engine()` builds `mysql+pymysql://` DSN from `MYSQL_*` env on first use.
- `query(sql, params)` / `query_one` / `execute` keep PyMySQL `%s` placeholders — `_convert()` rewrites to `:pN` for SQLAlchemy `text()`.
- `pool_pre_ping=True`, `pool_recycle=300`.

## Models (`sqlalchemy_models.py`)

See [Models & DB](models.md).

## Wrapper (`wrapper.py`)

Used by both `executor/bwrap_executor.py` and `utilities/scraper/ai.py` so validation and execution are identical. Generates a Python script that execs user code, sets `HIDDEN`, calls `Solution.<method>(**input)`, matches `got` vs `expected` with `1e-9` numeric tolerance, emits `__SOLVER_RESULT__`.

## gRPC

Proto in `shared/proto/executor.proto`, stubs in `shared/proto_gen/`, client in `shared/grpc_client.py`. See [Executor gRPC](../executor/sandbox.md).

## Templates & Static

`templates/base.html` is the site layout; solver's `ChoiceLoader` merges it without requiring the Docker copy on host. Static lives in `shared/static/` and is copied to `/app/static` in images.
