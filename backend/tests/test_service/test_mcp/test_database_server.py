"""Tests for the in-process database MCP server (Phase 2 Workstream B)."""

from __future__ import annotations

from unittest.mock import patch

import pytest


# The database tools are SYNC (no .coroutine), so the shim wraps them in
# asyncio.to_thread. We patch the underlying `.func` handle rather than
# `asyncio.to_thread` itself so the assertions stay readable and we also
# exercise the to_thread wiring along the way.


@pytest.mark.asyncio
async def test_execute_sql_query_mcp_success(in_memory_span_exporter):
    from src.service.mcp.database_server import execute_sql_query_mcp

    with patch(
        "src.service.mcp.database_server._execute_sql_query_func",
        return_value="Query executed successfully. Results (3 rows):\n\ncol\n1\n2\n3",
    ) as mock_exec:
        result = await execute_sql_query_mcp.handler({"query": "SELECT col FROM t"})

    assert result["is_error"] is False
    assert "3 rows" in result["content"][0]["text"]
    mock_exec.assert_called_once_with("SELECT col FROM t")

    spans = in_memory_span_exporter.get_finished_spans()
    assert any(s.name == "agent.tool.execute_sql_query" for s in spans)


@pytest.mark.asyncio
async def test_execute_sql_query_mcp_empty_query_rejected():
    """Pydantic would normally catch this, but the shim also guards."""
    from src.service.mcp.database_server import execute_sql_query_mcp

    result = await execute_sql_query_mcp.handler({"query": "   "})
    assert result["is_error"] is True
    assert "non-empty 'query'" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_execute_sql_query_mcp_error_string_maps_to_is_error(in_memory_span_exporter):
    """The LangChain tool's 'Error executing ...' return flips is_error=True."""
    from opentelemetry.trace import StatusCode

    from src.service.mcp.database_server import execute_sql_query_mcp

    with patch(
        "src.service.mcp.database_server._execute_sql_query_func",
        return_value="Error executing SQL query: syntax near FROM",
    ):
        result = await execute_sql_query_mcp.handler({"query": "SELECT bogus"})

    assert result["is_error"] is True
    spans = in_memory_span_exporter.get_finished_spans()
    matching = [s for s in spans if s.name == "agent.tool.execute_sql_query"]
    assert matching
    assert matching[0].status.status_code == StatusCode.ERROR


@pytest.mark.asyncio
async def test_execute_sql_query_mcp_exception_mapped_to_error():
    """An exception in the sync tool must surface as is_error=True — not propagate."""
    from src.service.mcp.database_server import execute_sql_query_mcp

    def _boom(query: str) -> str:
        raise RuntimeError("db pool exhausted")

    with patch("src.service.mcp.database_server._execute_sql_query_func", new=_boom):
        result = await execute_sql_query_mcp.handler({"query": "SELECT 1"})

    assert result["is_error"] is True
    assert "db pool exhausted" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_execute_sql_query_and_save_mcp_success():
    from src.service.mcp.database_server import execute_sql_query_and_save_mcp

    with patch(
        "src.service.mcp.database_server._execute_sql_query_and_save_func",
        return_value="Query executed successfully and results saved to storage.",
    ) as mock_exec:
        result = await execute_sql_query_and_save_mcp.handler(
            {"query": "SELECT * FROM t", "description": "weekly report"}
        )

    assert result["is_error"] is False
    mock_exec.assert_called_once_with("SELECT * FROM t", "weekly report")


@pytest.mark.asyncio
async def test_execute_sql_query_and_save_mcp_empty_description_ok():
    """Description is optional — missing value should pass through as empty string."""
    from src.service.mcp.database_server import execute_sql_query_and_save_mcp

    with patch(
        "src.service.mcp.database_server._execute_sql_query_and_save_func",
        return_value="ok",
    ) as mock_exec:
        await execute_sql_query_and_save_mcp.handler({"query": "SELECT 1"})

    mock_exec.assert_called_once_with("SELECT 1", "")


@pytest.mark.asyncio
async def test_get_database_schema_mcp_success(in_memory_span_exporter):
    from src.service.mcp.database_server import get_database_schema_mcp

    with patch(
        "src.service.mcp.database_server._get_database_schema_func",
        return_value="Tables:\n- foo(a, b, c)\n- bar(x, y)",
    ):
        result = await get_database_schema_mcp.handler({})

    assert result["is_error"] is False
    assert "Tables" in result["content"][0]["text"]
    spans = in_memory_span_exporter.get_finished_spans()
    assert any(s.name == "agent.tool.get_database_schema" for s in spans)


@pytest.mark.asyncio
async def test_get_database_schema_mcp_error_string():
    from src.service.mcp.database_server import get_database_schema_mcp

    with patch(
        "src.service.mcp.database_server._get_database_schema_func",
        return_value="Error retrieving database schema: connection refused",
    ):
        result = await get_database_schema_mcp.handler({})
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_get_random_subsamples_mcp_success():
    from src.service.mcp.database_server import get_random_subsamples_mcp

    with patch(
        "src.service.mcp.database_server._get_random_subsamples_func",
        return_value="Sampled 5 rows from 2 tables.",
    ) as mock_sample:
        result = await get_random_subsamples_mcp.handler(
            {
                "tables": [{"table": "foo", "columns": ["a", "b"]}],
                "sample_size": 5,
            }
        )

    assert result["is_error"] is False
    mock_sample.assert_called_once_with(
        [{"table": "foo", "columns": ["a", "b"]}],
        5,
    )


@pytest.mark.asyncio
async def test_get_random_subsamples_mcp_empty_tables_rejected():
    from src.service.mcp.database_server import get_random_subsamples_mcp

    result = await get_random_subsamples_mcp.handler({"tables": []})
    assert result["is_error"] is True
    assert "non-empty 'tables'" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_get_random_subsamples_mcp_missing_tables_rejected():
    from src.service.mcp.database_server import get_random_subsamples_mcp

    result = await get_random_subsamples_mcp.handler({"sample_size": 10})
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_get_random_subsamples_mcp_default_sample_size():
    """sample_size omitted → default to 5 (matches the tool's signature)."""
    from src.service.mcp.database_server import get_random_subsamples_mcp

    with patch(
        "src.service.mcp.database_server._get_random_subsamples_func",
        return_value="ok",
    ) as mock_sample:
        await get_random_subsamples_mcp.handler({"tables": [{"table": "t"}]})

    mock_sample.assert_called_once_with([{"table": "t"}], 5)


def test_build_database_server_registers_all_four_tools():
    from src.service.mcp.database_server import build_database_server

    server = build_database_server()
    # The server object's shape depends on the SDK internals; we just sanity-
    # check that it builds without error and the module-level MCP tools are
    # the same four we expect to expose.
    assert server is not None

    # The ORCHESTRATOR_MCP_TOOL_NAMES tuple is the authoritative surface —
    # another test pins parity between that tuple and the registered tools.
    from src.service.mcp import ORCHESTRATOR_MCP_TOOL_NAMES

    assert "mcp__database__execute_sql_query" in ORCHESTRATOR_MCP_TOOL_NAMES
    assert "mcp__database__execute_sql_query_and_save" in ORCHESTRATOR_MCP_TOOL_NAMES
    assert "mcp__database__get_database_schema" in ORCHESTRATOR_MCP_TOOL_NAMES
    assert "mcp__database__get_random_subsamples" in ORCHESTRATOR_MCP_TOOL_NAMES
