from __future__ import annotations

import logging
import traceback
import uuid

import grpc
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    import structlog  # type: ignore

    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or uuid.uuid4().hex


def _log(level: str, event: str, request: Request, **kw):
    rid = _request_id(request)
    extra = {"request_id": rid, "path": request.url.path, "method": request.method, **kw}
    if _HAS_STRUCTLOG:
        try:
            logger = structlog.get_logger("api" if "api" in str(request.url.path) else "portal")
            getattr(logger, level)(event, **extra)
            return rid
        except Exception:
            pass
    logging.getLogger("app").log(getattr(logging, level.upper(), logging.INFO), "%s %s", event, extra)
    return rid


def _envelope(code: str, message: str, request_id: str, details=None):
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    if details is not None:
        body["error"]["details"] = details
    return body


async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    rid = _request_id(request)
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        429: "TOO_MANY_REQUESTS",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    msg = str(exc.detail) if exc.detail else "Error"
    if exc.status_code >= 500:
        _log("error", "http_exception", request, status_code=exc.status_code, error_code=code, exc_info=True)
    else:
        _log("warning", "http_error", request, status_code=exc.status_code, error_code=code)
    return JSONResponse(_envelope(code, msg, rid), status_code=exc.status_code, headers={"X-Request-ID": rid})


async def handle_validation_error(request: Request, exc: RequestValidationError):
    rid = _request_id(request)
    _log("warning", "validation_error", request, status_code=400, error_code="VALIDATION_ERROR")
    details = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
    return JSONResponse(_envelope("VALIDATION_ERROR", "Validation failed", rid, details=details), status_code=400, headers={"X-Request-ID": rid})


async def handle_grpc_error(request: Request, exc: grpc.aio.AioRpcError):
    rid = _request_id(request)
    mapping = {
        grpc.StatusCode.NOT_FOUND: (404, "NOT_FOUND"),
        grpc.StatusCode.INVALID_ARGUMENT: (400, "INVALID_ARGUMENT"),
        grpc.StatusCode.ALREADY_EXISTS: (409, "ALREADY_EXISTS"),
        grpc.StatusCode.PERMISSION_DENIED: (403, "PERMISSION_DENIED"),
        grpc.StatusCode.UNAUTHENTICATED: (401, "UNAUTHENTICATED"),
        grpc.StatusCode.UNAVAILABLE: (503, "UPSTREAM_UNAVAILABLE"),
        grpc.StatusCode.DEADLINE_EXCEEDED: (504, "UPSTREAM_TIMEOUT"),
    }
    status, code = mapping.get(exc.code(), (503, "UPSTREAM_UNAVAILABLE"))
    msg = exc.details() or "Upstream unavailable"
    _log("error", "grpc_upstream_failed", request, status_code=status, error_code=code, grpc_code=str(exc.code()))
    return JSONResponse(_envelope(code, msg, rid), status_code=status, headers={"X-Request-ID": rid})


async def handle_generic_exception(request: Request, exc: Exception):
    rid = _request_id(request)
    _log("error", "unhandled_exception", request, status_code=500, error_code="INTERNAL_ERROR", exc_info=True)
    return JSONResponse(_envelope("INTERNAL_ERROR", "Internal server error", rid), status_code=500, headers={"X-Request-ID": rid})


def install_error_handlers(app):
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(grpc.aio.AioRpcError, handle_grpc_error)
    app.add_exception_handler(Exception, handle_generic_exception)
