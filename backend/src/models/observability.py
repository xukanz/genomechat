"""Response models for `/internal/*` observability endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TraceSpanSummary(BaseModel):
    """Sparse span metadata returned from /internal/traces."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    start_time: datetime
    duration_ms: float
    status_code: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    active_skills: list[str] = Field(default_factory=list)


class TraceListResponse(BaseModel):
    """Paginated span list for /internal/traces."""

    spans: list[TraceSpanSummary] = Field(default_factory=list)
    total: int = 0
    limit: int = 100
    offset: int = 0


class MemoryPreview(BaseModel):
    """Sparse memory row returned from /internal/memory.

    Embeddings are deliberately excluded — embeddings can in principle be
    inverted, so we treat them as sensitive per governance.
    """

    memory_id: str
    fact: str
    domain: str
    importance: float
    salience: float
    created_at: datetime
    updated_at: datetime


class MemoryRetrievalResponse(BaseModel):
    """Response for /internal/memory (retrieval preview)."""

    memories: list[MemoryPreview] = Field(default_factory=list)
    total: int = 0
    schema_version: str = "1"


class MemoryConsolidationResponse(BaseModel):
    """Response for POST /internal/memory/consolidate."""

    counters: dict[str, int] = Field(default_factory=dict)
    schema_version: str = "1"
