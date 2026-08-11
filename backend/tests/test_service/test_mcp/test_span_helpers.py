"""Tests for traced_mcp_tool span emission."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest


def _assert_span(span, expected_name: str, expected_success: bool):
    assert span.name == expected_name, f"expected span name {expected_name}, got {span.name}"
    attrs = dict(span.attributes)
    assert attrs.get("tool.name") == expected_name.removeprefix("agent.tool.")
    assert "tool.args_hash" in attrs
    # args_hash is 16 hex chars (sha256 prefix)
    assert len(attrs["tool.args_hash"]) == 16
    assert all(c in "0123456789abcdef" for c in attrs["tool.args_hash"])
    assert attrs.get("tool.success") is expected_success
    assert "agent.thread_id" in attrs  # always present, even if ""


@pytest.mark.asyncio
async def test_traced_mcp_tool_success_path(in_memory_span_exporter):
    from src.service.mcp._span_helpers import traced_mcp_tool

    @traced_mcp_tool("fake_tool")
    async def fake_tool(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "ok"}], "is_error": False}

    result = await fake_tool({"foo": "bar"})

    assert result["is_error"] is False
    spans = in_memory_span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_span(spans[0], "agent.tool.fake_tool", expected_success=True)


@pytest.mark.asyncio
async def test_traced_mcp_tool_is_error_result(in_memory_span_exporter):
    from opentelemetry.trace import StatusCode

    from src.service.mcp._span_helpers import traced_mcp_tool

    @traced_mcp_tool("broken_tool")
    async def broken_tool(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "nope"}], "is_error": True}

    result = await broken_tool({})

    assert result["is_error"] is True
    spans = in_memory_span_exporter.get_finished_spans()
    assert len(spans) == 1
    _assert_span(spans[0], "agent.tool.broken_tool", expected_success=False)
    assert spans[0].status.status_code == StatusCode.ERROR


@pytest.mark.asyncio
async def test_traced_mcp_tool_raises_records_exception(in_memory_span_exporter):
    from opentelemetry.trace import StatusCode

    from src.service.mcp._span_helpers import traced_mcp_tool

    @traced_mcp_tool("exploder")
    async def exploder(args: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await exploder({"x": 1})

    spans = in_memory_span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "agent.tool.exploder"
    assert dict(spans[0].attributes).get("tool.success") is False
    assert spans[0].status.status_code == StatusCode.ERROR
    # record_exception stores it as an event
    assert any("exception" in ev.name for ev in spans[0].events)


@pytest.mark.asyncio
async def test_traced_mcp_tool_args_hash_is_deterministic(in_memory_span_exporter):
    from src.service.mcp._span_helpers import traced_mcp_tool

    @traced_mcp_tool("t")
    async def t(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "x"}], "is_error": False}

    args = {"a": 1, "b": "two", "c": [1, 2, 3]}
    expected = hashlib.sha256(json.dumps(args, default=str, sort_keys=True).encode()).hexdigest()[:16]

    await t(args)
    spans = in_memory_span_exporter.get_finished_spans()
    assert dict(spans[0].attributes)["tool.args_hash"] == expected


@pytest.mark.asyncio
async def test_traced_mcp_tool_reads_thread_id_context(in_memory_span_exporter):
    from src.service.mcp._span_helpers import traced_mcp_tool
    from src.utils.context import thread_id_context

    @traced_mcp_tool("t")
    async def t(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": "x"}], "is_error": False}

    token = thread_id_context.set("user-42:conv-xyz")
    try:
        await t({})
    finally:
        thread_id_context.reset(token)

    spans = in_memory_span_exporter.get_finished_spans()
    assert dict(spans[0].attributes)["agent.thread_id"] == "user-42:conv-xyz"
