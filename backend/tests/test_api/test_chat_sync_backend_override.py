"""Tests for the per-request backend overrides on the non-streaming POST /chat.

The /sync CLI command routes through the synchronous chat() handler, so the
same Phase 2 Workstream A + B per-request toggles must apply there as on the
streaming path.

Pins:
- ``ChatRequest.coder_backend='sdk'`` causes ``resolve_agent_backend('coder')``
  to see ``AgentBackend.SDK`` during graph execution on the sync handler.
- ``ChatRequest.orchestrator_backend='sdk'`` likewise for the orchestrator.
- ContextVars are reset after the response is returned.
- Concurrent / sequential calls don't leak overrides across requests.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import app
from src.config.agent_backends import (
    coder_backend_context,
    orchestrator_backend_context,
    resolve_agent_backend,
)


class _AgentObservingBackend:
    """Records what the resolver sees inside the sync graph invocation."""

    def __init__(self, coder_observed: list[str], orch_observed: list[str]) -> None:
        self._coder_observed = coder_observed
        self._orch_observed = orch_observed

    async def ainvoke(self, state: dict[str, Any], config: dict | None = None) -> dict:
        self._coder_observed.append(resolve_agent_backend("coder").value)
        self._orch_observed.append(resolve_agent_backend("orchestrator").value)
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="ok")]}


class _BuilderObservingBackend:
    def __init__(self, coder_observed: list[str], orch_observed: list[str]) -> None:
        self._coder_observed = coder_observed
        self._orch_observed = orch_observed

    def compile(self, checkpointer=None):
        return _AgentObservingBackend(self._coder_observed, self._orch_observed)


@pytest.fixture
def _patch_graph_and_checkpointer(monkeypatch):
    """Replace the real graph + checkpointer so the test runs cheaply."""
    from src.api.routes import chat as chat_mod

    coder_observed: list[str] = []
    orch_observed: list[str] = []
    monkeypatch.setattr(
        chat_mod, "graph_builder", _BuilderObservingBackend(coder_observed, orch_observed)
    )

    @asynccontextmanager
    async def _fake_checkpointer():
        yield object()

    monkeypatch.setattr(chat_mod, "create_checkpointer", _fake_checkpointer)

    class _FakeConversationService:
        def get_conversation(self, *a, **kw):
            return {"exists": True}

        def update_timestamp(self, *a, **kw):
            return None

        def create_conversation(self, *a, **kw):
            return None

        async def auto_generate_and_update_title(self, **kw):
            return None

    import src.service.storage.conversation_service as conv_mod

    monkeypatch.setattr(conv_mod, "ConversationService", _FakeConversationService)

    return coder_observed, orch_observed


def test_sync_chat_coder_sdk_override_is_set_during_request(
    monkeypatch, _patch_graph_and_checkpointer
):
    """coder_backend='sdk' on POST /chat → graph sees SDK via resolver."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")

    coder_observed, _ = _patch_graph_and_checkpointer
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hello", "coder_backend": "sdk"})
    assert resp.status_code == 200, resp.text

    assert coder_observed, "graph should have observed at least one resolve call"
    assert "sdk" in coder_observed
    # ContextVar reset after handler returns.
    assert coder_backend_context.get() is None


def test_sync_chat_orchestrator_sdk_override_is_set_during_request(
    monkeypatch, _patch_graph_and_checkpointer
):
    """orchestrator_backend='sdk' on POST /chat → orchestrator resolver sees SDK."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "orchestrator_backend", "langchain")

    _, orch_observed = _patch_graph_and_checkpointer
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hi", "orchestrator_backend": "sdk"})
    assert resp.status_code == 200

    assert orch_observed
    assert "sdk" in orch_observed
    assert orchestrator_backend_context.get() is None


def test_sync_chat_no_override_falls_back_to_settings(monkeypatch, _patch_graph_and_checkpointer):
    """Missing fields → resolver reads settings; ContextVars stay unset."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "orchestrator_backend", "langchain")

    coder_observed, orch_observed = _patch_graph_and_checkpointer
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hi"})
    assert resp.status_code == 200

    assert coder_observed and all(b == "langchain" for b in coder_observed)
    assert orch_observed and all(b == "langchain" for b in orch_observed)
    assert coder_backend_context.get() is None
    assert orchestrator_backend_context.get() is None


def test_sync_chat_invalid_coder_backend_rejected_by_pydantic():
    """Bogus value rejected at the request boundary with 422 — same as /stream."""
    client = TestClient(app)
    resp = client.post("/chat", json={"message": "hi", "coder_backend": "anthropic"})
    assert resp.status_code == 422


def test_sync_chat_override_does_not_leak_across_requests(
    monkeypatch, _patch_graph_and_checkpointer
):
    """Sequential calls with different overrides stay isolated."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")

    coder_observed, _ = _patch_graph_and_checkpointer
    client = TestClient(app)

    resp = client.post("/chat", json={"message": "first", "coder_backend": "sdk"})
    assert resp.status_code == 200
    first = list(coder_observed)
    coder_observed.clear()

    resp = client.post("/chat", json={"message": "second"})
    assert resp.status_code == 200
    second = list(coder_observed)

    assert "sdk" in first
    assert second and all(b == "langchain" for b in second)
    assert coder_backend_context.get() is None
