# SolveSpace

Codeforces problem-solving workspace. A scraper pipeline pulls Codeforces
problems, AI-enriches them, and uploads them to a private FastAPI app where
submitted code runs in a bwrap sandbox.

## How it works

```text
utilities/scraper/   Codeforces ──► DB   (4 stages: HTML → images → upload → enrichment)
solver_private/      FastAPI :8000       (problems, solutions, editor, execution API)
executor/            bwrap sandbox       (runs submitted code against test cases)
caddy/               :7031               (reverse proxy; no forward_auth — gate at the apex)
```

The scraper runs on the host and writes problems and their test cases into the same database the app serves from; stage 1 needs a real browser because Codeforces challenges the request. The app never executes submitted code itself — it hands the job to the sandbox, which runs it with no network and a memory limit, then writes the verdict back.

## Components

- `solver_private/` — the FastAPI app (problems, solutions, editor, execution
  API — `create_app()` factory, `APIRouter` x3, `granian` 1 worker, `RequestIDMiddleware`+`structlog` JSON, `{error:{code,message,request_id}}`). Serves on port `8000` inside the container, behind the apex wildcard gate (GateKeeper).
- `executor/` — bwrap sandbox that runs submitted/generated code against test
  cases and writes results to the DB.
- `shared/` — DB layer, models, base templates, static assets, wrapper code.
- `utilities/scraper/` — 4-stage scraper pipeline (scrape HTML → download
  images → upload images → AI enrichment + upload).
- `caddy/` — local reverse proxy: one published port, `7031`, fanning out to
  `solver_private:8000` and `solver_documentation:8005`. No `forward_auth` — the
  gate is at the apex wildcard (GateKeeper).
- `mysql/` — reserved for init scripts (currently empty).

## Ports

Only Caddy publishes a host port. Every other service is reachable solely across
the compose networks.

| Port | Service |
|---|---|
| 7031 | Caddy (`127.0.0.1:7031:7031`) — the only published port |
| 8000 | solver app (container-internal) |
| 8005 | documentation (container-internal, via Caddy `/documentation/*`) |
| 50051 | executor gRPC (container-internal, `expose` only) |
| 3306 | MySQL (container-internal) |
| 80 | phpMyAdmin (container-internal, `expose` only) |

## Environment

See `.env.example`. Required: `MYSQL_PASS` (compose fails fast without it).
Optional: `MYSQL_USER`, `MYSQL_DATABASE`, `API_TOKEN` (scraper + write API),
`ACCESS_CODE` (GateKeeper magic-link handshake), and the scraper's LLM settings —
`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` (all three wired as `${VAR:-}` in
`compose.yaml`). Leave the LLM settings blank to scrape without enrichment.

Variables are injected by compose — there is no `.env` file. For local runs,
`export` the vars in your shell.

## Run

    docker compose up -d --build

Scraper pipeline (on the host; stage 1 needs a browser for Cloudflare):

    python3 utilities/scraper/run.py 1234

## Tests

```bash
uv run --no-project --with-requirements shared/requirements.txt \
  --with-requirements requirements-dev.txt pytest -q
```

Covers app construction and the 404 render path (`tests/test_health.py`), the
`?`-placeholder shim over the DB layer (`tests/test_db_shim.py`), the model
queries against a throwaway SQLite database (`tests/test_models.py`), and the
bwrap sandbox — the sandbox cases skip where `bwrap` is unavailable
(`tests/test_executor_sandbox.py`).
