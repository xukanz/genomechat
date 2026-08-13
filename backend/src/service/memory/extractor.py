"""Fire-and-forget memory extraction from a completed conversation turn.

Invoked via `asyncio.ensure_future` after the chat stream's `end` event so
extraction latency never blocks the user-visible response. Redaction runs
BEFORE the Haiku call and BEFORE any write to `research_memories` — that's the
compliance invariant, not a performance optimization.

Span emission: wrap the outer coroutine with `@trace_node("memory_extractor")`
so the span inherits `agent.thread_id` from `thread_id_context` and the inner
Haiku call's `gen_ai.chat` span is the natural child carrying cost via
`OTelCallbackHandler`. Never set `gen_ai.usage.cost_usd` on the outer span —
the Phase 0 contract derives it from the child tree.

Pilot gating: `settings.memory_extraction_enabled` + `settings.memory_pilot_user_ids`
are checked by the chat.py hook *before* calling us; this function assumes
it was already admitted.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.config.settings import settings
from src.prompts.template import get_processed_prompt
from src.service.database.connections.mongodb_connection import get_mongodb_client
from src.service.llm import LLMService
from src.service.memory.embeddings import get_embedder
from src.service.memory.redaction import RedactionHit, redact
from src.service.memory.schema import Memory, MemoryDomain
from src.service.observability.decorators import trace_node

logger = logging.getLogger(__name__)


_VALID_DOMAINS: set[str] = {
    "user-preference",
    "query-pattern",
    "failure-mode",
    "successful-pattern",
}


async def extract_memories_for_turn(
    *,
    thread_id: str,
    user_id: str,
    project_id: str | None,
    database_id: str | None,
    user_message: str,
    assistant_message: str,
) -> list[Memory]:
    """Extract 0-5 memories from the turn. Returns the inserted Memory objects.

    Returns an empty list when the LLM yields nothing, when every candidate
    dedupes against existing memories, or when any step fails — failures are
    logged but never propagated, because the caller is fire-and-forget and a
    memory-extraction crash must NEVER break the user response.
    """
    # Pass the state dict by the conventional `state` param so @trace_node can
    # hoist attributes; we stash thread_id / database_id so the span carries
    # the correct attributes.
    state = {
        "thread_id": thread_id,
        "database_id": database_id or "",
        "research_mode": "",
        "code_language": "",
    }
    return await _run_extraction(
        state,
        user_id=user_id,
        project_id=project_id,
        database_id=database_id,
        user_message=user_message,
        assistant_message=assistant_message,
    )


@trace_node("memory_extractor")
async def _run_extraction(
    state: dict[str, Any],
    *,
    user_id: str,
    project_id: str | None,
    database_id: str | None,
    user_message: str,
    assistant_message: str,
) -> list[Memory]:
    # 1. Redact at ingestion. Over-redaction is safe; under-redaction is not.
    redacted_user, user_hits = redact(user_message)
    redacted_assistant, assistant_hits = redact(assistant_message)
    all_hits = user_hits + assistant_hits
    if all_hits:
        _log_redaction_audit(user_id=user_id, thread_id=state["thread_id"], hits=all_hits)

    # 2. Invoke Haiku with JSON mode. Any failure → empty memory list.
    try:
        raw = await _call_extractor_llm(
            user_id=user_id,
            project_id=project_id or "",
            database_id=database_id or "",
            user_message=redacted_user,
            assistant_message=redacted_assistant,
        )
        candidates = _parse_candidates(raw)
    except Exception:
        logger.warning("memory_extractor: LLM call or parse failed", exc_info=True)
        return []

    if not candidates:
        return []

    # 3. Embed facts (bounded by module-level semaphore inside BedrockTitanEmbeddings)
    try:
        embedder = get_embedder()
        fact_vectors = await embedder.aembed_documents([c["fact"] for c in candidates])  # type: ignore[attr-defined]
    except Exception:
        logger.warning("memory_extractor: embedding failed; dropping batch", exc_info=True)
        return []

    # 4. Dedup + insert
    inserted: list[Memory] = []
    try:
        coll = get_mongodb_client()[settings.mongodb_db_name]["research_memories"]
    except Exception:
        logger.warning("memory_extractor: MongoDB unavailable; dropping batch", exc_info=True)
        return []

    for cand, vec in zip(candidates, fact_vectors):
        if _is_duplicate(coll, user_id=user_id, vector=vec):
            logger.debug("memory_extractor: dedup hit (user=%s)", user_id)
            continue

        mem = Memory(
            memory_id=uuid.uuid4().hex,
            user_id=user_id,
            project_id=project_id,
            thread_id=state["thread_id"],
            database_id=database_id,
            fact=cand["fact"],
            domain=cand["domain"],
            importance=float(cand["importance"]),
            embedding=list(vec),
        )
        try:
            # Default python mode keeps datetimes as BSON-compatible objects so
            # the TTL index on `updated_at` and the recency retrieval layer work.
            # See `schema.memory_index_specs` (memory_ttl_idx) and
            # `retriever._layer_recent_important`.
            coll.insert_one(mem.model_dump())
            inserted.append(mem)
        except Exception:
            logger.debug("memory_extractor: insert failed", exc_info=True)

    logger.info(
        "memory_extractor: user=%s inserted=%d candidates=%d redaction_hits=%d",
        user_id,
        len(inserted),
        len(candidates),
        len(all_hits),
    )
    return inserted


# ---------------------------------------------------------------------------
# Helpers — small enough to keep in-module; each under 30 lines.
# ---------------------------------------------------------------------------


async def _call_extractor_llm(
    *,
    user_id: str,
    project_id: str,
    database_id: str,
    user_message: str,
    assistant_message: str,
) -> str:
    prompt = get_processed_prompt(
        "memory_extractor",
        template_vars={
            "user_id": user_id,
            "project_id": project_id,
            "database_id": database_id,
            "user_message": user_message,
            "assistant_message": assistant_message,
        },
    )
    llm = LLMService.get_llm_by_agent(
        settings.memory_extraction_agent,
        streaming=False,
        temperature=0.3,
    )
    response = await llm.ainvoke(prompt)
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)


def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    """Parse the Haiku JSON output. Tolerates surrounding whitespace + code fences."""
    text = raw.strip()
    if text.startswith("```"):
        # Strip fenced code block if Haiku wrapped JSON despite the prompt
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to locating the outermost object — handles prefix chatter
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise
        data = json.loads(text[start : end + 1])

    memories = data.get("memories") if isinstance(data, dict) else None
    if not isinstance(memories, list):
        return []

    out: list[dict[str, Any]] = []
    for m in memories[:5]:  # Prompt says 0-5; enforce here too
        if not isinstance(m, dict):
            continue
        fact = m.get("fact")
        domain = m.get("domain")
        importance = m.get("importance")
        if not isinstance(fact, str) or not fact.strip():
            continue
        if domain not in _VALID_DOMAINS:
            continue
        try:
            importance_f = float(importance)
        except (TypeError, ValueError):
            continue
        if not 0.0 <= importance_f <= 1.0:
            continue
        out.append(
            {
                "fact": fact.strip(),
                "domain": domain,
                "importance": importance_f,
            }
        )
    return out


def _is_duplicate(coll: Any, *, user_id: str, vector: list[float]) -> bool:
    """Check whether any existing memory exceeds the dedup cosine threshold.

    Uses Atlas `$vectorSearch` when available; falls back to a brute-force
    cosine scan over the user's existing memories when the index is missing
    (Community Edition / not-yet-entitled clusters).
    """
    if settings.memory_atlas_vector_search_enabled:
        try:
            pipeline = [
                {
                    "$vectorSearch": {
                        "index": "research_memories_vector",
                        "path": "embedding",
                        "queryVector": list(vector),
                        "numCandidates": 20,
                        "limit": 5,
                        "filter": {"user_id": user_id},
                    }
                },
                {"$project": {"_id": 0, "score": {"$meta": "vectorSearchScore"}}},
            ]
            for doc in coll.aggregate(pipeline):
                if doc.get("score", 0.0) >= settings.memory_duplicate_threshold:
                    return True
            return False
        except Exception:
            logger.debug("dedup: vector search unavailable; falling back", exc_info=True)

    # Brute-force fallback. Bounded by per-user memory count.
    cutoff = settings.memory_duplicate_threshold
    for doc in coll.find({"user_id": user_id}, {"embedding": 1, "_id": 0}).limit(500):
        other = doc.get("embedding") or []
        if _cosine(vector, other) >= cutoff:
            return True
    return False


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _log_redaction_audit(*, user_id: str, thread_id: str, hits: list[RedactionHit]) -> None:
    """Write one audit row capturing pattern names + spans (never raw values)."""
    try:
        coll = get_mongodb_client()[settings.mongodb_db_name]["memory_redaction_log"]
        coll.insert_one(
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "hits": [{"pattern_name": h.pattern_name, "span": list(h.span)} for h in hits],
                "timestamp": datetime.now(tz=timezone.utc),
            }
        )
    except Exception:
        logger.debug("memory_extractor: redaction audit insert failed", exc_info=True)


# Derived constant used by tests to enforce prompt-domain sync
VALID_DOMAINS: set[MemoryDomain] = _VALID_DOMAINS  # type: ignore[assignment]
