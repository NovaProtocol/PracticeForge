# Getting Started

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Docker & Docker Compose | Latest | All services |
| Python | 3.14 | Local dev, scraper, tests |
| Bubblewrap (`bwrap`) | Latest | Executor sandbox (container has it) |
| MySQL client (optional) | 8.4 | Direct DB inspection |

## 1. Clone & Configure

```bash
git clone <repo-url> SolveSpace
cd SolveSpace
cp .env.example .env   # docs only — real vars come from compose interpolation
```

Key variables (full list in `.env.example`, source of truth):

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEPLOYMENT_TYPE` | yes | — | `DEBUG` or `PRODUCTION` |
| `MYSQL_PASS` | yes | — | MySQL root password (compose fails fast if missing) |
| `MYSQL_USER` | no | `root` | DB user |
| `MYSQL_DATABASE` | no | `solvespace` | DB name |
| `API_TOKEN` | no | — | Scraper + write API token |
| `EXECUTOR_GRPC_ADDR` | no | `solver_executor:50051` | Internal gRPC address (solver → executor) |
| `GRPC_PORT` | no | `50051` | Executor gRPC listen port |
| `MEMORY_LIMIT_MB` | no | `1024` | Sandbox memory hard limit |
| `PROCESS_LIMIT` | no | `64` | Sandbox nproc limit (capped by pids cgroup) |
| `CPU_LIMIT_SECONDS` | no | `25` | Sandbox CPU limit |
| `ZEN_API_KEY` | no | — | Scraper AI enrichment key |

> Every required var uses `${VAR:?}` in `compose.yaml` — missing = `docker compose up` refuses to start. There is no `.env` file at runtime; export vars in your shell or deployment tool.

## 2. Start All Services

```bash
docker compose up -d --build
```

First build pulls `python:3.14-slim`, `mysql:8.4`, `caddy:2-alpine`, `phpmyadmin:5.2` and builds the three app images.

Check health:

```bash
docker compose ps
curl -s http://127.0.0.1:7031/health || curl -s http://solver_private:8000/health
docker compose logs -f solver_private solver_executor solver_documentation
```

## 3. Access the System

| URL | Service | Gate |
|---|---|---|
| `http://<host>:7031/` | Solver app | gated |
| `http://<host>:7031/health` | Health (solver) | public |
| `http://<host>:7031/404` | Themed 404 | public |
| `http://<host>:7031/documentation/` | Docs site | gated |
| `http://127.0.0.1:7032/` | phpMyAdmin | loopback only |
| `solver_executor:50051` | Executor gRPC | internal only (`expose`, no `ports`) |

Gate means `forward_auth gatekeeper:7000 { uri /api/authz/forward-auth }` — present a valid `gatekeeper_token` cookie or `?access_code=` magic link.

## 4. Scraper Pipeline (host)

Stage 1 needs a browser for Cloudflare:

```bash
python3 utilities/scraper/run.py 1234          # scrape contest 1234
python3 utilities/scraper/run.py --help
```

Stages: `scrape` → `images_download` → `images_upload` → `ai` (AI enrichment + upload via `POST /api/problems/upload`).

## 5. Development Workflow

### Run solver locally

```bash
export DEPLOYMENT_TYPE=DEBUG
export MYSQL_HOST=127.0.0.1
export MYSQL_PASS=SolveSpace
python solver_private/run.py --mode debug   # uvicorn factory=True --reload
# or: granian --interface asgi --host 0.0.0.0 --port 8000 --workers 1 wsgi:app  (from solver_private/)
```

### Run executor locally

```bash
export DEPLOYMENT_TYPE=DEBUG
export MYSQL_HOST=127.0.0.1
python executor/bwrap_executor.py
```

### Run docs locally

```bash
pip install -r documentation/requirements.txt
mkdocs serve -a 127.0.0.1:8005
# or via container
docker compose up -d documentation
curl http://127.0.0.1:8005/health
```

### Tests

```bash
pytest
pre-commit run --all-files
```

## 6. gRPC Development

Proto lives at `shared/proto/executor.proto`, generated stubs at `shared/proto_gen/`.

Regenerate after editing the proto:

```bash
python -m grpc_tools.protoc -I shared/proto --python_out=shared/proto_gen --grpc_python_out=shared/proto_gen shared/proto/executor.proto
```

Solver dials the executor:

```python
import grpc
from shared.proto_gen import executor_pb2, executor_pb2_grpc

async with grpc.aio.insecure_channel("solver_executor:50051") as ch:
    stub = executor_pb2_grpc.ExecutorServiceStub(ch)
    resp = await stub.EnqueueExecution(executor_pb2.EnqueueRequest(problem_id=1, code="..."))
```
