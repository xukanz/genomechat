"""Internal `/internal/*` observability endpoints.

All routes enforce per-call scope checks, audit logging, and a sliding rate limit.
Tenant scoping is applied by default — a caller with only `traces:read:own` can
only query their own thread_ids. Cross-tenant reads require the
`traces:admin:cross-tenant` scope (manually granted).

Raw transcript retrieval (`traces:raw`) is reserved for Phase 1+; the relevant
endpoint returns 501 today.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.config.agent_backends import resolve_agent_backend
from src.config.settings import settings
from src.models.observability import (
    AgentBackendHealth,
    AgentBackendHealthResponse,
    TraceListResponse,
    TraceSpanSummary,
)
from src.models.user import User
from src.service.database.connections.mongodb_connection import get_mongodb_client
from src.service.observability.access import (
    CROSS_TENANT_SCOPE,
    _user_scopes,
    enforce_rate_limit,
    require_scopes,
    write_access_log,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/health/agent-backends", response_model=AgentBackendHealthResponse)
async def agent_backends_health(
    request: Request,
    user: User = Depends(require_scopes({"traces:read:own"})),
) -> AgentBackendHealthResponse:
    """Report the active backend per agent. Always returns the same shape."""
    await enforce_rate_limit(user)
    agents = [
        AgentBackendHealth(agent=name, backend=resolve_agent_backend(name).value)
        for name in ("coder", "orchestrator")
    ]
    write_access_log(
        request=request,
        caller=user,
        scopes_used={"traces:read:own"},
        row_count=len(agents),
    )
    return AgentBackendHealthResponse(agents=agents)


@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    request: Request,
    thread_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(require_scopes({"traces:read:own"})),
) -> TraceListResponse:
    """List spans filtered by thread_id with tenant scoping.

    - A caller without `traces:admin:cross-tenant` is restricted to thread IDs
      prefixed with their user_id (`<user_id>:<conversation_id>` per the
      platform's thread_id convention).
    - Cross-tenant reads require `traces:admin:cross-tenant` AND return 404 on
      explicit cross-tenant mismatch when the requester lacks the scope
      (don't leak existence).
    - `thread_id` wildcards / regex are rejected when the caller lacks the
      cross-tenant scope.
    """
    await enforce_rate_limit(user)
    scopes = _user_scopes(user)
    is_admin = CROSS_TENANT_SCOPE in scopes
    target_tenant: str | None = user.id

    if thread_id:
        if "*" in thread_id or "?" in thread_id:
            # Reject wildcards when not an admin
            if not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Wildcard thread_id requires admin scope",
                )
            target_tenant = None
        elif not is_admin and not thread_id.startswith(f"{user.id}:"):
            # Cross-tenant mismatch for a non-admin caller → 404 (not 403, per PRD §11)
            write_access_log(
                request=request,
                caller=user,
                target_thread_id=thread_id,
                scopes_used=scopes,
                row_count=0,
                response_status=404,
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        elif is_admin:
            target_tenant = thread_id.split(":", 1)[0] if ":" in thread_id else None

    try:
        client = get_mongodb_client()
        coll = client[settings.mongodb_db_name][settings.trace_mongodb_collection]
        mongo_filter: dict = {}
        if thread_id:
            mongo_filter["thread_id"] = thread_id
        elif not is_admin:
            mongo_filter["tenant_id"] = user.id

        total = coll.count_documents(mongo_filter)
        cursor = (
            coll.find(mongo_filter, {"_id": 0}).sort("start_time", -1).skip(offset).limit(limit)
        )
        spans = [
            TraceSpanSummary(
                trace_id=doc.get("trace_id", ""),
                span_id=doc.get("span_id", ""),
                parent_span_id=doc.get("parent_span_id"),
                name=doc.get("name", ""),
                start_time=doc["start_time"],
                duration_ms=float(doc.get("duration_ms", 0.0)),
                status_code=(doc.get("status") or {}).get("code", "UNSET"),
                attributes=doc.get("attributes", {}),
                events=doc.get("events", []),
                active_skills=list(doc.get("active_skills", [])),
            )
            for doc in cursor
        ]
    except HTTPException:
        raise
    except Exception:
        logger.exception("list_traces: failed to query MongoDB")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trace storage unavailable",
        )

    write_access_log(
        request=request,
        caller=user,
        target_tenant=target_tenant,
        target_thread_id=thread_id,
        scopes_used=scopes,
        row_count=len(spans),
    )
    return TraceListResponse(spans=spans, total=total, limit=limit, offset=offset)


@router.get("/traces/raw")
async def raw_traces_placeholder(
    request: Request,
    user: User = Depends(require_scopes({"traces:raw"})),
):
    """Raw transcript access — reserved for Phase 1+; stub returns 501."""
    write_access_log(
        request=request,
        caller=user,
        scopes_used={"traces:raw"},
        row_count=0,
        response_status=501,
    )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Raw transcript endpoint is reserved for Phase 1+",
    )
