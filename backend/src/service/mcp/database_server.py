"""In-process MCP server exposing database (SQL) operations to the SDK.

Wraps the four orchestrator-path database tools from ``src.tools.database``:
``execute_sql_query``, ``execute_sql_query_and_save``, ``get_database_schema``,
``get_random_subsamples``.

The underlying tools are **sync** LangChain ``@tool`` functions (they call
DuckDB / SQLite synchronously and format DataFrames). That means the
``StructuredTool.coroutine`` attribute is ``None`` — we can't await it like
we do in the s3 / file_ops shims. Instead we delegate to
``StructuredTool.func`` via ``asyncio.to_thread`` so the SDK's async event
loop doesn't block while DuckDB runs.

ContextVar propagation: the tools read ``database_id_context`` internally.
Because the MCP server runs in the same Python process as the backend, that
ContextVar propagates into ``asyncio.to_thread``'s wrapped callable.

Security: SQL queries frequently contain tenant data. We MUST NOT log raw
queries here. ``traced_mcp_tool`` hashes args and never records their raw
values — double-check if you extend this module.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from src.service.mcp._result_helpers import looks_like_tool_error
from src.service.mcp._span_helpers import traced_mcp_tool
from src.tools.database import (
    execute_sql_query as _execute_sql_query_tool,
    execute_sql_query_and_save as _execute_sql_query_and_save_tool,
    get_database_schema as _get_database_schema_tool,
    get_random_subsamples as _get_random_subsamples_tool,
)

logger = logging.getLogger(__name__)

# The LangChain sync tools expose their raw callable via `.func`. `.coroutine`
# is None for sync @tool functions.
_execute_sql_query_func = _execute_sql_query_tool.func
_execute_sql_query_and_save_func = _execute_sql_query_and_save_tool.func
_get_database_schema_func = _get_database_schema_tool.func
_get_random_subsamples_func = _get_random_subsamples_tool.func


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


@tool(
    "execute_sql_query",
    (
        "Execute a SQL query against the currently active database and return "
        "a formatted preview (first 100 rows). Use for simple analytical "
        "queries where the full result set is not needed downstream. If you "
        "will need the complete result for further code/analysis, use "
        "execute_sql_query_and_save instead."
    ),
    {
        "query": str,
    },
)
@traced_mcp_tool("execute_sql_query")
async def execute_sql_query_mcp(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query") or ""
    if not query.strip():
        return _err("execute_sql_query requires a non-empty 'query' argument.")
    try:
        text = await asyncio.to_thread(_execute_sql_query_func, query)
    except Exception as e:  # noqa: BLE001
        logger.exception("execute_sql_query (MCP) raised")
        return _err(f"Error executing SQL query: {e}")
    # The sync tool's error grammar: "Error executing SQL query: ..." which
    # matches the "Error: ..." / "Error executing ..." family. Reuse the
    # strict prefix matcher; also fall back to the literal prefix the tool
    # uses so we don't misclassify a legitimate empty-result string.
    if looks_like_tool_error(text) or text.startswith("Error executing "):
        return _err(text)
    return _ok(text)


@tool(
    "execute_sql_query_and_save",
    (
        "Execute a SQL query, save the full result set to storage (S3 if "
        "configured, else local filesystem), and return a summary + preview + "
        "file pointer. Use when downstream analysis (e.g. the coder) will need "
        "the complete dataset. Optional description is used in the filename."
    ),
    {
        "query": str,
        "description": str,
    },
)
@traced_mcp_tool("execute_sql_query_and_save")
async def execute_sql_query_and_save_mcp(args: dict[str, Any]) -> dict[str, Any]:
    query = args.get("query") or ""
    if not query.strip():
        return _err("execute_sql_query_and_save requires a non-empty 'query' argument.")
    description = args.get("description") or ""
    try:
        text = await asyncio.to_thread(_execute_sql_query_and_save_func, query, description)
    except Exception as e:  # noqa: BLE001
        logger.exception("execute_sql_query_and_save (MCP) raised")
        return _err(f"Error executing SQL query: {e}")
    if looks_like_tool_error(text) or text.startswith("Error executing "):
        return _err(text)
    return _ok(text)


@tool(
    "get_database_schema",
    (
        "Return the schema (tables, columns, types) of the currently active "
        "database. Always call this before writing non-trivial SQL so your "
        "query references real columns."
    ),
    {},
)
@traced_mcp_tool("get_database_schema")
async def get_database_schema_mcp(args: dict[str, Any]) -> dict[str, Any]:
    try:
        text = await asyncio.to_thread(_get_database_schema_func)
    except Exception as e:  # noqa: BLE001
        logger.exception("get_database_schema (MCP) raised")
        return _err(f"Error retrieving database schema: {e}")
    if looks_like_tool_error(text) or text.startswith("Error retrieving "):
        return _err(text)
    return _ok(text)


@tool(
    "get_random_subsamples",
    (
        "Fetch N random rows from each of the specified tables (default N=5) "
        "to let you inspect actual values before writing analytical queries. "
        "Pass a list of table entries, e.g. "
        '[{"table": "complex", "columns": ["antigen_epitope", "mhc_class"]}]. '
        "Columns is optional — omit it to sample all columns."
    ),
    {
        "tables": list,
        "sample_size": int,
    },
)
@traced_mcp_tool("get_random_subsamples")
async def get_random_subsamples_mcp(args: dict[str, Any]) -> dict[str, Any]:
    tables = args.get("tables")
    if not isinstance(tables, list) or not tables:
        return _err(
            "get_random_subsamples requires a non-empty 'tables' list "
            'of {"table": str, "columns"?: list[str]} entries.'
        )
    sample_size = args.get("sample_size") or 5
    try:
        text = await asyncio.to_thread(_get_random_subsamples_func, tables, sample_size)
    except Exception as e:  # noqa: BLE001
        logger.exception("get_random_subsamples (MCP) raised")
        return _err(f"Error sampling tables: {e}")
    if looks_like_tool_error(text):
        return _err(text)
    return _ok(text)


def build_database_server() -> Any:
    """Return the MCP server config object exposing all four database tools."""
    return create_sdk_mcp_server(
        name="database",
        version="1.0.0",
        tools=[
            execute_sql_query_mcp,
            execute_sql_query_and_save_mcp,
            get_database_schema_mcp,
            get_random_subsamples_mcp,
        ],
    )


__all__ = [
    "build_database_server",
    "execute_sql_query_mcp",
    "execute_sql_query_and_save_mcp",
    "get_database_schema_mcp",
    "get_random_subsamples_mcp",
]
