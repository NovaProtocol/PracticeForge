# Docker Infrastructure

## compose.yaml

Single `compose.yaml` orchestrates the whole stack.

```yaml
services:
  practiceforge_app: { build: solver_private/Dockerfile, container_name: practiceforge_app, expose: [8000], networks: [default, net-executor], healthcheck: urllib 8000/health, env: DEPLOYMENT_TYPE+MYSQL_*+API_TOKEN+LLM_* }
 practiceforge_executor: { build: executor/Dockerfile, container_name: practiceforge_executor, expose: [50051], networks: [default, net-executor], cap_add: [SYS_ADMIN], pids_limit: 128 }
 practiceforge_documentation: { build: documentation/Dockerfile, container_name: practiceforge_documentation, expose: [8005], networks: [default], healthcheck: 8005/health }
 practiceforge_mysql: { image: mysql:8.4, container_name: practiceforge_mysql, volumes: [mysql_data], healthcheck: mysqladmin ping }
 practiceforge_phpmyadmin: { image: phpmyadmin:5.2, expose: [80], networks: [default] }
 practiceforge_caddy: { build: caddy/Dockerfile, container_name: practiceforge_caddy, ports: [127.0.0.1:7031:7031], networks: [default, gatekeeper] }
networks:
 default: {}
 net-executor: { internal: true }
 gatekeeper: { external: true, name: gatekeeper }
volumes: { mysql_data: }
```

- Every app has `restart: unless-stopped`.
- Secrets via `${VAR:?}` interpolation, no `.env` file.
- `net-executor` is `internal: true`, only solver ↔ executor gRPC.

## Dockerfiles

| Service | Base | Key steps |
|---|---|---|
| practiceforge_app | `python:3.14-slim` | `PYTHONPATH=/app/shared:/app`, `apt gcc`, `pip shared/requirements`, `COPY shared` + `COPY practiceforge_app`, `compileall`, `USER appuser 10001`, `EXPOSE 8000`, `HEALTHCHECK urllib 8000/health`, `granian asgi 1 worker wsgi:app` |
| executor | `python:3.14-slim` | `apt bubblewrap`, `pip executor/requirements`, `COPY bwrap_executor + grpc_server`, `COPY shared/wrapper.py`, `CMD python bwrap_executor.py` (root) |
| documentation | `python:3.14-slim` | `pip shared/requirements + docs/requirements`, `COPY documentation`, `mkdocs build`, `USER appuser 10001`, `EXPOSE 8005`, `granian asgi` |
| caddy | `caddy:2-alpine` | `COPY Caddyfile` |

All use `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `--no-cache-dir`, `rm -rf /var/lib/apt/lists/*`.

## Caddyfile (`caddy/Caddyfile`)

```caddy
:7031 {
 handle /health {
 reverse_proxy practiceforge_app:8000
 }
 handle_path /documentation/* {
 reverse_proxy practiceforge_documentation:8005
 }
 handle {
 reverse_proxy practiceforge_app:8000
 }
}
```

- Live `caddy/Caddyfile` has 3 handles (`/health`, `/documentation/*`, catch-all), **zero per-app `forward_auth`** (the apex wildcard on `gatekeeper` decides; see live `Caddyfile`).
- Site address is the project port `:7031`; proxy targets are **container_name** (`practiceforge_app:8000`, `practiceforge_documentation:8005`).
- `/documentation/*` uses `handle_path` (strips prefix) so the docs app sees `/`.
- Single Caddyfile, always deployment config.

## MySQL

`image: mysql:8.4`, `container_name: practiceforge_mysql`, `MYSQL_ROOT_PASSWORD=${MYSQL_PASS:?}`, `MYSQL_DATABASE=${MYSQL_DATABASE:-practiceforge}`, `mysql_data:/var/lib/mysql`, `healthcheck: mysqladmin ping`.

phpMyAdmin `5.2` on the compose `default` network (`expose: [80]`, not published), `PMA_HOST=mysql`, `PMA_USER=${MYSQL_USER:-root}`.
