# Sandbox & gRPC

## bwrap Sandbox

Executor runs user code with **bubblewrap** (`bwrap`), no fallback, sandbox failure is a loud `failed` queue status.

### Invocation

```python
BWRAP = "/usr/bin/bwrap"
PYTHON_BIN = "/usr/local/bin/python3" # resolved via _find_python()

cmd = [
 BWRAP,
 "--unshare-all", # user, net, ipc, pid, uts, cgroup, time
 "--die-with-parent",
 "--ro-bind", "/usr", "/usr",
 "--ro-bind", "/usr/local", "/usr/local",
 "--ro-bind", "/lib", "/lib",
 "--ro-bind", "/lib64", "/lib64",
 "--tmpfs", "/tmp",
 "--dev", "/dev",
 "--ro-bind", script_path, script_path,
 "--chdir", "/", PYTHON_BIN, script_path,
]
subprocess.run(cmd, env={}, preexec_fn=_set_rlimits, timeout=TIMEOUT)
```

- Sandboxed process gets **empty env** (`_bwrap_env() → {}`), no `MYSQL_*` secrets.
- Extra binds add the user code file when needed.

### rlimits (`_set_rlimits`)

Set in `preexec_fn` before exec, inherited by bwrap + child:

| Limit | Value | Notes |
|---|---|---|
| `RLIMIT_AS` | `MEMORY_LIMIT_MB*1024*1024` (default 1024) | Address space |
| `RLIMIT_NPROC` | `PROCESS_LIMIT` (default 64) | Not enforced as uid 0 in user ns, bounded by `pids_limit: 128` cgroup |
| `RLIMIT_CPU` | `CPU_LIMIT_SECONDS` (default 25) | CPU time |
| `RLIMIT_CORE` | `0` | No core dumps |

Failures to set a limit are logged but don't abort, cgroup limits back them up.

### Container Privileges

Required in `compose.yaml`:

```yaml
cap_add: [SYS_ADMIN]
security_opt: [seccomp:unconfined, apparmor:unconfined]
mem_limit: 1g
pids_limit: 128
cpus: "2"
```

`SYS_ADMIN` + `unconfined` are mandatory for `bwrap --unshare-all` user namespace creation. Documented tradeoff, sandboxed code itself is still empty-env + rlimits + no net.

### Wrapper (`shared/wrapper.py`)

`build_wrapper(user_code_path, method_name, test_cases, stop_on_failure, executor_code)` generates a Python script that:

1. `exec`s the user `Solution` class file
2. `exec`s `executor_code` (interactive judge helpers) with `HIDDEN`/`_queries` globals
3. Per test case: sets `HIDDEN` from `hidden`, calls `method(**input)`, matches `got` vs `expected` (numeric 1e-9 tolerance), captures `stdout` + `timing_ms`, appends to `results`

Emits `__SOLVER_RESULT__` + JSON.

### Subreaper & Zombie Reaping

```python
libc.prctl(PR_SET_CHILD_SUBREAPER, 1) # become subreaper
os.waitpid(-1, WNOHANG) # reap_orphans() between runs
```

Orphaned sandbox children are reparented to the executor instead of init and reaped, prevents pid cgroup exhaustion.

## gRPC Service

### Proto (`shared/proto/executor.proto`)

```protobuf
syntax = "proto3";
package practiceforge.v1;

service ExecutorService {
 rpc EnqueueExecution(EnqueueRequest) returns (EnqueueResponse);
 rpc GetExecutionStatus(GetStatusRequest) returns (GetStatusResponse);
 rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
}

message EnqueueRequest {
 int32 problem_id = 1;
 string code = 2;
 string method_name = 3;
 string test_cases_json = 4;
 string exec_type = 5;
}
message EnqueueResponse { int64 queue_id = 1; string status = 2; }

message GetStatusRequest { int64 queue_id = 1; }
message GetStatusResponse {
 int64 queue_id = 1; string status = 2; string result = 3;
 string stdout = 4; string error = 5; int32 timing_ms = 6;
 int32 memory_kb = 7; int64 solution_id = 8;
}
message HealthCheckRequest {}
message HealthCheckResponse { string status = 1; }
```

Place in `shared/proto/`, generate to `shared/proto_gen/`:

```bash
python -m grpc_tools.protoc -I shared/proto --python_out=shared/proto_gen --grpc_python_out=shared/proto_gen shared/proto/executor.proto
```

### Server (`executor/grpc_server.py`)

```python
import grpc
from shared.proto_gen import executor_pb2, executor_pb2_grpc

class ExecutorServicer(executor_pb2_grpc.ExecutorServiceServicer):
 async def EnqueueExecution(self, request, context):
 # INSERT INTO execution_queue ...; return queue_id
 async def GetExecutionStatus(self, request, context):
 # SELECT FROM execution_queue WHERE id=...
 async def HealthCheck(self, request, context):
 return executor_pb2.HealthCheckResponse(status="ok")

async def serve():
 server = grpc.aio.server()
 executor_pb2_grpc.add_ExecutorServiceServicer_to_server(ExecutorServicer(), server)
 server.add_insecure_port("0.0.0.0:50051")
 await server.start()
 await server.wait_for_termination()
```

Runs alongside the poll loop (async task). Port `50051` is `expose` only on `net-executor` (`internal: true`).

### Client (`shared/grpc_client.py` / `solver_private/grpc_client.py`)

```python
import grpc
from shared.proto_gen import executor_pb2, executor_pb2_grpc

async def enqueue_via_grpc(problem_id, code, method_name, test_cases_json, exec_type):
 async with grpc.aio.insecure_channel("practiceforge_executor:50051") as ch:
 stub = executor_pb2_grpc.ExecutorServiceStub(ch)
 resp = await stub.EnqueueExecution(executor_pb2.EnqueueRequest(...))
 return resp.queue_id
```

For sync callers (executor poll, startup), a sync stub using `grpc.insecure_channel` is provided; FastAPI routes use `grpc.aio.insecure_channel` via `run_in_threadpool` bridge (`shared/grpc_client.py`).

### Compose Wiring

```yaml
executor:
 expose: ["50051"]
 networks: [default, net-executor]
practiceforge_app:
 environment: { EXECUTOR_GRPC_ADDR: "practiceforge_executor:50051" }
 networks: [default, net-executor]
networks:
 net-executor: { internal: true }
```

Caddy never proxies `50051`; browsers never dial it.
