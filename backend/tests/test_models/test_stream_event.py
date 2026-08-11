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
