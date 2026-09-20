# Executor

Bwrap sandbox that runs submitted code against test cases and writes results to MySQL. Polls `execution_queue` every second, optionally woken via gRPC.

## Layout

```
executor/
 bwrap_executor.py # poll loop, bwrap invocation, wrapper orchestration
 grpc_server.py # gRPC ExecutorService (Enqueue, GetStatus, HealthCheck)
 Dockerfile # python:3.14-slim + bubblewrap, root + SYS_ADMIN, mem/pids/cpus limits
 requirements.txt # PyMySQL, cryptography, grpcio, protobuf
 wrapper.py (via shared/wrapper.py) # build_wrapper / parse_output
```

## Poll Loop

`bwrap_executor.py:main()`:

1. `become_subreaper()` via `prctl(PR_SET_CHILD_SUBREAPER)` so orphaned sandbox pids are reparented here and reaped (prevents zombie + pids cgroup saturation).
2. Connect MySQL, loop:
 - `fetch_queued()` → `SELECT * FROM execution_queue WHERE status='queued' ORDER BY id LIMIT 1`
 - `process_entry()` or `sleep(POLL_INTERVAL=1)` + `reap_orphans()`

`process_entry()`:

- `mark_running()`, fetch `executor_code` + `problem` row
- Parse `test_cases_json` (list/dict/str)
- If `exec_type` is `brute_force`/`submit_brute`: `generate_brute_force_test_cases()`, runs `generator_code` in sandbox, validates each case by running `solution_code` through `build_wrapper()` in sandbox
- Write user code to `/tmp/solver-<label>-<qid>.py`, build wrapper with `build_wrapper()`, run via `run_bwrap()` (bwrap + rlimits), `parse_output()` → `results_json`
- Run solution_code against same cases for timing comparison (`sol_timing`)
- `mark_completed()` with `result` JSON + `timing_ms`/`memory_kb`; if `submit` also `create_solution()` + set `solution_id` on queue row
- `reap_orphans()` in `finally`

## gRPC Integration

`executor/grpc_server.py` hosts `ExecutorService` on `0.0.0.0:50051` (internal `net-executor`). The server shares the DB layer, `EnqueueExecution` inserts the queue row and returns the `queue_id` immediately; the poll loop still drives execution (no duplicate execution). `GetExecutionStatus` reads the queue row; `HealthCheck` returns `ok`.

Solver dials it:

```python
from shared.grpc_client import enqueue_via_grpc

queue_id = enqueue_via_grpc(problem_id, code, method_name, test_cases_json, exec_type)
```

Best-effort: if gRPC is unavailable (test env, cold start) the HTTP route falls back to DB-only; the 1s poll still processes the entry.

See [Sandbox & gRPC](sandbox.md) for bwrap details and proto contract.
