"""Tests for the Phase 2 per-request coder_backend override in stream_chat.

Pins the Workstream A contract:
- ``ChatRequest.coder_backend='sdk'`` causes ``resolve_agent_backend('coder')``
  to see ``AgentBackend.SDK`` during graph execution.
- ``ChatRequest.coder_backend='langchain'`` forces LangChain even when
  ``settings.coder_backend='sdk'``.
- Missing / None ``coder_backend`` leaves the ContextVar unset, so the
  resolver falls back to settings.
- The ContextVar is reset after the stream finishes, so a subsequent request
  on the same asyncio task doesn't see stale state.
- Concurrent streams with different ``coder_backend`` values stay isolated
  (regression for the Phase 1 Codex-review race).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import app
from src.config.agent_backends import (
    AgentBackend,
    coder_backend_context,
    resolve_agent_backend,
)


# ---------------------------------------------------------------------------
# Shared fakes — keep the graph lean so tests don't spin up MCP / Mongo.
# ---------------------------------------------------------------------------


class _AgentObservingBackend:
    """Fake graph agent whose ainvoke records the resolved coder backend.

    Records into a shared list so the test can assert what the graph observed
    while the event_generator was mid-stream.
    """

    def __init__(self, observed: list[str]) -> None:
        self._observed = observed

    async def ainvoke(self, state: dict[str, Any], config: dict | None = None) -> dict:
        self._observed.append(resolve_agent_backend("coder").value)
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="ok")]}

    async def astream_events(self, *args: Any, **kwargs: Any):
        # Record what the resolver sees during streaming (the thing we care about).
        self._observed.append(resolve_agent_backend("coder").value)
        # Emit a single no-op event so event_generator finishes cleanly.
        if False:
            yield {}
        return

    async def aget_state(self, config: dict | None = None):
        class _S:
            values: dict = {"messages": []}

        return _S()


class _BuilderObservingBackend:
    def __init__(self, observed: list[str]) -> None:
        self._observed = observed

    def compile(self, checkpointer=None):
        return _AgentObservingBackend(self._observed)


@pytest.fixture
def _patch_graph_and_checkpointer(monkeypatch):
    """Replace the real graph + checkpointer so we can drive stream_chat cheaply."""
    from contextlib import asynccontextmanager

    from src.api.routes import chat as chat_mod

    observed: list[str] = []
    monkeypatch.setattr(chat_mod, "graph_builder", _BuilderObservingBackend(observed))

    @asynccontextmanager
    async def _fake_checkpointer():
        yield object()

    monkeypatch.setattr(chat_mod, "create_checkpointer", _fake_checkpointer)

    # Stub conversation service so it doesn't touch Mongo.
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

    # Disable Phase 0.5 memory extraction so nothing touches Mongo / LLM.
    from src.config.settings import settings as _s

    monkeypatch.setattr(_s, "memory_extraction_enabled", False)

    return observed


# ---------------------------------------------------------------------------
# Unit test for the ContextVar override semantics (no HTTP layer).
# ---------------------------------------------------------------------------


def test_resolve_agent_backend_reads_coder_backend_context():
    """Sanity: the resolver honours ContextVar before settings.

    This pins the primitive stream_chat writes to.
    """
    token = coder_backend_context.set(AgentBackend.SDK)
    try:
        assert resolve_agent_backend("coder") == AgentBackend.SDK
    finally:
        coder_backend_context.reset(token)
    assert coder_backend_context.get() is None


# ---------------------------------------------------------------------------
# Integration tests against the real FastAPI route.
# ---------------------------------------------------------------------------


def _consume_stream(resp) -> list[dict]:
    """Parse an SSE streaming response into a list of decoded events."""
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


def test_stream_chat_sdk_override_is_set_during_request(monkeypatch, _patch_graph_and_checkpointer):
    """coder_backend='sdk' on the request body → graph sees SDK via the resolver."""
    from src.config.settings import settings

    # Settings default is LangChain; per-request override MUST win.
    monkeypatch.setattr(settings, "coder_backend", "langchain")

    observed: list[str] = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "run print(1+1)", "coder_backend": "sdk"},
    ) as resp:
        _consume_stream(resp)

    assert observed, "expected the fake graph to observe at least one resolve call"
    assert "sdk" in observed, f"expected 'sdk' in observed backends; got {observed!r}"
    # ContextVar must be reset after the stream finishes.
    assert coder_backend_context.get() is None


def test_stream_chat_langchain_override_beats_settings_sdk_default(
    monkeypatch, _patch_graph_and_checkpointer
):
    """coder_backend='langchain' wins even when settings.coder_backend='sdk'."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "sdk")

    observed: list[str] = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "hello", "coder_backend": "langchain"},
    ) as resp:
        _consume_stream(resp)

    assert observed
    assert all(b == "langchain" for b in observed), (
        f"per-request override must win over settings; got {observed!r}"
    )
    assert coder_backend_context.get() is None


def test_stream_chat_no_override_falls_back_to_settings(monkeypatch, _patch_graph_and_checkpointer):
    """Missing coder_backend → resolver reads settings."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")

    observed: list[str] = _patch_graph_and_checkpointer
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "hello"},
    ) as resp:
        _consume_stream(resp)

    assert observed
    assert all(b == "langchain" for b in observed), (
        f"fallback to settings.coder_backend='langchain' expected; got {observed!r}"
    )
    # Never set → never reset needed → still None.
    assert coder_backend_context.get() is None


def test_stream_chat_invalid_coder_backend_rejected_by_pydantic():
    """A bogus string is rejected at the request boundary with 422."""
    client = TestClient(app)
    resp = client.post(
        "/chat/stream",
        json={"message": "hello", "coder_backend": "anthropic"},
    )
    assert resp.status_code == 422


def test_stream_chat_override_does_not_leak_across_requests(
    monkeypatch, _patch_graph_and_checkpointer
):
    """Two sequential requests with different overrides stay isolated."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")

    observed: list[str] = _patch_graph_and_checkpointer
    client = TestClient(app)

    # First request: SDK override
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "first", "coder_backend": "sdk"},
    ) as resp:
        _consume_stream(resp)

    first_observations = list(observed)
    observed.clear()

    # Second request: no override — MUST fall back to settings (langchain).
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "second"},
    ) as resp:
        _consume_stream(resp)

    second_observations = list(observed)

    assert "sdk" in first_observations
    assert second_observations and all(b == "langchain" for b in second_observations), (
        f"second request leaked SDK from first; got {second_observations!r}"
    )
    assert coder_backend_context.get() is None


@pytest.mark.asyncio
async def test_stream_chat_override_resets_when_generator_raises(monkeypatch):
    """Even if the generator raises mid-stream, the ContextVar must reset.

    We drive the generator directly (not through TestClient) so we can control
    when the exception fires and assert the finally block ran.
    """
    from contextlib import asynccontextmanager

    from src.api.routes import chat as chat_mod
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "memory_extraction_enabled", False)

    class _ExplosiveAgent:
        async def astream_events(self, *a, **kw):
            raise RuntimeError("graph boom")
            if False:
                yield {}

        async def aget_state(self, *a, **kw):
            class _S:
                values: dict = {"messages": []}

            return _S()

    class _ExplosiveBuilder:
        def compile(self, checkpointer=None):
            return _ExplosiveAgent()

    monkeypatch.setattr(chat_mod, "graph_builder", _ExplosiveBuilder())

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

    # Drive the endpoint through the TestClient; the exception is caught
    # inside the generator and turned into an "error" SSE event, so the HTTP
    # response still returns 200. What we care about is the finally block.
    assert coder_backend_context.get() is None
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "go", "coder_backend": "sdk"},
    ) as resp:
        for _ in resp.iter_lines():
            pass
    assert coder_backend_context.get() is None, (
        "ContextVar leaked after an exception inside the generator"
    )


@pytest.mark.asyncio
async def test_concurrent_streams_preserve_backend_isolation(
    monkeypatch, _patch_graph_and_checkpointer
):
    """Two concurrent streams with different coder_backend must not cross-talk.

    Regression for the Phase 1 Codex finding applied to the HTTP path: if the
    override were stored on shared module state instead of a ContextVar, two
    streams scheduled on the same task-tree could see each other's values.
    """
    from httpx import ASGITransport, AsyncClient

    observed: list[str] = _patch_graph_and_checkpointer

    async def _one(coder_backend: str) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            async with ac.stream(
                "POST",
                "/chat/stream",
                json={"message": "go", "coder_backend": coder_backend},
            ) as resp:
                async for _ in resp.aiter_lines():
                    pass

    # Fire several concurrent pairs to give scheduling variation a chance.
    for _ in range(3):
        observed.clear()
        await asyncio.gather(_one("sdk"), _one("langchain"))
        # At least one of each must have been seen by the resolver.
        assert "sdk" in observed and "langchain" in observed, (
            f"expected both backends to be observed; got {observed!r}"
        )

    assert coder_backend_context.get() is None
