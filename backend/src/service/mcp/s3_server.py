"""In-process MCP server exposing S3 operations to the SDK.

Mirrors the semantics of ``src.tools.s3_operations.read_file_from_s3`` and
``list_s3_files``. We reach into the LangChain tool's ``.coroutine`` attribute
so the SDK path uses the IDENTICAL async callable the LangChain path does —
zero risk of behavioral drift between backends.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from src.service.mcp._result_helpers import looks_like_tool_error
from src.service.mcp._span_helpers import traced_mcp_tool
from src.tools.s3_operations import list_s3_files as _list_s3_files_tool
from src.tools.s3_operations import read_file_from_s3 as _read_file_from_s3_tool

logger = logging.getLogger(__name__)

# LangChain StructuredTool.coroutine is the raw async function underlying
# `.ainvoke({...})`. Reuse it so business logic (bucket validation, default
# bucket fallback, CSV truncation) stays a single implementation.
_read_file_coroutine = _read_file_from_s3_tool.coroutine
_list_s3_files_coroutine = _list_s3_files_tool.coroutine


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


@tool(
    "read_file_from_s3",
    (
        "Read a file from S3 and return its content (truncated for large files). "
        "Returns first 50 rows for CSV files, or first 50K characters for other files. "
        "For processing large files, use execute_code with s3_inputs instead."
    ),
    {
        "bucket": str,
        "key": str,
    },
)
@traced_mcp_tool("read_file_from_s3")
async def read_file_from_s3_mcp(args: dict[str, Any]) -> dict[str, Any]:
    """Delegate to the LangChain tool's underlying coroutine."""
    key = args.get("key") or ""
    if not key:
        return _err("read_file_from_s3 requires a non-empty 'key' argument.")
    bucket = args.get("bucket") or None
    try:
        text = await _read_file_coroutine(bucket=bucket, key=key)
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected error reading from S3 (MCP)")
        return _err(f"Error reading from S3: {e}")
    # The LangChain tool returns "Error: ..." / "Error reading ..." on
    # known failures; map those to is_error=True so the span status and
    # tool.success attribute reflect reality. ``looks_like_tool_error``
    # matches the underlying tool's exact error grammar so a legitimate
    # file whose content starts with the bare word "Error" stays
    # classified as success.
    if looks_like_tool_error(text):
        return _err(text)
    return _ok(text)


@tool(
    "list_s3_files",
    (
        "List files in an S3 bucket with optional prefix filter. "
        "Use this to discover available files in an S3 bucket before processing them."
    ),
    {
        "bucket": str,
        "prefix": str,
    },
)
@traced_mcp_tool("list_s3_files")
async def list_s3_files_mcp(args: dict[str, Any]) -> dict[str, Any]:
    """Delegate to the LangChain tool's underlying coroutine."""
    bucket = args.get("bucket") or None
    prefix = args.get("prefix") or ""
    try:
        text = await _list_s3_files_coroutine(bucket=bucket, prefix=prefix)
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected error listing S3 files (MCP)")
        return _err(f"Error listing S3 files: {e}")
    if looks_like_tool_error(text):
        return _err(text)
    return _ok(text)


def build_s3_server() -> Any:
    """Return the MCP server config object exposing both S3 tools."""
    return create_sdk_mcp_server(
        name="s3",
        version="1.0.0",
        tools=[read_file_from_s3_mcp, list_s3_files_mcp],
    )


__all__ = ["build_s3_server", "read_file_from_s3_mcp", "list_s3_files_mcp"]
