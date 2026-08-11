"""Pydantic models + MongoDB index definitions for the memory pipeline.

Phase 0.5 writes to two collections in the shared `mongodb_db_name` database:
- `research_memories` — per-user extracted facts with embeddings
- `memory_insights` — consolidation outputs summarizing related clusters

The index definitions are returned by `MEMORY_INDEXES` so `indexes.ensure_indexes`
can apply them idempotently on app startup.

Domains align with the extractor prompt and must stay in sync:
  user-preference | query-pattern | failure-mode | successful-pattern
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryDomain = Literal[
    "user-preference",
    "query-pattern",
    "failure-mode",
    "successful-pattern",
]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Memory(BaseModel):
    """A single extracted fact stored in `research_memories`."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="UUID4 hex string")
    user_id: str
    project_id: str | None = None
    thread_id: str | None = None
    database_id: str | None = None
    fact: str = Field(..., description="Redacted, standalone fact text")
    domain: MemoryDomain
    importance: float = Field(..., ge=0.0, le=1.0)
    salience: float = Field(default=1.0, ge=0.0, le=1.0)
    embedding: list[float] | None = None
    pinned: bool = Field(default=False, description="Pinned memories exempt from TTL decay")
    superseded_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    access_count: int = Field(default=0, ge=0)
    last_accessed_at: datetime | None = None


class MemoryInsight(BaseModel):
    """A consolidation-emitted insight across a memory cluster.

    Written to `memory_insights`; never decayed automatically — only removed
    when the underlying cluster is fully superseded.
    """

    model_config = ConfigDict(extra="forbid")

    insight_id: str = Field(..., description="UUID4 hex string")
    user_id: str
    summary: str
    domain: MemoryDomain
    member_memory_ids: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class RetrievedMemory(BaseModel):
    """Retriever output row. One layer of provenance plus the matched memory."""

    model_config = ConfigDict(extra="forbid")

    memory: Memory
    score: float = Field(..., description="Source-weighted relevance score")
    source: Literal["semantic", "fts", "recent", "insight", "conversation-history"]


# ---------------------------------------------------------------------------
# Index definitions — read by indexes.ensure_indexes and applied once at startup.
# ---------------------------------------------------------------------------


def _vector_search_index(dimensions: int) -> dict[str, Any]:
    """Return the Atlas $vectorSearch index definition for research_memories."""
    return {
        "name": "research_memories_vector",
        "definition": {
            "mappings": {
                "dynamic": False,
                "fields": {
                    "embedding": {
                        "type": "knnVector",
                        "dimensions": dimensions,
                        "similarity": "cosine",
                    },
                    "user_id": {"type": "token"},
                },
            }
        },
    }


def memory_index_specs(dimensions: int, ttl_days: int) -> dict[str, list[dict[str, Any]]]:
    """Return index specs per collection. Pure function — no I/O.

    Callers (`indexes.ensure_indexes`) translate these into `create_index` and
    `createSearchIndexes` commands with appropriate error handling.
    """
    return {
        "research_memories": [
            {
                "keys": [("user_id", 1), ("salience", -1)],
                "name": "user_salience_idx",
            },
            {
                "keys": [("user_id", 1), ("domain", 1), ("updated_at", -1)],
                "name": "user_domain_recent_idx",
            },
            {
                "keys": [("fact", "text")],
                "name": "fact_text_idx",
            },
            {
                "keys": [("updated_at", 1)],
                "name": "memory_ttl_idx",
                "expireAfterSeconds": ttl_days * 86400,
            },
            {
                "keys": [("memory_id", 1)],
                "name": "memory_id_unique",
                "unique": True,
            },
        ],
        "memory_insights": [
            {
                "keys": [("user_id", 1), ("created_at", -1)],
                "name": "user_created_idx",
            },
            {
                "keys": [("insight_id", 1)],
                "name": "insight_id_unique",
                "unique": True,
            },
        ],
        "memory_redaction_log": [
            {
                "keys": [("user_id", 1), ("timestamp", -1)],
                "name": "user_timestamp_idx",
            },
        ],
    }


def vector_search_index_spec(dimensions: int) -> dict[str, Any]:
    """Return the Atlas Search index spec; caller decides whether to create it."""
    return _vector_search_index(dimensions)
