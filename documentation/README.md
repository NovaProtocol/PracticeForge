# SolveSpace Documentation

MkDocs site for SolveSpace — served as a dedicated `documentation` container on `:8005` behind the Caddy gate.

## Local preview

```bash
pip install -r requirements.txt
mkdocs serve -a 127.0.0.1:8005
```

## Build

```bash
mkdocs build
```

Output goes to `site/` (gitignored, built inside the Docker image).

## Container

```bash
docker compose build documentation
docker compose up -d documentation
curl http://127.0.0.1:8005/health
```

Caddy exposes the site at `https://<host>/documentation/` (gated via
`forward_auth gatekeeper:7000` on `:7031`).

## Structure

- `mkdocs.yml` — Material theme, WBS-pattern config
- `docs/` — Markdown source (`index.md`, `getting-started.md`, `architecture.md` + solver/executor/scraper/etc)
- `requirements.txt` — mkdocs + material + plugins + FastAPI/granian
- `app.py` — FastAPI serving `site/` on `8005`
- `Dockerfile` — `python:3.14-slim`, `mkdocs build`, `USER appuser 10001`
