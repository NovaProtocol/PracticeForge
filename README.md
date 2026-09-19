# SolveSpace

Codeforces problem-solving workspace. A scraper pipeline pulls Codeforces
problems, AI-enriches them, and uploads them to a private FastAPI app where
submitted code runs in a bwrap sandbox.

## Components

- `solver_private/` — the FastAPI app (problems, solutions, editor, execution
  API — `create_app()` factory, `APIRouter` x3, `granian` 1 worker, `RequestIDMiddleware`+`structlog` JSON, `{error:{code,message,request_id}}`). Serves on port `8000` inside the container, behind the Caddy
  forward-auth gate (GateKeeper).
- `executor/` — bwrap sandbox that runs submitted/generated code against test
  cases and writes results to the DB.
- `shared/` — DB layer, models, base templates, static assets, wrapper code.
- `utilities/scraper/` — 4-stage scraper pipeline (scrape HTML → download
  images → upload images → AI enrichment + upload).
- `caddy/` — local reverse proxy: port `7031`, forward-auth gate, `/404`
  passthrough.
- `mysql/` — reserved for init scripts (currently empty).

## Ports

| Port | Service |
|---|---|
| 8000 | solver app (container-internal) |
| 7031 | local network via Caddy (`http://<host>:7031`) |
| 7032 | phpMyAdmin (loopback only) |
| 7033 | reserved |

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

None yet.
