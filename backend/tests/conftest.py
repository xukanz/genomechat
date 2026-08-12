"""Pytest configuration and shared fixtures."""

from typing import Any, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest


def make_mongo_cursor(docs: list[dict[str, Any]]) -> MagicMock:
    """Build a MagicMock that behaves like a PyMongo cursor over `docs`.

    Services chain `find(...).sort(...).skip(...).limit(...)` before iterating,
    so every chaining method has to return the same object. A bare MagicMock
    returns a fresh child mock from `.sort()`, which iterates as empty and
    makes the assertions silently compare against zero rows.
    """
    cursor = MagicMock()
    cursor.__iter__ = MagicMock(side_effect=lambda: iter(docs))
    for method in ("sort", "skip", "limit"):
        getattr(cursor, method).return_value = cursor
    return cursor


@pytest.fixture
def mock_agent():
    """Mock agent for testing."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def sample_chat_request():
    """Sample chat request for testing."""
    from src.models.api import ChatRequest

    return ChatRequest(message="Hello, how are you?")


@pytest.fixture
def sample_thread_id():
    """Sample thread ID for testing."""
    return "test-thread-123"


@pytest.fixture
def mongomock_client():
    """In-memory MongoDB client suitable for exporter / access-log tests."""
    import mongomock

    return mongomock.MongoClient()


@pytest.fixture
def in_memory_span_exporter() -> Iterator:
    """OTel InMemorySpanExporter wired to a fresh TracerProvider for the test.

    Yields the exporter so the test can call `.get_finished_spans()`.
    Resets the global TracerProvider on teardown to keep tests isolated.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    original_provider = trace._TRACER_PROVIDER  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = provider  # type: ignore[attr-defined]
    # Swap both module-level tracer handles so decorator and callback spans
    # land in this exporter. Keep the same test-wide TracerProvider on all
    # three surfaces — anything else creates inconsistent tracing in tests.
    import src.service.observability.callbacks as cb_mod
    import src.service.observability.decorators as dec_mod

    shared_tracer = provider.get_tracer("genomechat.platform")
    original_dec_tracer = dec_mod.tracer
    original_cb_tracer = cb_mod.tracer
    dec_mod.tracer = shared_tracer
    cb_mod.tracer = shared_tracer
    try:
        yield exporter
    finally:
        dec_mod.tracer = original_dec_tracer
        cb_mod.tracer = original_cb_tracer
        trace._TRACER_PROVIDER = original_provider  # type: ignore[attr-defined]
