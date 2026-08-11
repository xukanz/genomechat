"""Unit tests for observability/mongodb_exporter.py."""

from datetime import datetime
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from src.service.observability import mongodb_exporter as exp_mod


def test_disabled_exporter_returns_success_without_db_call(monkeypatch):
    from opentelemetry.sdk.trace.export import SpanExportResult

    monkeypatch.setattr(exp_mod.settings, "trace_storage_enabled", False)
    exporter = exp_mod.MongoDBSpanExporter()
    # Calling export on a disabled exporter should not attempt DB operations
    result = exporter.export([])
    assert result == SpanExportResult.SUCCESS


def test_normalize_attrs_handles_tuples_and_dicts():
    raw = {"seq": (1, 2, 3), "nested": {"k": "v"}, "n": 7, "ok": True, "none": None}
    out = exp_mod._normalize_attrs(raw)
    assert out["seq"] == [1, 2, 3]
    assert out["nested"] == {"k": "v"}
    assert out["n"] == 7
    assert out["ok"] is True
    assert out["none"] is None


def test_to_document_contains_minimum_commitment_fields(mongomock_client, monkeypatch):
    # Point the exporter at our mongomock client
    monkeypatch.setattr(exp_mod.settings, "trace_storage_enabled", True)
    monkeypatch.setattr(exp_mod.settings, "mongodb_db_name", "test_db")
    with patch.object(exp_mod, "get_mongodb_client", return_value=mongomock_client):
        exporter = exp_mod.MongoDBSpanExporter(collection_name="traces_test")

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("unit-test")

        with tracer.start_as_current_span("agent.node.coder") as span:
            span.set_attribute("agent.name", "coder")
            span.set_attribute("agent.thread_id", "u1:c1")
            span.set_attribute("active_skills", [])

    collection = mongomock_client["test_db"]["traces_test"]
    docs = list(collection.find())
    assert len(docs) == 1
    doc = docs[0]
    assert doc["name"] == "agent.node.coder"
    assert doc["attributes"]["agent.name"] == "coder"
    assert doc["attributes"]["agent.thread_id"] == "u1:c1"
    assert doc["active_skills"] == []
    assert isinstance(doc["start_time"], datetime)
    assert doc["schema_version"] == "1"


def test_exporter_handles_init_failure_gracefully(monkeypatch):
    """If MongoDB init raises, exporter disables itself instead of crashing."""
    monkeypatch.setattr(exp_mod.settings, "trace_storage_enabled", True)

    def boom():
        raise RuntimeError("mongo down")

    monkeypatch.setattr(exp_mod, "get_mongodb_client", boom)
    exporter = exp_mod.MongoDBSpanExporter()
    assert exporter._enabled is False
    assert exporter._collection is None


# Ensure test leaves global tracer provider in a clean state
def teardown_function(_):
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
