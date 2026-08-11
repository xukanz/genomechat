"""Tests for StreamEvent model token_usage field."""

from src.models.api import StreamEvent


def test_stream_event_with_token_usage():
    """Verify StreamEvent accepts token_usage field."""
    event = StreamEvent(
        type="end",
        content="",
        token_usage={"estimated_tokens": 5000, "max_tokens": 140000, "usage_pct": 3.6},
    )
    assert event.token_usage is not None
    assert event.token_usage["estimated_tokens"] == 5000
    assert event.token_usage["max_tokens"] == 140000
    assert event.token_usage["usage_pct"] == 3.6


def test_stream_event_without_token_usage():
    """Verify StreamEvent works without token_usage (backward compatible)."""
    event = StreamEvent(type="end", content="")
    assert event.token_usage is None


def test_stream_event_token_usage_serialization():
    """Verify token_usage serializes correctly in JSON."""
    event = StreamEvent(
        type="end",
        content="",
        token_usage={"estimated_tokens": 50000, "max_tokens": 140000, "usage_pct": 35.7},
    )
    json_str = event.model_dump_json()
    assert '"estimated_tokens": 50000' in json_str or '"estimated_tokens":50000' in json_str
    assert '"usage_pct"' in json_str


# ---------------------------------------------------------------------------
# agent_backend — Phase 1 frontend-badge support
# ---------------------------------------------------------------------------


def test_stream_event_agent_backend_sdk():
    """agent_backend='sdk' on a worker agent_start event round-trips cleanly."""
    event = StreamEvent(
        type="agent_start",
        content="Coder started",
        agent_name="Coder",
        agent_backend="sdk",
    )
    assert event.agent_backend == "sdk"
    json_str = event.model_dump_json()
    assert '"agent_backend":"sdk"' in json_str or '"agent_backend": "sdk"' in json_str


def test_stream_event_agent_backend_default_none():
    """agent_backend defaults to None when not provided (backward compatible)."""
    event = StreamEvent(
        type="agent_start",
        content="Coordinator started",
        agent_name="Coordinator",
    )
    assert event.agent_backend is None


def test_stream_event_agent_backend_on_agent_end():
    """agent_end events may also carry agent_backend to label the completed turn."""
    event = StreamEvent(
        type="agent_end",
        content="done",
        agent_name="Coder",
        agent_backend="langchain",
    )
    assert event.agent_backend == "langchain"
