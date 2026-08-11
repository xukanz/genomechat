"""In-process MCP server exposing file-tracking operations to the SDK.

Wraps ``list_files_by_thread`` and ``list_files_by_type`` from
``src.tools.file_operations``. These read ``thread_id_context`` internally
to scope results to the caller's conversation — because the MCP server runs
in the same Python interpreter as the request handler, the ContextVar
propagates into the handler without additional plumbing.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from src.service.mcp._result_helpers import looks_like_tool_error
from src.service.mcp._span_helpers import traced_mcp_tool
from src.tools.file_operations import (
    list_files_by_thread as _list_files_by_thread_tool,
)
from src.tools.file_operations import (
    list_files_by_type as _list_files_by_type_tool,
)

logger = logging.getLogger(__name__)

_list_files_by_thread_coroutine = _list_files_by_thread_tool.coroutine
_list_files_by_type_coroutine = _list_files_by_type_tool.coroutine


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


@tool(
    "list_files_by_thread",
    (
        "List files created in the current conversation thread with full metadata. "
        "The thread_id is automatically extracted from the conversation context, "
        "so you don't need to provide it."
    ),
    {
        # All optional — the tool reads thread_id_context by default
        "thread_id": str,
        "file_type": str,
        "limit": int,
    },
)
@traced_mcp_tool("list_files_by_thread")
async def list_files_by_thread_mcp(args: dict[str, Any]) -> dict[str, Any]:
    thread_id = args.get("thread_id") or None
    file_type = args.get("file_type") or None
    limit = args.get("limit") or 20
    try:
        text = await _list_files_by_thread_coroutine(
            thread_id=thread_id,
            file_type=file_type,
            limit=limit,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("list_files_by_thread (MCP) raised")
        return _err(f"Error listing files: {e}")
    if looks_like_tool_error(text):
        return _err(text)
    return _ok(text)


@tool(
    "list_files_by_type",
    (
        "List files by type (query_result, analysis, coder_output, other) with full "
        "metadata. The thread_id is automatically extracted from the conversation "
        "context; provide it only to search a different thread."
    ),
    {
        "file_type": str,
        "thread_id": str,
        "limit": int,
    },
)
@traced_mcp_tool("list_files_by_type")
async def list_files_by_type_mcp(args: dict[str, Any]) -> dict[str, Any]:
    file_type = args.get("file_type") or ""
    if not file_type:
        return _err("list_files_by_type requires a non-empty 'file_type' argument.")
    thread_id = args.get("thread_id") or None
    limit = args.get("limit") or 20
    try:
        text = await _list_files_by_type_coroutine(
            file_type=file_type,
            thread_id=thread_id,
            limit=limit,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("list_files_by_type (MCP) raised")
        return _err(f"Error listing files: {e}")
    if looks_like_tool_error(text):
        return _err(text)
    return _ok(text)


def build_file_ops_server() -> Any:
    """Return the MCP server config object exposing both file-tracking tools."""
    return create_sdk_mcp_server(
        name="file_ops",
        version="1.0.0",
        tools=[list_files_by_thread_mcp, list_files_by_type_mcp],
    )


__all__ = [
    "build_file_ops_server",
    "list_files_by_thread_mcp",
    "list_files_by_type_mcp",
]
