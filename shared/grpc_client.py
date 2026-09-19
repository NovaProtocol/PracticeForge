from __future__ import annotations

import grpc

try:
    from shared.proto_gen import executor_pb2, executor_pb2_grpc
except ImportError:  # fallback
    import executor_pb2  # type: ignore
    import executor_pb2_grpc  # type: ignore


def _grpc_addr() -> str:
    from shared.config import get_config

    return get_config().EXECUTOR_GRPC_ADDR


async def enqueue_via_grpc_async(
    problem_id: int,
    code: str,
    method_name: str = "run",
    test_cases_json: str = "[]",
    exec_type: str = "run",
    timeout: float = 5.0,
) -> int | None:
    """Async gRPC enqueue — use from async context (FastAPI/granian)."""
    addr = _grpc_addr()
    try:
        async with grpc.aio.insecure_channel(addr) as ch:
            stub = executor_pb2_grpc.ExecutorServiceStub(ch)
            resp = await stub.EnqueueExecution(
                executor_pb2.EnqueueRequest(
                    problem_id=int(problem_id),
                    code=code,
                    method_name=method_name or "run",
                    test_cases_json=test_cases_json or "[]",
                    exec_type=exec_type or "run",
                ),
                timeout=timeout,
            )
            return int(resp.queue_id) if resp.queue_id else None
    except grpc.aio.AioRpcError:
        return None


def enqueue_via_grpc(
    problem_id: int,
    code: str,
    method_name: str = "run",
    test_cases_json: str = "[]",
    exec_type: str = "run",
    timeout: float = 5.0,
) -> int | None:
    """Sync gRPC enqueue — safe for Flask (solver_private) routes."""
    addr = _grpc_addr()
    try:
        with grpc.insecure_channel(addr) as ch:
            stub = executor_pb2_grpc.ExecutorServiceStub(ch)
            resp = stub.EnqueueExecution(
                executor_pb2.EnqueueRequest(
                    problem_id=int(problem_id),
                    code=code,
                    method_name=method_name or "run",
                    test_cases_json=test_cases_json or "[]",
                    exec_type=exec_type or "run",
                ),
                timeout=timeout,
            )
            return int(resp.queue_id) if resp.queue_id else None
    except grpc.RpcError:
        return None


def get_status_via_grpc(queue_id: int, timeout: float = 5.0) -> dict | None:
    """Sync status fetch via gRPC — returns dict or None on miss/error."""
    addr = _grpc_addr()
    try:
        with grpc.insecure_channel(addr) as ch:
            stub = executor_pb2_grpc.ExecutorServiceStub(ch)
            resp = stub.GetExecutionStatus(
                executor_pb2.GetStatusRequest(queue_id=int(queue_id)),
                timeout=timeout,
            )
            # NOT_FOUND returns empty + context code, handled as exception above
            return {
                "queue_id": int(resp.queue_id),
                "status": resp.status,
                "result": resp.result,
                "stdout": resp.stdout,
                "error": resp.error,
                "timing_ms": int(resp.timing_ms),
                "memory_kb": int(resp.memory_kb),
                "solution_id": int(resp.solution_id),
            }
    except grpc.RpcError:
        return None


async def get_status_via_grpc_async(queue_id: int, timeout: float = 5.0) -> dict | None:
    addr = _grpc_addr()
    try:
        async with grpc.aio.insecure_channel(addr) as ch:
            stub = executor_pb2_grpc.ExecutorServiceStub(ch)
            resp = await stub.GetExecutionStatus(
                executor_pb2.GetStatusRequest(queue_id=int(queue_id)),
                timeout=timeout,
            )
            return {
                "queue_id": int(resp.queue_id),
                "status": resp.status,
                "result": resp.result,
                "stdout": resp.stdout,
                "error": resp.error,
                "timing_ms": int(resp.timing_ms),
                "memory_kb": int(resp.memory_kb),
                "solution_id": int(resp.solution_id),
            }
    except grpc.aio.AioRpcError:
        return None
