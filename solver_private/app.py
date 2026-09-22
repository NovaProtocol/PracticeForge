from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import ChoiceLoader, FileSystemLoader
from starlette.templating import Jinja2Templates

from shared.config import get_config, shared_static_dir, shared_templates_dir
from shared.errors import install_error_handlers
from shared.middleware import CacheControlMiddleware, RequestIDMiddleware

try:
    import structlog  # type: ignore

    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False


def _configure_logging() -> None:
    if _HAS_STRUCTLOG:
        try:
            import structlog

            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.JSONRenderer(),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
                context_class=dict,
                logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
                cache_logger_on_first_use=True,
            )
            return
        except Exception:
            pass
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create tables (sync, safe at startup)
    try:
        from shared.startup import run as run_startup

        run_startup()
    except Exception as exc:
        logging.getLogger("app").warning("startup run failed: %s", exc)
    # warm async engine
    try:
        from shared.db import get_async_engine

        get_async_engine()
    except Exception:
        pass
    yield


def _build_templates() -> Jinja2Templates:
    app_root = Path(__file__).resolve().parent
    app_templates = app_root / "templates"
    shared_templates = Path(shared_templates_dir())
    # fallback to repo layout if shared_templates_dir not found
    candidates = []
    # blueprint template roots so "problems/index.html" resolves
    for sub in ("apps/problems/templates", "apps/solutions/templates"):
        p = app_root / sub
        if p.exists():
            candidates.append(str(p))
    candidates += [str(app_templates), str(shared_templates)]
    # Jinja2Templates with ChoiceLoader so both dirs work (host + container)
    loader = ChoiceLoader([FileSystemLoader(c) for c in candidates])
    from jinja2 import Environment, select_autoescape

    env = Environment(loader=loader, autoescape=select_autoescape(["html", "xml"]))
    # Provide Flask-like url_for shim for existing templates
    def _url_for(endpoint: str, **values):
        # map known Flask blueprint endpoints to paths
        if endpoint in ("problems_blueprint.index", "problems.index"):
            return "/"
        if endpoint in ("solutions_blueprint.index", "solutions.index"):
            return "/solutions/"
        if endpoint in ("problems_blueprint.detail", "problems.detail"):
            cid = values.get("contest_id", "")
            idx = values.get("index", values.get("problem_index", ""))
            return f"/problem/{cid}/{idx}/"
        # fallback: try to return raw endpoint
        return "/" + endpoint.replace(".", "/")

    env.globals["url_for"] = _url_for
    return Jinja2Templates(env=env)


_templates = _build_templates()


def create_app() -> FastAPI:
    _configure_logging()
    config = get_config()

    app = FastAPI(title="PracticeForge", debug=config.DEBUG, lifespan=lifespan)

    # RequestID must be first so even 401s have X-Request-ID
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(CacheControlMiddleware, is_debug=config.DEBUG)

    # static
    static_dir = Path(shared_static_dir())
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # routers
    from apps.api.routes import router as api_router
    from apps.problems.routes import router as problems_router
    from apps.solutions.routes import router as solutions_router

    app.include_router(problems_router)
    app.include_router(solutions_router)
    app.include_router(api_router)

    @app.get("/health")
    async def health(request: Request):
        # lightweight DB check, degraded if unreachable
        try:
            from sqlalchemy import text

            from shared.db import get_async_engine

            engine = get_async_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return {"status": "ok"}
        except Exception as exc:
            return JSONResponse({"status": "degraded", "db": str(exc)}, status_code=503)

    @app.get("/404", response_class=HTMLResponse)
    async def not_found_page(request: Request):
        return _templates.TemplateResponse(request, "404.html", {}, status_code=404)

    # error envelope + structlog JSON + X-Request-ID
    install_error_handlers(app)

    return app
