"""FastAPI application setup."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings

# Configure logging
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Suppress noisy loggers
logging.getLogger("watchfiles").setLevel(logging.WARNING)  # Reduce file watcher noise
logging.getLogger("httpx").setLevel(logging.WARNING)  # Reduce HTTP request noise
logging.getLogger("httpcore").setLevel(logging.WARNING)  # Reduce HTTP core noise
logging.getLogger("urllib3").setLevel(logging.WARNING)  # Reduce urllib3 noise

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application.

    Handles startup and shutdown events.
    """
    logger.info("Starting FastAPI application")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"API Version: {settings.api_version}")

    # Phase 0: observability — idempotent; no-op when OTEL_ENABLED=false
    try:
        from src.service.observability import setup_tracing

        setup_tracing(app)
    except Exception:
        logger.exception("Failed to setup tracing; continuing without OTel")

    # APScheduler hosts Phase 0 (S3 archive), Phase 0.5 (memory consolidation),
    # and Phase 1 (SDK transcript orphan cleanup) jobs so we run at most one
    # scheduler per process. Phase 1's cleanup job is always scheduled — it is
    # harmless on LangChain-only pods (sweeps an empty directory) and prevents
    # unbounded growth under ~/.claude/projects/ when CODER_BACKEND=sdk.
    scheduler = None
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()

        if settings.trace_s3_archive_enabled:
            from src.service.observability.s3_archive import run_daily_archive

            scheduler.add_job(run_daily_archive, "cron", hour=2, id="trace_s3_archive")

        if settings.memory_consolidation_enabled:
            from src.service.memory import run_consolidation

            scheduler.add_job(
                run_consolidation,
                "interval",
                minutes=settings.memory_consolidation_interval_minutes,
                id="memory_consolidation",
            )

        # Phase 1: crash-recovery sweep on startup + periodic orphan cleanup
        try:
            from src.service.sdk_runtime import cleanup_orphans

            removed = cleanup_orphans()
            if removed:
                logger.info("Phase 1 startup sweep removed %d orphaned transcript dir(s)", removed)

            scheduler.add_job(
                cleanup_orphans,
                "interval",
                minutes=settings.sdk_orphan_cleanup_interval_minutes,
                id="sdk_orphan_cleanup",
            )
        except Exception:
            logger.exception("Failed to schedule SDK orphan cleanup; continuing")

        if scheduler.get_jobs():
            scheduler.start()
            logger.info("APScheduler started with %d job(s)", len(scheduler.get_jobs()))
        else:
            scheduler = None
    except Exception:
        logger.exception("Failed to start APScheduler; background jobs disabled")
        scheduler = None

    # Phase 0.5: memory collection indexes (idempotent; honors atlas-search flag)
    if settings.memory_extraction_enabled or settings.memory_consolidation_enabled:
        try:
            from src.service.memory import ensure_indexes

            await ensure_indexes()
        except Exception:
            logger.exception("Failed to ensure memory indexes; continuing")

    yield

    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.debug("APScheduler shutdown raised", exc_info=True)

    try:
        from src.service.observability.otel_setup import shutdown_tracing

        shutdown_tracing()
    except Exception:
        logger.debug("shutdown_tracing raised", exc_info=True)

    logger.info("Shutting down FastAPI application")


# Create FastAPI application
app = FastAPI(
    title="GenomeChat API",
    description="FastAPI backend with LangGraph middleware agents",
    version=settings.api_version,
    lifespan=lifespan,
)

# CORS. Exact origins come from CORS_ORIGINS; CORS_ORIGIN_REGEX is an optional
# escape hatch for deployments that serve the frontend from a wildcard subdomain
# (e.g. r"https://.*\.example\.com"). Left unset, only the exact list applies.
_cors_kwargs: dict[str, Any] = {
    "allow_origins": settings.cors_origins_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_origin_regex:
    _cors_kwargs["allow_origin_regex"] = settings.cors_origin_regex

app.add_middleware(CORSMiddleware, **_cors_kwargs)
