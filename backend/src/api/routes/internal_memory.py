"""Internal `/internal/memory` endpoints.

Reuses Phase 0 access-control machinery wholesale:
- `require_scopes` — gate each endpoint by explicit scope set
- `enforce_rate_limit` — shared 1-hour sliding window against observability_access_log
- `write_access_log` — every call produces an audit row

Cross-tenant requests return 404 (not 403) to match `/internal/traces` behavior
— don't leak the existence of other tenants' memory collections.

Embeddings are NEVER returned: the response model drops them and the
MongoDB projection excludes them so a future route change can't accidentally
leak them either.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.config.settings import settings
from src.models.observability import (
    MemoryConsolidationResponse,
    MemoryPreview,
    MemoryRetrievalResponse,
)
from src.models.user import User
from src.service.database.connections.mongodb_connection import get_mongodb_client
from src.service.observability.access import (
    _user_scopes,
    enforce_rate_limit,
    require_scopes,
    write_access_log,
)

logger = logging.getLogger(__name__)


MEMORY_READ_SCOPE = "memory:read:own"
MEMORY_ADMIN_SCOPE = "memory:admin"


router = APIRouter(prefix="/internal/memory", tags=["internal"])


@router.get("", response_model=MemoryRetrievalResponse)
async def list_memories(
    request: Request,
    query: str | None = Query(default=None, description="Optional retrieval query"),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_scopes({MEMORY_READ_SCOPE})),
) -> MemoryRetrievalResponse:
    """List memories for the caller, or run a retrieval preview when `query` is set.

    Non-admin callers can only read their own memories; cross-tenant requests
    return 404 to match `/internal/traces` behavior.
    """
    await enforce_rate_limit(user)
    scopes = _user_scopes(user)
    is_admin = MEMORY_ADMIN_SCOPE in scopes
    target_user_id = user_id or user.id

    if target_user_id != user.id and not is_admin:
        write_access_log(
            request=request,
            caller=user,
            target_tenant=target_user_id,
            scopes_used=scopes,
            row_count=0,
            response_status=404,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    try:
        if query:
            from src.service.memory.retriever import retrieve_memories

            retrieved = await retrieve_memories(query=query, user_id=target_user_id, k=limit)
            memories = [
                MemoryPreview(
                    memory_id=r.memory.memory_id,
                    fact=r.memory.fact,
                    domain=r.memory.domain,
                    importance=r.memory.importance,
                    salience=r.memory.salience,
                    created_at=r.memory.created_at,
                    updated_at=r.memory.updated_at,
                )
                for r in retrieved
            ]
            total = len(memories)
        else:
            coll = get_mongodb_client()[settings.mongodb_db_name]["research_memories"]
            # Projection drops embedding — governance invariant
            cursor = (
                coll.find(
                    {"user_id": target_user_id},
                    {
                        "_id": 0,
                        "memory_id": 1,
                        "fact": 1,
                        "domain": 1,
                        "importance": 1,
                        "salience": 1,
                        "created_at": 1,
                        "updated_at": 1,
                    },
                )
                .sort([("salience", -1), ("updated_at", -1)])
                .limit(limit)
            )
            memories = [MemoryPreview.model_validate(doc) for doc in cursor]
            total = coll.count_documents({"user_id": target_user_id})
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_memories: storage query failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory storage unavailable",
        )

    write_access_log(
        request=request,
        caller=user,
        target_tenant=target_user_id,
        scopes_used=scopes,
        row_count=len(memories),
    )
    return MemoryRetrievalResponse(memories=memories, total=total)


@router.post("/consolidate", response_model=MemoryConsolidationResponse)
async def trigger_consolidation(
    request: Request,
    user_id: str | None = Query(default=None),
    user: User = Depends(require_scopes({MEMORY_READ_SCOPE})),
) -> MemoryConsolidationResponse:
    """Manually trigger consolidation for a single user.

    Non-admin callers can only run their own consolidation. `memory:admin`
    grants are processed the same way as `traces:admin:cross-tenant` — via
    MongoDB `users.scopes` with an audit-log entry (see Phase 0 guide).
    """
    await enforce_rate_limit(user)
    scopes = _user_scopes(user)
    is_admin = MEMORY_ADMIN_SCOPE in scopes
    target_user_id = user_id or user.id

    if target_user_id != user.id and not is_admin:
        write_access_log(
            request=request,
            caller=user,
            target_tenant=target_user_id,
            scopes_used=scopes,
            row_count=0,
            response_status=404,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    from src.service.memory.consolidator import run_consolidation

    try:
        counters = await run_consolidation(user_id=target_user_id)
    except Exception:
        logger.exception("trigger_consolidation: unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Consolidation failed",
        )

    write_access_log(
        request=request,
        caller=user,
        target_tenant=target_user_id,
        scopes_used=scopes,
        row_count=counters.get("users_processed", 0),
    )
    return MemoryConsolidationResponse(counters=counters)
