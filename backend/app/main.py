import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import domains as domains_api
from app.api import health
from app.core.config import get_settings
from app.core.db import check_db
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware
from app.core.providers import get_embedder, get_llm
from app.domains import service

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    # Fail loudly: without Postgres nothing works, so refuse to start.
    # Raising here makes uvicorn exit with a non-zero code.
    try:
        check_db()
    except Exception as exc:
        logger.critical("postgres_unreachable", extra={"error": str(exc)})
        raise RuntimeError(f"Cannot connect to Postgres: {exc}") from exc

    # Load domain packs. A broken pack is logged and skipped (other packs still
    # load); but if the reload itself fails (e.g. migrations not run) refuse to start.
    try:
        result = service.reload()
    except Exception as exc:
        logger.critical("domain_load_failed", extra={"error": str(exc), "hint": "did you run `alembic upgrade head`?"})
        raise RuntimeError(f"Cannot load domains: {exc}") from exc
    logger.info("domains_loaded_at_startup", extra={"loaded": result.loaded, "failed_count": len(result.failed)})

    # Run the Gemini check once and cache it; a failure is reported by
    # /health but doesn't stop the app from starting.
    app.state.gemini_status = health.check_gemini(get_llm(), get_embedder())
    logger.info("startup_complete", extra={"gemini": app.state.gemini_status["status"]})
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Multi-Domain Research Assistant", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestLoggingMiddleware)  # added last = outermost, so it times everything
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(domains_api.router, prefix="/api/v1")
    return app


app = create_app()
