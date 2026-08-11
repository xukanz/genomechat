"""Integration test — stream_chat emits a root ``agent.request`` trace span.

Phase 2 Workstream C groundwork: the root span carries Langfuse-native
attributes (``langfuse.trace.name`` / ``langfuse.session.id`` / ``user.id`` /
``langfuse.tags``) so every trace in Langfuse gets a conversation-level
grouping + filter metadata.

This test verifies the span is actually produced and the attributes land
where they should. It does NOT verify Langfuse's UI rendering — that's
an operator concern covered in the operator guide §7.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import app


class _NoopAgent:
    async def astream_events(self, *a: Any, **kw: Any):
        if False:  # pragma: no cover — make this a generator
            yield {}
        return

    async def aget_state(self, config: dict | None = None):
        class _S:
            values: dict = {"messages": []}

        return _S()


class _NoopBuilder:
    def compile(self, checkpointer=None):
        return _NoopAgent()


@pytest.fixture
def _patch_graph_and_checkpointer(monkeypatch):
    from src.api.routes import chat as chat_mod

    monkeypatch.setattr(chat_mod, "graph_builder", _NoopBuilder())

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

    from src.config.settings import settings

    monkeypatch.setattr(settings, "memory_extraction_enabled", False)
    monkeypatch.setattr(settings, "otel_enabled", True)


@pytest.fixture
def _patch_chat_tracer(in_memory_span_exporter, monkeypatch):
    """Swap src.api.routes.chat.tracer onto the test's TracerProvider so the
    root ``agent.request`` span lands in the InMemorySpanExporter.

    The repo-wide ``in_memory_span_exporter`` fixture already swaps the
    decorator + callback tracer handles; we extend it here for the chat
    route's root-span emission.
    """
    from opentelemetry import trace

    import src.api.routes.chat as chat_mod

    shared_tracer = trace._TRACER_PROVIDER.get_tracer("genomechat.platform")  # type: ignore[attr-defined]
    monkeypatch.setattr(chat_mod, "tracer", shared_tracer)


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


def _find_request_span(exporter):
    return next(
        (s for s in exporter.get_finished_spans() if s.name == "agent.request"),
        None,
    )


def test_stream_chat_emits_root_request_span_with_session_and_tags(
    in_memory_span_exporter, _patch_graph_and_checkpointer, _patch_chat_tracer
):
    """Happy path: agent.request span emitted with session_id + name + tags."""
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "message": "Top 10 V genes?",
            "thread_id": "test-conv-1",
            "research_mode": "standard",
            "code_language": "python",
        },
    ) as resp:
        _consume_stream(resp)

    span = _find_request_span(in_memory_span_exporter)
    assert span is not None, "agent.request span must be emitted by stream_chat"

    attrs = dict(span.attributes)
    # Conversation grouping — anonymous user so thread_id carries the anonymous: prefix.
    assert attrs["langfuse.session.id"] == "anonymous:test-conv-1"
    # Trace name is the user message text.
    assert "Top 10 V genes" in attrs["langfuse.trace.name"]
    # Tags surface the request-shape knobs.
    tags = list(attrs["langfuse.tags"])
    assert "research_mode:standard" in tags
    assert "code_language:python" in tags
    # Anonymous: user.id omitted, anonymous tag present.
    assert "user.id" not in attrs
    assert "anonymous" in tags


def test_stream_chat_root_span_includes_backend_override_tags(
    in_memory_span_exporter, _patch_graph_and_checkpointer, _patch_chat_tracer
):
    """When a request sets coder_backend / orchestrator_backend overrides,
    each surfaces as a separate tag so Langfuse users can filter A/B runs."""
    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "message": "hi",
            "thread_id": "t-1",
            "coder_backend": "sdk",
            "orchestrator_backend": "langchain",
        },
    ) as resp:
        _consume_stream(resp)

    span = _find_request_span(in_memory_span_exporter)
    assert span is not None
    tags = set(span.attributes.get("langfuse.tags") or [])
    assert "coder_backend:sdk" in tags
    assert "orchestrator_backend:langchain" in tags


def test_stream_chat_root_span_is_noop_when_otel_disabled(
    in_memory_span_exporter, _patch_graph_and_checkpointer, _patch_chat_tracer, monkeypatch
):
    """When otel_enabled=False, the span still fires (the tracer itself is
    not gated by settings) but the Langfuse attribute set is empty — so no
    PII-adjacent strings land on spans operators didn't consent to capture.
    """
    from src.config.settings import settings

    monkeypatch.setattr(settings, "otel_enabled", False)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/chat/stream",
        json={"message": "hi", "thread_id": "t-disabled"},
    ) as resp:
        _consume_stream(resp)

    span = _find_request_span(in_memory_span_exporter)
    assert span is not None
    # Span exists but carries no Langfuse enrichment.
    assert "langfuse.session.id" not in span.attributes
    assert "langfuse.trace.name" not in span.attributes
    assert "langfuse.tags" not in span.attributes
