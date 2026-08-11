"""Tenant-scoped access control for `/internal/*` observability endpoints.

Phase 0 delivers the wiring, not the admin UI:

- `traces:read:own`          — default scope on every authenticated JWT; the user
                                can read their own traces and health info
- `traces:admin:cross-tenant` — manual grant via MongoDB `users.scopes`; allows
                                querying traces across tenants (audit-logged)
- `traces:raw`                — reserved for Phase 1+ raw-transcript access;
                                stub returns 501 in Phase 0

Every call is audited in `observability_access_log`. Sliding-window rate limit
is enforced per caller at `settings.internal_observability_rate_limit_per_hour`.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from fastapi import Depends, HTTPException, Request, status

from src.config.settings import settings
from src.models.user import User
from src.service.auth.dependencies import get_current_user
from src.service.database.connections.mongodb_connection import get_mongodb_client

logger = logging.getLogger(__name__)


DEFAULT_SCOPES = {"traces:read:own"}
CROSS_TENANT_SCOPE = "traces:admin:cross-tenant"
RAW_SCOPE = "traces:raw"


def _user_scopes(user: User) -> set[str]:
    """Return the union of default scopes + any DB-granted scopes.

    Reads `users.scopes` (list[str]) from MongoDB if present; falls back to the
    default set when unset. Any exception during lookup degrades safely to the
    default scope set.
    """
    scopes: set[str] = set(DEFAULT_SCOPES)
    try:
        client = get_mongodb_client()
        record = client[settings.mongodb_db_name]["users"].find_one({"id": user.id}, {"scopes": 1})
        if record and isinstance(record.get("scopes"), list):
            scopes.update(str(s) for s in record["scopes"])
    except Exception:
        logger.debug("_user_scopes: DB lookup failed; falling back to defaults", exc_info=True)
    return scopes


def require_scopes(allowed: Iterable[str]):
    """FastAPI dependency factory. 401 if unauthenticated, 403 if missing scopes."""
    allowed_set = set(allowed)

    async def _dep(user: User = Depends(get_current_user)) -> User:
        scopes = _user_scopes(user)
        if not allowed_set.issubset(scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing required scope(s) for this endpoint",
            )
        return user

    return _dep


async def enforce_rate_limit(user: User) -> None:
    """Slide a 1-hour window of `observability_access_log` rows; raise on exceed.

    The audit-log collection is already keyed by caller + timestamp, so we reuse
    it as the counter substrate. No separate rate-limit collection needed.
    """
    limit = settings.internal_observability_rate_limit_per_hour
    if limit <= 0:
        return
    try:
        client = get_mongodb_client()
        coll = client[settings.mongodb_db_name]["observability_access_log"]
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        count = coll.count_documents({"caller_user_id": user.id, "timestamp": {"$gte": cutoff}})
        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Observability endpoint rate limit exceeded",
            )
    except HTTPException:
        raise
    except Exception:
        logger.debug("enforce_rate_limit: counter lookup failed; allowing", exc_info=True)


def write_access_log(
    *,
    request: Request,
    caller: User,
    target_tenant: Optional[str] = None,
    target_thread_id: Optional[str] = None,
    scopes_used: Iterable[str] = (),
    row_count: int = 0,
    response_status: int = 200,
) -> None:
    """Write one audit row; swallows DB errors so the user request still returns."""
    try:
        client = get_mongodb_client()
        coll = client[settings.mongodb_db_name]["observability_access_log"]
        # Indexes are cheap and idempotent; ensure on every write is acceptable at Phase 0 scale.
        try:
            coll.create_index([("caller_user_id", 1), ("timestamp", -1)])
            coll.create_index([("target_tenant", 1), ("timestamp", -1)])
        except Exception:
            pass
        coll.insert_one(
            {
                "caller_user_id": caller.id,
                "caller_email": caller.email,
                "target_tenant": target_tenant or caller.id,
                "target_thread_id": target_thread_id,
                "scopes_used": sorted(set(scopes_used)),
                "path": str(request.url.path),
                "query": dict(request.query_params),
                "row_count": row_count,
                "response_status": response_status,
                "timestamp": datetime.now(tz=timezone.utc),
            }
        )
    except Exception:
        logger.debug("write_access_log: insert failed (non-fatal)", exc_info=True)
