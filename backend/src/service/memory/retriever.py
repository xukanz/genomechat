"""Five-layer retrieval for the memory pipeline.

Phase 0.5 SHIPS the retriever but does NOT wire it into the orchestrator's
prompt — Phase 3 will. Callers get `list[RetrievedMemory]` back; the caller
decides how to render.

Layers, all scoped to a single `user_id`:
  1. semantic          — $vectorSearch on `embedding`, score ≥ 0.3
  2. fts               — MongoDB text index on `fact`
  3. recent-important  — updated in last 48h AND importance ≥ 0.8
  4. insights          — cosine match on MemoryInsight.embedding
  5. conversation-hist — recent checkpoint message keyword match (best-effort)

Fallbacks: if Atlas vector search is unavailable, layer 1 becomes a brute-force
cosine scan over the user's memories. If any layer fails, it returns an empty
contribution — never propagates.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError

from src.config.settings import settings
from src.service.database.connections.mongodb_connection import get_mongodb_client
from src.service.memory.embeddings import get_embedder
from src.service.memory.schema import Memory, RetrievedMemory

logger = logging.getLogger(__name__)


# Source weights for the final score. Tuned so no single layer dominates.
_SOURCE_WEIGHTS: dict[str, float] = {
    "semantic": 1.0,
    "insight": 0.85,
    "recent": 0.75,
    "fts": 0.6,
    "conversation-history": 0.5,
}

_SEMANTIC_SCORE_FLOOR = 0.3


async def retrieve_memories(
    *,
    query: str,
    user_id: str,
    k: int = 10,
) -> list[RetrievedMemory]:
    """Return up to `k` most relevant memories for `query` scoped to `user_id`."""
    if not query or not user_id:
        return []

    try:
        embedder = get_embedder()
        query_vec = await embedder.aembed_query(query)  # type: ignore[attr-defined]
    except Exception:
        logger.warning(
            "retrieve_memories: embedding failed; semantic layer disabled", exc_info=True
        )
        query_vec = []

    semantic, fts, recent, insight, convo = await asyncio.gather(
        _layer_semantic(user_id, query_vec),
        _layer_fts(user_id, query),
        _layer_recent_important(user_id),
        _layer_insights(user_id, query_vec),
        _layer_conversation_history(user_id, query),
        return_exceptions=True,
    )

    combined: dict[str, RetrievedMemory] = {}
    for layer_name, results in (
        ("semantic", semantic),
        ("fts", fts),
        ("recent", recent),
        ("insight", insight),
        ("conversation-history", convo),
    ):
        if isinstance(results, Exception):
            logger.debug("retrieve_memories: layer %s raised", layer_name, exc_info=results)
            continue
        for mem, raw_score in results:  # type: ignore[union-attr]
            weighted = raw_score * _SOURCE_WEIGHTS[layer_name]
            existing = combined.get(mem.memory_id)
            if existing is None or weighted > existing.score:
                combined[mem.memory_id] = RetrievedMemory(
                    memory=mem,
                    score=weighted,
                    source=layer_name,  # type: ignore[arg-type]
                )

    ranked = sorted(
        combined.values(),
        key=lambda r: (
            r.score,
            r.memory.salience,
            r.memory.updated_at,
        ),
        reverse=True,
    )
    return ranked[:k]


# ---------------------------------------------------------------------------
# Per-layer implementations. Each returns list[(Memory, raw_score)]
# ---------------------------------------------------------------------------


async def _layer_semantic(user_id: str, query_vec: list[float]) -> list[tuple[Memory, float]]:
    if not query_vec:
        return []

    def _run() -> list[tuple[Memory, float]]:
        coll = get_mongodb_client()[settings.mongodb_db_name]["research_memories"]
        if settings.memory_atlas_vector_search_enabled:
            try:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": "research_memories_vector",
                            "path": "embedding",
                            "queryVector": query_vec,
                            "numCandidates": 100,
                            "limit": 10,
                            "filter": {"user_id": user_id},
                        }
                    },
                    {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                ]
                out: list[tuple[Memory, float]] = []
                for doc in coll.aggregate(pipeline):
                    score = float(doc.get("score", 0.0))
                    if score < _SEMANTIC_SCORE_FLOOR:
                        continue
                    out.append((_doc_to_memory(doc), score))
                return out
            except Exception:
                logger.debug("_layer_semantic: vector search failed; falling back", exc_info=True)

        # Brute-force fallback — read per-user memories and score in Python
        out = []
        for doc in coll.find({"user_id": user_id}).limit(500):
            emb = doc.get("embedding") or []
            score = _cosine(query_vec, emb)
            if score >= _SEMANTIC_SCORE_FLOOR:
                out.append((_doc_to_memory(doc), score))
        return out

    return await asyncio.to_thread(_run)


async def _layer_fts(user_id: str, query: str) -> list[tuple[Memory, float]]:
    def _run() -> list[tuple[Memory, float]]:
        coll = get_mongodb_client()[settings.mongodb_db_name]["research_memories"]
        # Projection must include every Memory field alongside the text-score meta.
        # Earlier versions projected only {"score": {"$meta": "textScore"}}, which
        # returns {_id, score} — `_doc_to_memory` then failed validation and a
        # broad except silently dropped every hit.
        projection = {
            "_id": 0,
            "memory_id": 1,
            "user_id": 1,
            "project_id": 1,
            "thread_id": 1,
            "database_id": 1,
            "fact": 1,
            "domain": 1,
            "importance": 1,
            "salience": 1,
            "embedding": 1,
            "pinned": 1,
            "superseded_at": 1,
            "created_at": 1,
            "updated_at": 1,
            "access_count": 1,
            "last_accessed_at": 1,
            "score": {"$meta": "textScore"},
        }
        try:
            cursor = (
                coll.find(
                    {"user_id": user_id, "$text": {"$search": query}},
                    projection,
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(10)
            )
        except Exception:
            logger.debug("_layer_fts: text search unavailable", exc_info=True)
            return []
        out: list[tuple[Memory, float]] = []
        for doc in cursor:
            try:
                out.append((_doc_to_memory(doc), float(doc.get("score", 0.0))))
            except ValidationError:
                # Projection drift — a required Memory field is missing from the
                # result. Narrower than `except Exception` so real bugs surface
                # in tests instead of being silently swallowed.
                logger.debug("_layer_fts: result doc failed Memory validation", exc_info=True)
                continue
        return out

    return await asyncio.to_thread(_run)


async def _layer_recent_important(user_id: str) -> list[tuple[Memory, float]]:
    def _run() -> list[tuple[Memory, float]]:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
        coll = get_mongodb_client()[settings.mongodb_db_name]["research_memories"]
        cursor = (
            coll.find(
                {
                    "user_id": user_id,
                    "importance": {"$gte": 0.8},
                    "updated_at": {"$gte": cutoff},
                }
            )
            .sort([("updated_at", -1)])
            .limit(10)
        )
        return [(_doc_to_memory(doc), float(doc.get("importance", 0.8))) for doc in cursor]

    return await asyncio.to_thread(_run)


async def _layer_insights(user_id: str, query_vec: list[float]) -> list[tuple[Memory, float]]:
    """Match the query against consolidation insights; fan out to their members."""
    if not query_vec:
        return []

    def _run() -> list[tuple[Memory, float]]:
        db = get_mongodb_client()[settings.mongodb_db_name]
        insights = db["memory_insights"]
        members_coll = db["research_memories"]

        best_member_ids: list[str] = []
        best_score = 0.0
        for ins in insights.find({"user_id": user_id}).limit(200):
            emb = ins.get("embedding") or []
            s = _cosine(query_vec, emb)
            if s >= 0.3 and s > best_score:
                best_score = s
                best_member_ids = list(ins.get("member_memory_ids") or [])

        if not best_member_ids:
            return []

        out: list[tuple[Memory, float]] = []
        for doc in members_coll.find({"memory_id": {"$in": best_member_ids}}):
            out.append((_doc_to_memory(doc), best_score))
        return out

    return await asyncio.to_thread(_run)


async def _layer_conversation_history(user_id: str, query: str) -> list[tuple[Memory, float]]:
    """Keyword match against the user's 7-day checkpoint message corpus.

    This layer is intentionally best-effort: the LangGraph checkpoint shape
    varies by LG version and is not the authoritative store. We degrade to
    empty list when anything goes wrong.
    """
    _ = user_id, query
    # Phase 0.5 ships the retriever scaffolding; the checkpoint-traversal
    # implementation is left deliberately empty here (will be filled by Phase 3
    # when we have concrete feedback-loop requirements). Keeping the signature
    # stable lets the merge/ranking logic above stay unchanged.
    return []


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _doc_to_memory(doc: dict[str, Any]) -> Memory:
    """Build a Memory from a MongoDB document, dropping Mongo-only fields."""
    clean = {k: v for k, v in doc.items() if k not in {"_id", "score"}}
    return Memory.model_validate(clean)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
