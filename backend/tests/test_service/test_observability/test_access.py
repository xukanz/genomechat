"""Unit tests for observability/access.py."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.service.observability import access as access_mod


def _make_user(user_id: str = "u-1"):
    from src.models.user import User

    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name="Test",
        role="user",
        created_at=datetime.now(tz=timezone.utc),
    )


def test_user_scopes_includes_default_when_db_empty(mongomock_client):
    u = _make_user()
    with patch.object(access_mod, "get_mongodb_client", return_value=mongomock_client):
        scopes = access_mod._user_scopes(u)
    assert "traces:read:own" in scopes


def test_user_scopes_unions_db_grants(mongomock_client, monkeypatch):
    u = _make_user("admin-1")
    monkeypatch.setattr(access_mod.settings, "mongodb_db_name", "test_db")
    mongomock_client["test_db"]["users"].insert_one(
        {"id": "admin-1", "scopes": ["traces:admin:cross-tenant"]}
    )
    with patch.object(access_mod, "get_mongodb_client", return_value=mongomock_client):
        scopes = access_mod._user_scopes(u)
    assert "traces:admin:cross-tenant" in scopes
    assert "traces:read:own" in scopes


@pytest.mark.asyncio
async def test_require_scopes_403_when_missing(mongomock_client):
    from src.service.observability.access import require_scopes

    u = _make_user()
    dep = require_scopes({"traces:raw"})
    with patch.object(access_mod, "get_mongodb_client", return_value=mongomock_client):
        with pytest.raises(HTTPException) as exc:
            await dep(user=u)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_scopes_passes_with_admin_grant(mongomock_client, monkeypatch):
    from src.service.observability.access import require_scopes

    u = _make_user("admin")
    monkeypatch.setattr(access_mod.settings, "mongodb_db_name", "test_db")
    mongomock_client["test_db"]["users"].insert_one(
        {"id": "admin", "scopes": ["traces:admin:cross-tenant"]}
    )
    dep = require_scopes({"traces:admin:cross-tenant"})
    with patch.object(access_mod, "get_mongodb_client", return_value=mongomock_client):
        result = await dep(user=u)
    assert result is u


def test_write_access_log_inserts_row(mongomock_client, monkeypatch):
    from starlette.requests import Request

    monkeypatch.setattr(access_mod.settings, "mongodb_db_name", "test_db")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/internal/traces",
        "query_string": b"",
        "headers": [],
    }
    request = Request(scope)
    u = _make_user()
    with patch.object(access_mod, "get_mongodb_client", return_value=mongomock_client):
        access_mod.write_access_log(
            request=request,
            caller=u,
            target_tenant=u.id,
            scopes_used={"traces:read:own"},
            row_count=5,
        )
    rows = list(mongomock_client["test_db"]["observability_access_log"].find())
    assert len(rows) == 1
    assert rows[0]["caller_user_id"] == u.id
    assert rows[0]["row_count"] == 5


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_threshold(mongomock_client, monkeypatch):
    monkeypatch.setattr(access_mod.settings, "mongodb_db_name", "test_db")
    monkeypatch.setattr(access_mod.settings, "internal_observability_rate_limit_per_hour", 2)

    u = _make_user("rate-1")
    coll = mongomock_client["test_db"]["observability_access_log"]
    now = datetime.now(tz=timezone.utc)
    for _ in range(2):
        coll.insert_one({"caller_user_id": u.id, "timestamp": now})

    with patch.object(access_mod, "get_mongodb_client", return_value=mongomock_client):
        with pytest.raises(HTTPException) as exc:
            await access_mod.enforce_rate_limit(u)
    assert exc.value.status_code == 429
