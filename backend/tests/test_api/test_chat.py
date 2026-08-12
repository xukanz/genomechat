"""Tests for chat endpoints."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from src.models.api import ChatRequest

client = TestClient(app)


@contextlib.contextmanager
def _mocked_agent(agent: MagicMock):
    """Patch out the per-request agent compilation and its MongoDB dependencies.

    The chat routes build their agent inside the request: they open a
    checkpointer, compile `graph_builder` against it, and separately touch
    `ConversationService` for conversation metadata. All three need stubbing
    for the endpoint to run without a live MongoDB or LLM.
    """

    @contextlib.asynccontextmanager
    async def fake_checkpointer():
        yield MagicMock()

    with (
        patch("src.api.routes.chat.create_checkpointer", fake_checkpointer),
        patch("src.api.routes.chat.graph_builder") as mock_builder,
        patch(
            "src.service.storage.conversation_service.ConversationService"
        ) as mock_conversation_service,
    ):
        mock_builder.compile.return_value = agent
        mock_conversation_service.return_value.get_conversation.return_value = None
        yield mock_builder


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_chat_endpoint():
    """The synchronous endpoint returns the agent's last message and a thread_id."""
    request = ChatRequest(message="Hello")
    mock_agent = MagicMock()
    mock_agent.ainvoke = AsyncMock(
        return_value={"messages": [MagicMock(content="Hello! How can I help you?")]}
    )

    with _mocked_agent(mock_agent):
        response = client.post("/chat", json=request.model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Hello! How can I help you?"
    assert data["thread_id"]
    mock_agent.ainvoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_chat_endpoint():
    """The streaming endpoint emits SSE frames, starting with a thinking event."""
    request = ChatRequest(message="Hello")

    async def mock_stream(*_args, **_kwargs):
        yield {
            "event": "on_chat_model_stream",
            "name": "coordinator",
            "data": {"chunk": MagicMock(content="Hello")},
        }

    mock_agent = MagicMock()
    mock_agent.astream_events = mock_stream

    with _mocked_agent(mock_agent):
        response = client.post("/chat/stream", json=request.model_dump())
        body = response.text

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type":"thinking"' in body.replace(" ", "")


def test_pilot_user_ids_set_parses_csv(monkeypatch):
    """Phase 0.5: the memory-extraction pilot gate parses comma-separated ids."""
    from src.api.routes import chat as chat_mod

    chat_mod._pilot_user_ids_set.cache_clear()
    monkeypatch.setattr(chat_mod.settings, "memory_pilot_user_ids", "alice, bob , charlie ")
    assert chat_mod._pilot_user_ids_set() == frozenset({"alice", "bob", "charlie"})


def test_pilot_user_ids_set_empty_returns_empty(monkeypatch):
    from src.api.routes import chat as chat_mod

    chat_mod._pilot_user_ids_set.cache_clear()
    monkeypatch.setattr(chat_mod.settings, "memory_pilot_user_ids", "")
    assert chat_mod._pilot_user_ids_set() == frozenset()


def test_pilot_user_ids_set_drops_empty_segments(monkeypatch):
    from src.api.routes import chat as chat_mod

    chat_mod._pilot_user_ids_set.cache_clear()
    monkeypatch.setattr(chat_mod.settings, "memory_pilot_user_ids", "alice,,bob,, ")
    assert chat_mod._pilot_user_ids_set() == frozenset({"alice", "bob"})
