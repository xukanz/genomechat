"""OpenTelemetry TracerProvider setup.

`setup_tracing(app)` is idempotent and safe to call from FastAPI lifespan
startup. When `settings.otel_enabled=False`, it's a no-op — the module-level
tracer still works (emits to the NoOp TracerProvider), which means decorators
apply everywhere without a branch.

Multi-exporter design: each enabled exporter gets wrapped in its own
BatchSpanProcessor. Adding Langfuse or another OTLP backend is a settings
flip, not a rewrite. See the plan's Sub-Phase B task 12 rationale.
"""

from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from src.config.settings import settings
from src.service.observability.mongodb_exporter import MongoDBSpanExporter

logger = logging.getLogger(__name__)


# Module-level sentinel so we configure the global TracerProvider exactly once
# even across hot-reload or multiple lifespan invocations.
_CONFIGURED = False


def setup_tracing(app: Any | None = None) -> None:
    """Install a TracerProvider + exporters and instrument FastAPI/pymongo.

    Idempotent. When `otel_enabled=False`, this is a no-op and the default
    NoOp tracer remains in place.
    """
    global _CONFIGURED

    if not settings.otel_enabled:
        logger.info("setup_tracing: otel_enabled=False; skipping instrumentation")
        return

    if _CONFIGURED:
        logger.debug("setup_tracing: already configured; skipping")
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.api_version,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)

    exporters: list[SpanExporter] = []
    if settings.trace_storage_enabled:
        exporters.append(MongoDBSpanExporter())

    if settings.langfuse_enabled:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore
                OTLPSpanExporter,
            )

            headers = (
                {"Authorization": f"Basic {settings.langfuse_auth_header}"}
                if settings.langfuse_auth_header
                else {}
            )
            exporters.append(
                OTLPSpanExporter(
                    endpoint=settings.langfuse_otlp_endpoint,
                    headers=headers,
                )
            )
        except Exception:
            # Don't fail startup if Langfuse can't be reached; MongoDB export still works.
            logger.exception("setup_tracing: failed to initialize Langfuse exporter; skipping")

    for exporter in exporters:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)

    # Instrument FastAPI + pymongo; wrap in try/except so an instrumentation
    # incompatibility in one doesn't prevent the other from running.
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore

            FastAPIInstrumentor.instrument_app(app)
        except Exception:
            logger.exception("setup_tracing: FastAPI instrumentation failed")

    try:
        from opentelemetry.instrumentation.pymongo import PymongoInstrumentor  # type: ignore

        PymongoInstrumentor().instrument()
    except Exception:
        logger.exception("setup_tracing: pymongo instrumentation failed")

    _CONFIGURED = True
    logger.info(
        "setup_tracing: configured with %d exporter(s); service.name=%s",
        len(exporters),
        settings.otel_service_name,
    )


def shutdown_tracing() -> None:
    """Flush + shut down the current TracerProvider. Safe to call when unset."""
    provider = trace.get_tracer_provider()
    flusher = getattr(provider, "force_flush", None)
    if callable(flusher):
        try:
            flusher()
        except Exception:
            logger.debug("shutdown_tracing: force_flush raised", exc_info=True)
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        try:
            shutdown()
        except Exception:
            logger.debug("shutdown_tracing: shutdown raised", exc_info=True)
