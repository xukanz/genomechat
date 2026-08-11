"""Tests for the Phase 2 per-request ``orchestrator_backend`` override.

Mirror of ``test_chat_coder_backend_override.py`` applied to the orchestrator
worker. Pins the Workstream B contract:

- ``ChatRequest.orchestrator_backend='sdk'`` causes
  ``resolve_agent_backend('orchestrator')`` to see ``AgentBackend.SDK``
  during graph execution.
- ``ChatRequest.orchestrator_backend='langchain'`` forces LangChain even when
  ``settings.orchestrator_backend='sdk'``.
- Missing / None ``orchestrator_backend`` leaves the ContextVar unset, so the
  resolver falls back to settings.
- The ContextVar is reset after the stream finishes.
- Concurrent streams with different ``orchestrator_backend`` values stay
  isolated — and setting orchestrator_backend doesn't bleed into coder_backend.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import app
from src.config.agent_backends import (
    coder_backend_context,
    orchestrator_backend_context,
    resolve_agent_backend,
)


class _OrchObservingBackend:
    """Fake graph agent recording the resolved orchestrator backend.

    We record for BOTH workers so one assertion proves the coder/orchestrator
    ContextVars don't cross-contaminate.
    """

    def __init__(self, orch_observed: list[str], coder_observed: list[str]) -> None:
        self._orch_observed = orch_observed
        self._coder_observed = coder_observed

    async def astream_events(self, *args: Any, **kwargs: Any):
        self._orch_observed.append(resolve_agent_backend("orchestrator").value)
        self._coder_observed.append(resolve_agent_backend("coder").value)
        if False:  # pragma: no cover — make this function a generator
            yield {}
        return

    async def aget_state(self, config: dict | None = None):
        class _S:
            values: dict = {"messages": []}

        return _S()


class _OrchBuilder:
    def __init__(self, orch_observed: list[str], coder_observed: list[str]) -> None:
        self._orch_observed = orch_observed
        self._coder_observed = coder_observed

    def compile(self, checkpointer=None):
        return _OrchObservingBackend(self._orch_observed, self._coder_observed)


@pytest.fixture
def _patch_graph_and_checkpointer(monkeypatch):
    """Swap the real graph + checkpointer for the orchestrator-observing fakes."""
    from contextlib import asynccontextmanager

    from src.api.routes import chat as chat_mod

    orch_observed: list[str] = []
    coder_observed: list[str] = []
    monkeypatch.setattr(chat_mod, "graph_builder", _OrchBuilder(orch_observed, coder_observed))

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

    from src.config.settings import settings as _s

    monkeypatch.setattr(_s, "memory_extraction_enabled", False)

    return orch_observed, coder_observed


def _consume_stream(resp) -> list[dict]:
    events = []
    for line in resp.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode()
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                continue
    return events


def test_stream_chat_orchestrator_sdk_override_is_set_during_request(
    monkeypatch, _patch_graph_and_checkpointer
):
    """orchestrator_backend='sdk' on the request body → graph sees SDK via the resolver."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "orchestrator_backend", "langchain")
    monkeypatch.setattr(settings, "coder_backend", "langchain")

    orch_observed, _ = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "run analysis", "orchestrator_backend": "sdk"},
    ) as resp:
        _consume_stream(resp)

    assert orch_observed, "expected the fake graph to observe at least one resolve call"
    assert "sdk" in orch_observed, (
        f"expected 'sdk' in orchestrator backends observed; got {orch_observed!r}"
    )
    assert orchestrator_backend_context.get() is None


def test_stream_chat_orchestrator_langchain_override_beats_settings_sdk_default(
    monkeypatch, _patch_graph_and_checkpointer
):
    """orchestrator_backend='langchain' wins even when settings.orchestrator_backend='sdk'."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "orchestrator_backend", "sdk")
    monkeypatch.setattr(settings, "coder_backend", "langchain")

    orch_observed, _ = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "hi", "orchestrator_backend": "langchain"},
    ) as resp:
        _consume_stream(resp)

    assert orch_observed
    assert all(b == "langchain" for b in orch_observed), (
        f"per-request override must win over settings; got {orch_observed!r}"
    )
    assert orchestrator_backend_context.get() is None


def test_stream_chat_no_orchestrator_override_falls_back_to_settings(
    monkeypatch, _patch_graph_and_checkpointer
):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "orchestrator_backend", "langchain")
    monkeypatch.setattr(settings, "coder_backend", "langchain")

    orch_observed, _ = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "hi"},
    ) as resp:
        _consume_stream(resp)

    assert orch_observed
    assert all(b == "langchain" for b in orch_observed)
    assert orchestrator_backend_context.get() is None


def test_stream_chat_invalid_orchestrator_backend_rejected_by_pydantic():
    client = TestClient(app)
    resp = client.post(
        "/chat/stream",
        json={"message": "hi", "orchestrator_backend": "anthropic"},
    )
    assert resp.status_code == 422


def test_stream_chat_both_backends_flip_independently(monkeypatch, _patch_graph_and_checkpointer):
    """A request can pick coder and orchestrator independently without cross-leak.

    This is the crucial invariant for the 2x2 evaluation matrix — if the
    two ContextVars ever aliased, the matrix would produce garbage.
    """
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "orchestrator_backend", "langchain")

    orch_observed, coder_observed = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "message": "mixed run",
            "coder_backend": "sdk",
            "orchestrator_backend": "langchain",
        },
    ) as resp:
        _consume_stream(resp)

    # Coder resolved to SDK (per-request wins)
    assert coder_observed and all(b == "sdk" for b in coder_observed), (
        f"coder should resolve to SDK given the override; got {coder_observed!r}"
    )
    # Orchestrator resolved to LangChain (per-request wins over settings default)
    assert orch_observed and all(b == "langchain" for b in orch_observed), (
        f"orchestrator should resolve to LangChain given the override; got {orch_observed!r}"
    )
    # Both ContextVars cleaned up
    assert coder_backend_context.get() is None
    assert orchestrator_backend_context.get() is None


def test_stream_chat_orchestrator_override_does_not_leak_across_requests(
    monkeypatch, _patch_graph_and_checkpointer
):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "orchestrator_backend", "langchain")
    monkeypatch.setattr(settings, "coder_backend", "langchain")

    orch_observed, _ = _patch_graph_and_checkpointer
    client = TestClient(app)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "first", "orchestrator_backend": "sdk"},
    ) as resp:
        _consume_stream(resp)

    first = list(orch_observed)
    orch_observed.clear()

    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "second"},  # no override — falls back to settings
    ) as resp:
        _consume_stream(resp)

    second = list(orch_observed)

    assert "sdk" in first
    assert second and all(b == "langchain" for b in second), (
        f"second request leaked SDK from first; got {second!r}"
    )
    assert orchestrator_backend_context.get() is None


@pytest.mark.asyncio
async def test_concurrent_streams_preserve_orchestrator_backend_isolation(
    monkeypatch, _patch_graph_and_checkpointer
):
    """Two concurrent streams with different orchestrator_backend must not cross-talk."""
    from httpx import ASGITransport, AsyncClient

    orch_observed, _ = _patch_graph_and_checkpointer

    async def _one(orch_backend: str) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async with ac.stream(
                "POST",
                "/chat/stream",
                json={"message": "go", "orchestrator_backend": orch_backend},
            ) as resp:
                async for _ in resp.aiter_lines():
                    pass

    for _ in range(3):
        orch_observed.clear()
        await asyncio.gather(_one("sdk"), _one("langchain"))
        assert "sdk" in orch_observed and "langchain" in orch_observed, (
            f"expected both backends to be observed; got {orch_observed!r}"
        )

    assert orchestrator_backend_context.get() is None
