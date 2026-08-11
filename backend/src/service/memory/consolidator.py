"""Scheduled consolidation of extracted memories.

Fires every `settings.memory_consolidation_interval_minutes`. For each user
with memories:

1. Cluster memories by cosine ≥ 0.7 (simple greedy clustering — good enough
   for pilot-scale cohorts; replace with proper clustering when the corpus
   justifies it).
2. For each cluster, pairwise classify contradictions via Haiku and mark
   superseded memories (importance *= 0.3, salience *= 0.5).
3. Emit one MemoryInsight per cluster summarizing the theme.
4. Apply salience decay: `salience *= 0.95 ** days_since_last_access` for
   non-pinned memories.
5. Hard-delete when `salience < 0.05`.

Emits span `memory.consolidate`. Runs from the APScheduler; must be cheap
enough that one pilot user's corpus doesn't blow the loop budget — per-user
timeout caps the work at 600s (10 min) before yielding.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.config.settings import settings
from src.prompts.template import get_processed_prompt
from src.service.database.connections.mongodb_connection import get_mongodb_client
from src.service.llm import LLMService
from src.service.memory.embeddings import get_embedder
from src.service.observability.decorators import tracer

logger = logging.getLogger(__name__)


_DECAY_BASE = 0.95
_HARD_DELETE_FLOOR = 0.05
_CLUSTER_COSINE_THRESHOLD = 0.7
_PER_USER_TIMEOUT_SECONDS = 600.0


async def run_consolidation(user_id: str | None = None) -> dict[str, int]:
    """Run consolidation for one user (or all users when `user_id` is None).

    Returns a counter dict so operators can watch work volume via the span
    attributes. Never raises — logs and continues on partial failures.
    """
    counters: dict[str, int] = {
        "users_processed": 0,
        "clusters": 0,
        "superseded": 0,
        "insights": 0,
        "decayed": 0,
        "deleted": 0,
    }

    try:
        db = get_mongodb_client()[settings.mongodb_db_name]
    except Exception:
        logger.warning("run_consolidation: MongoDB unavailable", exc_info=True)
        return counters

    memories_coll = db["research_memories"]

    if user_id:
        user_ids: list[str] = [user_id]
    else:
        user_ids = list(memories_coll.distinct("user_id"))

    with tracer.start_as_current_span("memory.consolidate") as span:
        span.set_attribute("user_count", len(user_ids))
        for uid in user_ids:
            try:
                await asyncio.wait_for(
                    _consolidate_user(db, uid, counters),
                    timeout=_PER_USER_TIMEOUT_SECONDS,
                )
                counters["users_processed"] += 1
            except asyncio.TimeoutError:
                logger.warning("run_consolidation: user %s timed out", uid)
            except Exception:
                logger.warning("run_consolidation: user %s failed", uid, exc_info=True)

        for key, value in counters.items():
            span.set_attribute(f"memory.{key}", value)

    logger.info("run_consolidation: %s", counters)
    return counters


async def _consolidate_user(db: Any, user_id: str, counters: dict[str, int]) -> None:
    memories_coll = db["research_memories"]
    insights_coll = db["memory_insights"]

    all_memories = list(memories_coll.find({"user_id": user_id}))
    if not all_memories:
        return

    clusters = _greedy_cluster(all_memories)
    counters["clusters"] += len(clusters)

    for cluster in clusters:
        if len(cluster) >= 2:
            await _detect_contradictions(memories_coll, cluster, counters)
            await _emit_insight(insights_coll, user_id, cluster, counters)

    # Decay + hard-delete outside the cluster loop so every memory is touched once
    now = datetime.now(tz=timezone.utc)
    for mem in all_memories:
        if mem.get("pinned"):
            continue
        last_access = mem.get("last_accessed_at") or mem.get("updated_at") or now
        if isinstance(last_access, str):
            try:
                last_access = datetime.fromisoformat(last_access.replace("Z", "+00:00"))
            except ValueError:
                last_access = now
        # MongoDB returns naive datetimes; normalize to UTC
        if isinstance(last_access, datetime) and last_access.tzinfo is None:
            last_access = last_access.replace(tzinfo=timezone.utc)
        days = max(0, (now - last_access).days)
        if days <= 0:
            continue

        new_salience = float(mem.get("salience", 1.0)) * (_DECAY_BASE**days)
        if new_salience < _HARD_DELETE_FLOOR:
            memories_coll.delete_one({"memory_id": mem["memory_id"]})
            counters["deleted"] += 1
        else:
            memories_coll.update_one(
                {"memory_id": mem["memory_id"]},
                {"$set": {"salience": new_salience}},
            )
            counters["decayed"] += 1


def _greedy_cluster(memories: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Greedy cluster by cosine ≥ 0.7. O(N*K) where K = number of clusters.

    Good enough for pilot-scale (≤ 5 users, hundreds of memories). Replace
    with hierarchical clustering when the corpus crosses ~10k memories.
    """
    clusters: list[list[dict[str, Any]]] = []
    for mem in memories:
        embedding = mem.get("embedding") or []
        placed = False
        for cluster in clusters:
            seed_embedding = cluster[0].get("embedding") or []
            if _cosine(embedding, seed_embedding) >= _CLUSTER_COSINE_THRESHOLD:
                cluster.append(mem)
                placed = True
                break
        if not placed:
            clusters.append([mem])
    return clusters


async def _detect_contradictions(
    memories_coll: Any, cluster: list[dict[str, Any]], counters: dict[str, int]
) -> None:
    """Pairwise-classify contradictions within the cluster. Mark losers superseded."""
    llm = None
    try:
        llm = LLMService.get_llm_by_agent(
            settings.memory_extraction_agent, streaming=False, temperature=0.0
        )
    except Exception:
        logger.debug("_detect_contradictions: LLM unavailable; skipping", exc_info=True)
        return

    # Compare each pair once — (i, j) where i < j
    for i in range(len(cluster)):
        for j in range(i + 1, len(cluster)):
            a, b = cluster[i], cluster[j]
            prompt = get_processed_prompt(
                "memory_contradiction_detector",
                template_vars={
                    "fact_a": a["fact"],
                    "domain_a": a["domain"],
                    "created_at_a": str(a.get("created_at", "")),
                    "fact_b": b["fact"],
                    "domain_b": b["domain"],
                    "created_at_b": str(b.get("created_at", "")),
                },
            )
            try:
                response = await llm.ainvoke(prompt)
                content = getattr(response, "content", None) or ""
                parsed = _parse_contradiction(content)
            except Exception:
                logger.debug("_detect_contradictions: LLM call failed", exc_info=True)
                continue

            if not parsed.get("contradicts"):
                continue

            # Older one loses
            a_created = a.get("created_at")
            b_created = b.get("created_at")
            older = a if (a_created or datetime.min) <= (b_created or datetime.min) else b
            _mark_superseded(memories_coll, older)
            counters["superseded"] += 1


def _mark_superseded(memories_coll: Any, mem: dict[str, Any]) -> None:
    """Apply the supersede decay to a single memory."""
    memories_coll.update_one(
        {"memory_id": mem["memory_id"]},
        {
            "$set": {
                "importance": float(mem.get("importance", 0.5)) * 0.3,
                "salience": float(mem.get("salience", 1.0)) * 0.5,
                "superseded_at": datetime.now(tz=timezone.utc),
            }
        },
    )


async def _emit_insight(
    insights_coll: Any,
    user_id: str,
    cluster: list[dict[str, Any]],
    counters: dict[str, int],
) -> None:
    """Summarize the cluster into one MemoryInsight + one embedding.

    Idempotent: `insight_id` is derived from the sorted member memory_ids so
    the same cluster upserts into the same row every scheduled run. This
    keeps the 30-minute APScheduler cadence from accumulating duplicate
    insights for a stable corpus. When cluster membership changes, the
    fingerprint changes and a new insight is written; the prior insight
    (now pointing to a subset) is left in place — Phase 3 GC is tracked.
    """
    summary = _summarize_cluster(cluster)
    domain = cluster[0].get("domain", "query-pattern")
    try:
        embedder = get_embedder()
        vec = await embedder.aembed_query(summary)  # type: ignore[attr-defined]
    except Exception:
        logger.debug("_emit_insight: embedding failed; dropping insight", exc_info=True)
        return

    sorted_member_ids = sorted(m["memory_id"] for m in cluster)
    insight_id = hashlib.sha256("|".join(sorted_member_ids).encode("utf-8")).hexdigest()[:32]

    try:
        result = insights_coll.update_one(
            {"insight_id": insight_id, "user_id": user_id},
            {
                "$set": {
                    "summary": summary,
                    "domain": domain,
                    "member_memory_ids": sorted_member_ids,
                    "embedding": list(vec),
                },
                "$setOnInsert": {
                    "insight_id": insight_id,
                    "user_id": user_id,
                    "created_at": datetime.now(tz=timezone.utc),
                },
            },
            upsert=True,
        )
        if result.upserted_id is not None:
            counters["insights"] += 1
    except Exception:
        logger.debug("_emit_insight: upsert failed", exc_info=True)


def _summarize_cluster(cluster: list[dict[str, Any]]) -> str:
    """Build a one-line summary. Uses facts directly — Phase 3 can replace with LLM."""
    facts = [m.get("fact", "") for m in cluster[:3]]
    if len(cluster) <= 3:
        return " | ".join(f for f in facts if f)
    return " | ".join(f for f in facts if f) + f" (+{len(cluster) - 3} more)"


def _parse_contradiction(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"contradicts": False}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)
