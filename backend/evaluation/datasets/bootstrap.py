"""Build a consent-filtered trajectory replay dataset from MongoDB conversations.

Output one JSON line per conversation's final user turn:
    {query, thread_id, database_id, project_id, user_id,
     source_conversation_id, captured_at}

No response text is persisted — `harness.replay` recaptures responses against
the current graph. The dataset file is git-ignored; only `baselines/*.jsonl`
replay outputs are committed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.settings import settings

logger = logging.getLogger(__name__)


MIN_DATASET_SIZE = 1  # sanity floor; Phase 0 target is ≥ 200 real queries


def _parse_consented_user_ids() -> list[str]:
    raw = (settings.eval_consented_user_ids or "").strip()
    if not raw:
        return []
    return [u.strip() for u in raw.split(",") if u.strip()]


async def build_dataset(out_path: Path) -> int:
    """Enumerate MongoDB conversations for consented users and emit JSONL.

    Returns the number of records written. Raises on I/O failure or empty corpus.
    """
    consented = _parse_consented_user_ids()
    if not consented:
        raise RuntimeError(
            "eval_consented_user_ids is empty. Set EVAL_CONSENTED_USER_IDS "
            "(comma-separated) to the pilot user IDs before running bootstrap."
        )

    from src.service.database.connections.mongodb_connection import get_mongodb_client

    client = get_mongodb_client()
    conversations = client[settings.mongodb_db_name]["conversations"]

    records: list[dict[str, Any]] = []
    for user_id in consented:
        cursor = conversations.find({"user_id": user_id}).sort("updated_at", -1)
        for conv in cursor:
            query = await _extract_final_user_query(conv)
            if not query:
                continue
            records.append(
                {
                    "query": query,
                    "thread_id": conv.get("thread_id")
                    or f"{user_id}:{conv.get('conversation_id', '')}",
                    "database_id": conv.get("database_id") or "",
                    "project_id": conv.get("project_id") or "",
                    "user_id": user_id,
                    "source_conversation_id": conv.get("conversation_id") or "",
                    "captured_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            )

    if len(records) < MIN_DATASET_SIZE:
        raise RuntimeError(
            f"Consented corpus yielded only {len(records)} record(s); expected ≥ "
            f"{MIN_DATASET_SIZE}. Verify EVAL_CONSENTED_USER_IDS and that those "
            "users have conversations in MongoDB."
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    logger.info("Wrote %d records to %s", len(records), out_path)
    return len(records)


async def _extract_final_user_query(conv: dict[str, Any]) -> str | None:
    """Pull the final human-authored query from the LangGraph checkpoint for this conv.

    Only accepts messages with `type in ("human", "user")` AND an empty `name`.
    LangChain's user-input HumanMessage never sets `name`; the platform's
    synthetic rewrites always do — coordinator_node stores its direct response
    as HumanMessage(name="coordinator"), and the worker-prep path remaps
    orchestrator output to HumanMessage(name="orchestrator_task"). Without
    the name filter, the last human-type message in a short/direct-response
    conversation is the model's answer, not the user's prompt.

    Conversations without a checkpoint or without a real user message are
    dropped (returned None) — the caller filters them out.
    """
    thread_id = conv.get("thread_id")
    if not thread_id:
        return None
    try:
        from src.graph.checkpointer import create_checkpointer

        async with create_checkpointer() as checkpointer:
            state = None
            async for state in checkpointer.alist(
                config={"configurable": {"thread_id": thread_id}},
                limit=1,
            ):
                break
            if state is None:
                return None
            messages = (state.checkpoint or {}).get("channel_values", {}).get("messages", [])
            # Walk backwards to find the last genuine user-authored HumanMessage.
            for msg in reversed(messages):
                if isinstance(msg, dict):
                    msg_type = msg.get("type")
                    name = msg.get("name")
                    content = msg.get("content")
                else:
                    msg_type = getattr(msg, "type", None)
                    name = getattr(msg, "name", None)
                    content = getattr(msg, "content", None)
                if msg_type not in ("human", "user"):
                    continue
                if name:  # synthetic rewrite — skip
                    continue
                if isinstance(content, str) and content.strip():
                    return content.strip()
    except Exception:
        logger.exception("bootstrap: failed to read checkpoint for thread %s", thread_id)
    return None


def run(out_path: str) -> int:
    """Synchronous entrypoint (for CLI use)."""
    return asyncio.run(build_dataset(Path(out_path)))
