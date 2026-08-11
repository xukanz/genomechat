"""Unit tests for observability/trace_schema.py."""

from datetime import datetime, timezone

import pytest

from src.service.observability.trace_schema import (
    LLMSpanAttrs,
    NodeSpanAttrs,
    SpanEvent,
    ToolSpanAttrs,
    TraceSpan,
)


def test_node_span_attrs_defaults_active_skills_to_empty_list():
    attrs = NodeSpanAttrs(**{"agent.name": "coder"})
    assert attrs.active_skills == []
    # optional fields default to empty string
    assert attrs.agent_thread_id == ""


def test_llm_span_attrs_requires_all_fields():
    with pytest.raises(Exception):
        LLMSpanAttrs(**{"gen_ai.system": "anthropic"})  # missing most fields


def test_tool_span_attrs_defaults_success_true():
    attrs = ToolSpanAttrs(**{"tool.name": "execute_code", "tool.args_hash": "abc"})
    assert attrs.tool_success is True


def test_trace_span_model_round_trips_and_reserves_active_skills():
    now = datetime.now(tz=timezone.utc)
    doc = {
        "trace_id": "0" * 32,
        "span_id": "1" * 16,
        "parent_span_id": None,
        "name": "agent.node.coder",
        "kind": "INTERNAL",
        "start_time": now,
        "end_time": now,
        "duration_ms": 0.0,
        "attributes": {"agent.name": "coder"},
        "events": [
            {"name": "langgraph.command", "timestamp": 0, "attributes": {"goto": "orchestrator"}}
        ],
        "resource": {"service.name": "genomechat-backend"},
    }
    span = TraceSpan(**doc)
    assert span.active_skills == []
    assert span.schema_version == "1"
    assert span.events[0].attributes["goto"] == "orchestrator"
    assert isinstance(span.events[0], SpanEvent)
