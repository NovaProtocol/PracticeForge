from __future__ import annotations

import asyncio
import logging
import os

import grpc

from shared.db import execute, query_one

try:
    from shared.proto_gen import executor_pb2, executor_pb2_grpc
except ImportError:  # fallback when PYTHONPATH differs
    import executor_pb2  # type: ignore
    import executor_pb2_grpc  # type: ignore

logger = logging.getLogger(__name__)


class ExecutorServicer(executor_pb2_grpc.ExecutorServiceServicer):
    """gRPC servicer, delegates to shared DB layer, same as HTTP routes."""

    async def EnqueueExecution(self, request, context):  # type: ignore[no-untyped-def]
        try:
            if not request.code:
                await context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                await context.set_details("code is required")
                return executor_pb2.EnqueueResponse()
            # exec_type validation mirrors execution_queue ENUM
            if request.exec_type not in ("run", "submit", "brute_force", "submit_brute", ""):
                await context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                await context.set_details(f"invalid exec_type: {request.exec_type}")
                return executor_pb2.EnqueueResponse()
            exec_type = request.exec_type or "run"
            method_name = request.method_name or "run"
            test_cases_json = request.test_cases_json or "[]"
            qid = execute(
                """INSERT INTO execution_queue
                   (problem_id, code, method_name, test_cases_json, exec_type, status)
                   VALUES (%s, %s, %s, %s, %s, 'queued')""",
                (request.problem_id, request.code, method_name, test_cases_json, exec_type),
            )
            return executor_pb2.EnqueueResponse(queue_id=int(qid), status="queued")
        except Exception as exc:  # pragma: no cover
            logger.exception("EnqueueExecution failed: %s", exc)
            await context.set_code(grpc.StatusCode.INTERNAL)
            await context.set_details(str(exc))
            return executor_pb2.EnqueueResponse()

    async def GetExecutionStatus(self, request, context):  # type: ignore[no-untyped-def]
        row = query_one(
            "SELECT id, status, result, stdout, error, timing_ms, memory_kb, solution_id "
            "FROM execution_queue WHERE id = %s",
            (int(request.queue_id),),
        )
        if row is None:
            await context.set_code(grpc.StatusCode.NOT_FOUND)
            await context.set_details("queue entry not found")
            return executor_pb2.GetStatusResponse()
        return executor_pb2.GetStatusResponse(
            queue_id=int(row["id"]),
            status=row["status"] or "",
            result=row["result"] or "",
            stdout=row["stdout"] or "",
            error=row["error"] or "",
            timing_ms=int(row["timing_ms"] or 0),
            memory_kb=int(row["memory_kb"] or 0),
            solution_id=int(row["solution_id"] or 0),
        )

    async def HealthCheck(self, request, context):  # type: ignore[no-untyped-def]
        return executor_pb2.HealthCheckResponse(status="ok")


async def serve_grpc(port: int = 50051) -> None:
    """Run gRPC server forever (internal net only)."""
    server = grpc.aio.server()
    executor_pb2_grpc.add_ExecutorServiceServicer_to_server(ExecutorServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    await server.start()
    logger.info("gRPC ExecutorService listening on 0.0.0.0:%s", port)
    await server.wait_for_termination()


def create_grpc_server(port: int = 50051) -> grpc.aio.Server:
    """Create but not start, for embedding in bwrap_executor lifespan."""
    server = grpc.aio.server()
    executor_pb2_grpc.add_ExecutorServiceServicer_to_server(ExecutorServicer(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _port = int(os.environ.get("GRPC_PORT", "50051"))
    asyncio.run(serve_grpc(_port))
