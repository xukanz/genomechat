"""Integration tests for /internal/memory and /internal/memory/consolidate.

Mirrors the fixture/style of `test_internal_traces.py` — bypasses auth via
FastAPI dependency override and points the memory access-log queries at
mongomock.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.models.user import User


def _make_user(user_id: str = "alice") -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        name=user_id.title(),
        role="user",
        created_at=datetime.now(tz=timezone.utc),
    )


@pytest.fixture
def api_client(mongomock_client, monkeypatch):
    """TestClient with mongomock-backed memory path and bypassed auth."""
    from main import app
    from src.api.routes import internal_memory as im_mod
    from src.service.auth.dependencies import get_current_user
    from src.service.observability import access as access_mod

    monkeypatch.setattr(access_mod.settings, "mongodb_db_name", "test_db")
    monkeypatch.setattr(access_mod.settings, "internal_observability_rate_limit_per_hour", 1000)
    monkeypatch.setattr(im_mod.settings, "mongodb_db_name", "test_db")
    monkeypatch.setattr(access_mod, "get_mongodb_client", lambda: mongomock_client)
    monkeypatch.setattr(im_mod, "get_mongodb_client", lambda: mongomock_client)

    # The grant scope lookup reads users collection; default to memory:read:own
    mongomock_client["test_db"]["users"].insert_one({"id": "alice", "scopes": ["memory:read:own"]})

    app.dependency_overrides[get_current_user] = lambda: _make_user("alice")
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user, None)


def _insert_memory(mongomock_client, user_id: str, memory_id: str, fact: str) -> None:
    now = datetime.now(tz=timezone.utc)
    mongomock_client["test_db"]["research_memories"].insert_one(
        {
            "memory_id": memory_id,
            "user_id": user_id,
            "project_id": None,
            "thread_id": None,
            "database_id": None,
            "fact": fact,
            "domain": "user-preference",
            "importance": 0.7,
            "salience": 1.0,
            "embedding": [0.1, 0.2, 0.3],  # NOT returned by the API
            "pinned": False,
            "superseded_at": None,
            "created_at": now,
            "updated_at": now,
            "access_count": 0,
            "last_accessed_at": None,
        }
    )


def test_list_memories_scoped_to_caller(api_client, mongomock_client):
    _insert_memory(mongomock_client, user_id="alice", memory_id="a1", fact="alice fact")
    _insert_memory(mongomock_client, user_id="bob", memory_id="b1", fact="bob fact")

    r = api_client.get("/internal/memory")
    assert r.status_code == 200
    body = r.json()
    ids = [m["memory_id"] for m in body["memories"]]
    assert "a1" in ids
    assert "b1" not in ids  # tenant scoping
    assert body["schema_version"] == "1"


def test_list_memories_omits_embedding(api_client, mongomock_client):
    _insert_memory(mongomock_client, user_id="alice", memory_id="a1", fact="x")
    r = api_client.get("/internal/memory")
    body = r.json()
    for m in body["memories"]:
        assert "embedding" not in m  # governance invariant


def test_cross_tenant_request_returns_404_for_non_admin(api_client, mongomock_client):
    _insert_memory(mongomock_client, user_id="bob", memory_id="b1", fact="bob fact")
    r = api_client.get("/internal/memory?user_id=bob")
    assert r.status_code == 404


def test_admin_scope_enables_cross_tenant(api_client, mongomock_client):
    _insert_memory(mongomock_client, user_id="bob", memory_id="b1", fact="bob fact")
    mongomock_client["test_db"]["users"].update_one(
        {"id": "alice"}, {"$set": {"scopes": ["memory:read:own", "memory:admin"]}}
    )
    r = api_client.get("/internal/memory?user_id=bob")
    assert r.status_code == 200
    ids = [m["memory_id"] for m in r.json()["memories"]]
    assert "b1" in ids


def test_missing_scope_returns_403(api_client, mongomock_client):
    mongomock_client["test_db"]["users"].update_one({"id": "alice"}, {"$set": {"scopes": []}})
    r = api_client.get("/internal/memory")
    assert r.status_code == 403


def test_consolidate_endpoint_runs_for_caller(api_client, mongomock_client):
    _insert_memory(mongomock_client, user_id="alice", memory_id="a1", fact="x")
    r = api_client.post("/internal/memory/consolidate")
    assert r.status_code == 200
    body = r.json()
    assert "counters" in body
    assert body["schema_version"] == "1"


def test_consolidate_cross_tenant_returns_404_for_non_admin(api_client, mongomock_client):
    r = api_client.post("/internal/memory/consolidate?user_id=bob")
    assert r.status_code == 404


def test_access_log_written_for_memory_endpoint(api_client, mongomock_client):
    api_client.get("/internal/memory")
    rows = list(mongomock_client["test_db"]["observability_access_log"].find())
    assert any(r.get("path") == "/internal/memory" for r in rows)
