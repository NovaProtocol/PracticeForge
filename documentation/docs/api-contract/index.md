# API Contract

## HTTP (public ingress via Caddy `:7031 → solver_private:8000`)

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | public | `{"status":"ok"}` |
| `GET` | `/404` | public | Themed 404 |
| `GET` | `/` | gated | Problems index |
| `GET` | `/problems/<cid>/<idx>` | gated | Problem detail |
| `GET` | `/solutions` | gated | Solutions list |
| `GET` | `/api/problems` | gated | List summaries |
| `GET` | `/api/problems/<cid>/<idx>` | gated | Problem detail + examples |
| `POST` | `/api/problems/upload` | gated / token | Upsert problem |
| `GET` | `/api/problems/exists/<cid>/<idx>` | gated | Exists check |
| `GET` | `/api/tags` | gated | All tags |
| `GET` | `/api/submissions/<pid>` | gated | Submissions for problem |
| `GET` | `/api/editorial/<pid>` | gated | Editorial |
| `POST` | `/api/run/<cid>/<idx>` | gated | Enqueue run |
| `POST` | `/api/brute-force/<cid>/<idx>` | gated | Enqueue brute_force |
| `POST` | `/api/submit/<cid>/<idx>` | gated | Enqueue submit_brute |
| `POST` | `/api/format` | gated | Black format |
| `POST` | `/api/re-run/<sid>` | gated | Re-run accepted |
| `GET` | `/api/queue-status/<qid>` | gated | Queue poll |
| `GET` | `/api/files/<pid>` | gated | List files |
| `POST` | `/api/files/<pid>` | gated | Create file |
| `PUT` | `/api/files/<pid>/<file>` | gated | Save file |
| `DELETE` | `/api/files/<pid>/<file>` | gated | Delete file |
| `POST` | `/api/files/<pid>/<old>/rename` | gated | Rename |
| `POST` | `/api/save/<cid>/<idx>` | gated | Beacon autosave |
| `GET` | `/api/auto-save/<pid>` | gated | Load autosave |
| `GET` | `/api/images/<file>` | gated | Image blob |
| `POST` | `/api/images` | gated | Upload image |
| `DELETE` | `/api/images/<file>` | gated | Delete image |
| `GET` | `/api/images/exists/<file>` | gated | Exists |
| `GET` | `/documentation/*` | gated | Docs site (`handle_path` → `solver_documentation:8005`) |

Caddy `handle /health` + `handle /404` are public; `handle_path /documentation/*` and `handle /*` are `forward_auth gatekeeper:7000`.

## gRPC (internal `net-executor`, `solver_executor:50051`)

Proto: `shared/proto/executor.proto`

```
service ExecutorService {
  rpc EnqueueExecution(EnqueueRequest) → EnqueueResponse;
  rpc GetExecutionStatus(GetStatusRequest) → GetStatusResponse;
  rpc HealthCheck(HealthCheckRequest) → HealthCheckResponse;
}
```

- Server: `solver_executor:50051` (`grpc.aio.server`, `add_insecure_port("0.0.0.0:50051")`)
- Client: `solver_private` via `grpc.aio.insecure_channel("solver_executor:50051")`
- Transport: `expose: ["50051"]` on `net-executor` (`internal: true`), never `ports`, never via Caddy.
- Auth: none (internal network isolation); add `x-internal-api-key` metadata if needed.

### EnqueueRequest

| Field | Type | Description |
|---|---|---|
| `problem_id` | int32 | Problem FK |
| `code` | string | Source code |
| `method_name` | string | e.g. `run` |
| `test_cases_json` | string | JSON list |
| `exec_type` | string | `run` / `brute_force` / `submit_brute` |

### GetExecutionStatus

Request `queue_id`; response `status`, `result`, `stdout`, `error`, `timing_ms`, `memory_kb`, `solution_id`.

### Flow

```
Browser POST /api/run → solver_private INSERT queue + gRPC Enqueue → executor poll → bwrap → UPDATE queue → browser poll GET /api/queue-status
```

HTTP is the public edge; gRPC is the internal notify. Both share the same service layer (`execution_queue` table).

## Port Summary

| Port | Service | Publish |
|---|---|---|
| 8000 | solver_private (HTTP + optional gRPC) | `expose` only |
| 7031 | Caddy gateway | via `cloudflared-tunnel_default` (no host `ports`) |
| 50051 | executor gRPC | `expose` only, `net-executor` internal |
| 8005 | documentation HTTP | `expose` only |
| 3306 | MySQL | `expose` only |
| 7032 | phpMyAdmin | `127.0.0.1:7032:80` loopback |

## Error Mapping

- gRPC `NOT_FOUND` → HTTP `404`
- gRPC `INVALID_ARGUMENT` → HTTP `400`
- gRPC `PERMISSION_DENIED` → HTTP `403`
- Business logic lives in `*_service.py` / `shared/models.py` — both transports call it, no duplication.
