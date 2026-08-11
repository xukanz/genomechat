"""Unit tests for observability/decorators.py."""

import pytest

from src.service.observability.decorators import trace_node, trace_tool


@pytest.mark.asyncio
async def test_async_node_emits_span_with_minimum_attributes(in_memory_span_exporter):
    @trace_node("coder")
    async def my_node(state):
        return "ok"

    await my_node({"thread_id": "t1", "database_id": "clinvar", "research_mode": "quick"})
    spans = in_memory_span_exporter.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "agent.node.coder"
    assert s.attributes["agent.name"] == "coder"
    assert s.attributes["agent.thread_id"] == "t1"
    assert s.attributes["agent.database_id"] == "clinvar"
    assert s.attributes["agent.research_mode"] == "quick"
    assert list(s.attributes["active_skills"]) == []


def test_sync_node_is_supported(in_memory_span_exporter):
    @trace_node("coordinator")
    def coord(state):
        return "done"

    coord({"thread_id": "x"})
    spans = in_memory_span_exporter.get_finished_spans()
    assert spans[0].name == "agent.node.coordinator"


@pytest.mark.asyncio
async def test_node_records_langgraph_command_event(in_memory_span_exporter):
    class FakeCommand:
        goto = "orchestrator"

    @trace_node("coder")
    async def worker(state):
        return FakeCommand()

    await worker({})
    spans = in_memory_span_exporter.get_finished_spans()
    events = spans[0].events
    assert any(e.name == "langgraph.command" for e in events)
    cmd_event = next(e for e in events if e.name == "langgraph.command")
    assert cmd_event.attributes["goto"] == "orchestrator"


@pytest.mark.asyncio
async def test_node_records_exception_status(in_memory_span_exporter):
    @trace_node("coder")
    async def bad(state):
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await bad({})
    span = in_memory_span_exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"


@pytest.mark.asyncio
async def test_node_preserves_error_status_set_by_caller(in_memory_span_exporter):
    """SDK paths catch exceptions and stamp ERROR on the current span before
    returning ""; trace_node must not overwrite that with OK on normal return.
    """
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    @trace_node("orchestrator")
    async def soft_failure(state):
        # Node catches its own failure and returns "" instead of raising.
        trace.get_current_span().set_status(Status(StatusCode.ERROR, "worker.timeout"))
        return ""

    result = await soft_failure({})
    assert result == ""
    span = in_memory_span_exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
    assert span.status.description == "worker.timeout"


def test_sync_node_preserves_error_status_set_by_caller(in_memory_span_exporter):
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    @trace_node("coordinator")
    def soft_failure(state):
        trace.get_current_span().set_status(Status(StatusCode.ERROR, "boom"))
        return "fallback"

    soft_failure({})
    span = in_memory_span_exporter.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"


@pytest.mark.asyncio
async def test_trace_tool_wraps_async_coroutine(in_memory_span_exporter):
    from langchain_core.tools import tool

    @trace_tool
    @tool
    async def sample_tool(value: str) -> str:
        """A sample async tool."""
        return f"got {value}"

    result = await sample_tool.ainvoke({"value": "hello"})
    assert result == "got hello"
    spans = in_memory_span_exporter.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "agent.tool.sample_tool"
    assert s.attributes["tool.name"] == "sample_tool"
    # args_hash present, and never equal to raw value
    assert "tool.args_hash" in s.attributes
    assert "hello" not in s.attributes["tool.args_hash"]
    assert s.attributes["tool.success"] is True


def test_trace_tool_wraps_sync_func(in_memory_span_exporter):
    from langchain_core.tools import tool

    @trace_tool
    @tool
    def sync_sample(value: str) -> str:
        """A sync tool."""
        return f"sync {value}"

    result = sync_sample.invoke({"value": "hi"})
    assert result == "sync hi"
    spans = in_memory_span_exporter.get_finished_spans()
    assert spans[0].name == "agent.tool.sync_sample"
    assert spans[0].attributes["tool.success"] is True


@pytest.mark.asyncio
async def test_trace_tool_records_failure(in_memory_span_exporter):
    from langchain_core.tools import tool

    @trace_tool
    @tool
    async def failing_tool(value: str) -> str:
        """Raises."""
        raise RuntimeError("boom")

    with pytest.raises(Exception):
        await failing_tool.ainvoke({"value": "x"})
    span = in_memory_span_exporter.get_finished_spans()[0]
    assert span.attributes["tool.success"] is False
    assert span.status.status_code.name == "ERROR"


@pytest.mark.asyncio
async def test_trace_tool_propagates_thread_id_from_contextvar(in_memory_span_exporter):
    """Regression for Codex Finding 2 — tool spans must carry `agent.thread_id`.

    Before the fix, `MongoDBSpanExporter` couldn't hoist `tenant_id` for tool
    docs, so `/internal/traces` returned only node spans per turn.
    """
    from langchain_core.tools import tool

    from src.utils.context import thread_id_context

    @trace_tool
    @tool
    async def ctx_tool(value: str) -> str:
        """Async tool reading from thread_id_context."""
        return f"ok {value}"

    token = thread_id_context.set("alice:conv-xyz")
    try:
        await ctx_tool.ainvoke({"value": "hi"})
    finally:
        thread_id_context.reset(token)

    span = in_memory_span_exporter.get_finished_spans()[0]
    assert span.attributes["agent.thread_id"] == "alice:conv-xyz"


def test_trace_tool_defaults_thread_id_when_context_unset(in_memory_span_exporter):
    """When no ContextVar is set, the attribute is still present as empty string."""
    from langchain_core.tools import tool

    @trace_tool
    @tool
    def plain_tool(value: str) -> str:
        """Sync tool."""
        return value

    plain_tool.invoke({"value": "x"})
    span = in_memory_span_exporter.get_finished_spans()[0]
    # Present but empty — keeps the span shape predictable for downstream consumers
    assert span.attributes.get("agent.thread_id", None) == ""
