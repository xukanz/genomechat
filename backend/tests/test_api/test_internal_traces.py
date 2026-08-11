"""Integration tests for /internal/traces and /internal/health/agent-backends."""

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
    """Build a TestClient with a mongomock-backed observability path and bypassed auth."""
    from main import app
    from src.service.auth.dependencies import get_current_user
    from src.service.observability import access as access_mod
    from src.api.routes import internal_traces as it_mod

    monkeypatch.setattr(access_mod.settings, "mongodb_db_name", "test_db")
    monkeypatch.setattr(access_mod.settings, "internal_observability_rate_limit_per_hour", 1000)
    monkeypatch.setattr(access_mod, "get_mongodb_client", lambda: mongomock_client)
    monkeypatch.setattr(it_mod, "get_mongodb_client", lambda: mongomock_client)

    app.dependency_overrides[get_current_user] = lambda: _make_user("alice")

    yield TestClient(app)

    app.dependency_overrides.pop(get_current_user, None)


def test_agent_backends_health(api_client):
    r = api_client.get("/internal/health/agent-backends")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1"
    names = {a["agent"] for a in body["agents"]}
    assert names == {"coder", "orchestrator"}
    for row in body["agents"]:
        assert row["backend"] == "langchain"


def test_list_traces_own_tenant_returns_owned_spans(api_client, mongomock_client, monkeypatch):
    monkeypatch.setenv("dummy", "1")  # ensure no test suite assumes env var
    coll = mongomock_client["test_db"]["traces"]
    # Owned span
    coll.insert_one(
        {
            "schema_version": "1",
            "trace_id": "t1",
            "span_id": "s1",
            "parent_span_id": None,
            "name": "agent.node.coder",
            "kind": "INTERNAL",
            "start_time": datetime.now(tz=timezone.utc),
            "end_time": datetime.now(tz=timezone.utc),
            "duration_ms": 10.0,
            "status": {"code": "OK"},
            "attributes": {"agent.thread_id": "alice:conv-1"},
            "events": [],
            "active_skills": [],
            "thread_id": "alice:conv-1",
            "tenant_id": "alice",
        }
    )
    # Other tenant's span
    coll.insert_one(
        {
            "schema_version": "1",
            "trace_id": "t2",
            "span_id": "s2",
            "parent_span_id": None,
            "name": "agent.node.coder",
            "kind": "INTERNAL",
            "start_time": datetime.now(tz=timezone.utc),
            "end_time": datetime.now(tz=timezone.utc),
            "duration_ms": 10.0,
            "status": {"code": "OK"},
            "attributes": {"agent.thread_id": "bob:conv-9"},
            "events": [],
            "active_skills": [],
            "thread_id": "bob:conv-9",
            "tenant_id": "bob",
        }
    )

    r = api_client.get("/internal/traces")
    assert r.status_code == 200
    names = [s["trace_id"] for s in r.json()["spans"]]
    assert "t1" in names
    assert "t2" not in names


def test_cross_tenant_thread_id_returns_404_for_non_admin(api_client, mongomock_client):
    r = api_client.get("/internal/traces?thread_id=bob:conv-9")
    assert r.status_code == 404


def test_wildcard_thread_id_rejected_for_non_admin(api_client):
    r = api_client.get("/internal/traces?thread_id=bob:*")
    assert r.status_code == 400


def test_admin_scope_enables_cross_tenant(api_client, mongomock_client, monkeypatch):
    # Grant the admin scope to alice
    mongomock_client["test_db"]["users"].insert_one(
        {"id": "alice", "scopes": ["traces:admin:cross-tenant"]}
    )
    coll = mongomock_client["test_db"]["traces"]
    coll.insert_one(
        {
            "schema_version": "1",
            "trace_id": "t-cross",
            "span_id": "s-cross",
            "parent_span_id": None,
            "name": "agent.node.coder",
            "kind": "INTERNAL",
            "start_time": datetime.now(tz=timezone.utc),
            "end_time": datetime.now(tz=timezone.utc),
            "duration_ms": 10.0,
            "status": {"code": "OK"},
            "attributes": {"agent.thread_id": "bob:conv-9"},
            "events": [],
            "active_skills": [],
            "thread_id": "bob:conv-9",
            "tenant_id": "bob",
        }
    )
    r = api_client.get("/internal/traces?thread_id=bob:conv-9")
    assert r.status_code == 200
    trace_ids = [s["trace_id"] for s in r.json()["spans"]]
    assert "t-cross" in trace_ids


def test_raw_endpoint_501_for_non_holder(api_client):
    r = api_client.get("/internal/traces/raw")
    assert r.status_code == 403  # missing traces:raw scope


def test_access_log_written(api_client, mongomock_client):
    api_client.get("/internal/health/agent-backends")
    rows = list(mongomock_client["test_db"]["observability_access_log"].find())
    assert any(r.get("path") == "/internal/health/agent-backends" for r in rows)


def test_list_traces_returns_full_trace_tree(api_client, mongomock_client):
    """Regression for Codex Finding 2 — with thread_id propagated onto tool
    and LLM spans, /internal/traces must return node + tool + LLM spans for
    the same conversation. Before the fix, only node spans survived tenant
    scoping because tool/LLM docs had empty thread_id/tenant_id.
    """
    coll = mongomock_client["test_db"]["traces"]
    now = datetime.now(tz=timezone.utc)

    def _doc(name: str, span_id: str, attrs: dict) -> dict:
        return {
            "schema_version": "1",
            "trace_id": "trace-alice",
            "span_id": span_id,
            "parent_span_id": None,
            "name": name,
            "kind": "INTERNAL",
            "start_time": now,
            "end_time": now,
            "duration_ms": 5.0,
            "status": {"code": "OK"},
            "attributes": attrs,
            "events": [],
            "active_skills": [],
            "thread_id": "alice:conv-full",
            "tenant_id": "alice",
        }

    coll.insert_many(
        [
            _doc("agent.node.coder", "sn1", {"agent.thread_id": "alice:conv-full"}),
            _doc(
                "agent.tool.execute_code",
                "st1",
                {"tool.name": "execute_code", "agent.thread_id": "alice:conv-full"},
            ),
            _doc(
                "gen_ai.chat",
                "sl1",
                {
                    "gen_ai.request.model": "claude-haiku-4-5",
                    "agent.thread_id": "alice:conv-full",
                },
            ),
        ]
    )

    r = api_client.get("/internal/traces?thread_id=alice:conv-full")
    assert r.status_code == 200
    names = sorted(s["name"] for s in r.json()["spans"])
    assert names == ["agent.node.coder", "agent.tool.execute_code", "gen_ai.chat"]
