# Solver API Reference

Base path `/api` (via Caddy `handle /*` → `solver_private:8000`).

## Problems

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/problems` | List summaries (no large HTML) |
| `GET` | `/api/problems/<cid>/<idx>` | Full problem (adds `examples`, `constraints` arrays) |
| `POST` | `/api/problems/upload` | Upsert problem (scraper) — `{contest_id, problem_index, title, ...}` |
| `GET` | `/api/problems/exists/<cid>/<idx>` | Existence check |

## Solutions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/solutions` | List with join on problems |
| `GET` | `/api/solutions/<id>` | Detail + `test_results` + `stdout` from queue |

## Execution

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/run/<cid>/<idx>` | Enqueue `run` (examples) — form `code`, `filename`, `testcases` |
| `POST` | `/api/brute-force/<cid>/<idx>` | Enqueue `brute_force` (generator) |
| `POST` | `/api/submit/<cid>/<idx>` | Enqueue `submit_brute` (generator + verdict + solution row) |
| `POST` | `/api/format` | Black format — form `code` |
| `POST` | `/api/re-run/<solution_id>` | Re-run accepted solution on examples |
| `GET` | `/api/queue-status/<qid>` | Poll `execution_queue` row |

All enqueue routes do:

1. `get_problem(cid, idx)` → 404 if missing
2. `save_last_ran(problem_id, code, filename)`
3. `INSERT INTO execution_queue (queued)` → `queue_id`
4. Best-effort `grpc EnqueueExecution` to `solver_executor:50051`
5. Return `{"queue_id":…, "status":"queued"}`

## Files (autosave)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/files/<pid>` | List active files for problem |
| `POST` | `/api/files/<pid>` | Create file `{filename, code}` |
| `PUT` | `/api/files/<pid>/<filename>` | Save code |
| `DELETE` | `/api/files/<pid>/<filename>` | Soft-delete |
| `POST` | `/api/files/<pid>/<old>/rename` | Rename |
| `POST` | `/api/save/<cid>/<idx>` | Beacon autosave (handles `text/plain` body) |
| `GET` | `/api/auto-save/<pid>?filename=` | Load code + last_ran |

## Images

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/images/<filename>` | Blob + `content_type`, `X-Content-Type-Options: nosniff` |
| `POST` | `/api/images` | Upload `{filename, data (base64), content_type}` |
| `DELETE` | `/api/images/<filename>` | Delete |
| `GET` | `/api/images/exists/<filename>` | Existence |

Allowed `content_type`: `image/png`, `image/jpeg`, `image/gif`, `image/webp`, `image/bmp`.

## Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{"status":"ok"}` — public, no gate |
| `GET` | `/404` | Themed 404 page — public |

## gRPC (internal)

See [Executor gRPC](../executor/sandbox.md) and [API Contract](../api-contract/index.md).

- Proto: `shared/proto/executor.proto`
- Server: `solver_executor:50051` (`grpc.aio.server`, `expose` only)
- Client: `solver_private` via `grpc.aio.insecure_channel("solver_executor:50051")`
- Methods: `EnqueueExecution`, `GetExecutionStatus`, `HealthCheck`
