"""MongoDB-backed OTel SpanExporter.

No-ops when `trace_storage_enabled=False`. Designed to be wrapped in a
BatchSpanProcessor so inserts happen off the request hot path. Attribute
values that OTel returns as tuples or non-JSON-safe types are normalized
to JSON-safe shapes in `_normalize_attrs`.

TTL: on init, we ensure a TTL index on `start_time` — MongoDB expires old
trace docs automatically after `settings.trace_ttl_days` days. S3 daily
archive is the long-term retention path.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from src.config.settings import settings
from src.service.database.connections.mongodb_connection import get_mongodb_client

logger = logging.getLogger(__name__)


_TRACE_SCHEMA_VERSION = "1"


class MongoDBSpanExporter(SpanExporter):
    """Exports OTel spans to the MongoDB `traces` collection."""

    def __init__(self, collection_name: str | None = None) -> None:
        self._collection_name = collection_name or settings.trace_mongodb_collection
        self._enabled = settings.trace_storage_enabled
        self._shutdown = False
        self._collection = None
        if self._enabled:
            try:
                client = get_mongodb_client()
                self._collection = client[settings.mongodb_db_name][self._collection_name]
                self._ensure_ttl_index()
            except Exception:
                # Misconfigured MongoDB should not crash the app; disable export.
                logger.exception("MongoDBSpanExporter: failed to initialize; disabling")
                self._enabled = False
                self._collection = None

    def _ensure_ttl_index(self) -> None:
        if self._collection is None:
            return
        expire_seconds = settings.trace_ttl_days * 86400
        try:
            self._collection.create_index(
                "start_time", expireAfterSeconds=expire_seconds, name="ttl_start_time"
            )
        except Exception:
            # mongomock and older servers may not implement TTL — not fatal.
            logger.debug("MongoDBSpanExporter: could not create TTL index (expected on mongomock)")

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._shutdown or not self._enabled or not spans or self._collection is None:
            return SpanExportResult.SUCCESS
        docs = [self._to_document(span) for span in spans]
        try:
            self._collection.insert_many(docs, ordered=False)
            return SpanExportResult.SUCCESS
        except Exception:
            logger.exception("MongoDBSpanExporter: failed to insert %d spans", len(docs))
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._shutdown = True

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True

    @staticmethod
    def _to_document(span: ReadableSpan) -> dict[str, Any]:
        ctx = span.get_span_context()
        parent = span.parent
        start_ns = span.start_time or 0
        end_ns = span.end_time or start_ns
        start_dt = datetime.fromtimestamp(start_ns / 1_000_000_000, tz=timezone.utc)
        end_dt = datetime.fromtimestamp(end_ns / 1_000_000_000, tz=timezone.utc)
        status = span.status
        attrs = _normalize_attrs(dict(span.attributes or {}))
        # Top-level queryable fields mirror a few hot attributes so we can index
        # and query them with plain equality — dotted-key attributes (e.g.
        # `agent.thread_id`) cannot be queried by dotted path because MongoDB
        # treats the dot as nested-document navigation.
        thread_id = attrs.get("agent.thread_id", "") or ""
        return {
            "schema_version": _TRACE_SCHEMA_VERSION,
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            "parent_span_id": format(parent.span_id, "016x") if parent else None,
            "name": span.name,
            "kind": span.kind.name,
            "start_time": start_dt,
            "end_time": end_dt,
            "duration_ms": (end_ns - start_ns) / 1_000_000,
            "status": {
                "code": status.status_code.name,
                "description": status.description,
            },
            "attributes": attrs,
            "events": [
                {
                    "name": e.name,
                    "timestamp": e.timestamp,
                    "attributes": _normalize_attrs(dict(e.attributes or {})),
                }
                for e in span.events
            ],
            "resource": _normalize_attrs(dict(span.resource.attributes or {})),
            "active_skills": attrs.get("active_skills", []),
            # Indexed query handles
            "thread_id": thread_id,
            "tenant_id": thread_id.split(":", 1)[0] if ":" in thread_id else "",
        }


def _normalize_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Flatten OTel attribute values to JSON-safe primitives.

    OTel allows homogeneous tuples of primitives; BSON doesn't care but our
    downstream consumers want lists. Anything non-primitive falls back to a
    JSON-stringified form as a last resort (BSON won't accept arbitrary
    Python objects).
    """
    out: dict[str, Any] = {}
    for k, v in attrs.items():
        if isinstance(v, (list, tuple)):
            out[k] = list(v)
        elif isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, dict):
            out[k] = _normalize_attrs(v)
        else:
            out[k] = json.dumps(v, default=str)
    return out
