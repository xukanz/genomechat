"""Tests for the in-process file_ops MCP server.

Critical invariant: ``thread_id_context`` set by the FastAPI request task
must propagate into the MCP handler, so the underlying LangChain tool
reads the correct thread_id. This is the ContextVar-inheritance test the
plan specifically calls out.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_list_files_by_thread_mcp_passes_args_through():
    from src.service.mcp.file_ops_server import list_files_by_thread_mcp

    with patch(
        "src.service.mcp.file_ops_server._list_files_by_thread_coroutine",
        new=AsyncMock(return_value="Found 0 file(s) in thread 'test'"),
    ) as mock_list:
        await list_files_by_thread_mcp.handler(
            {"thread_id": "u:c", "file_type": "query_result", "limit": 10}
        )

    mock_list.assert_awaited_once_with(
        thread_id="u:c", file_type="query_result", limit=10
    )


@pytest.mark.asyncio
async def test_list_files_by_thread_mcp_uses_default_limit():
    from src.service.mcp.file_ops_server import list_files_by_thread_mcp

    with patch(
        "src.service.mcp.file_ops_server._list_files_by_thread_coroutine",
        new=AsyncMock(return_value="ok"),
    ) as mock_list:
        await list_files_by_thread_mcp.handler({})

    kwargs = mock_list.call_args.kwargs
    assert kwargs["limit"] == 20
    assert kwargs["thread_id"] is None
    assert kwargs["file_type"] is None


@pytest.mark.asyncio
async def test_thread_id_context_propagates_into_mcp_handler():
    """Critical: ContextVar set in parent task must be readable from handler body.

    We don't need to hit the real tool — we install a fake coroutine that
    reads thread_id_context itself to assert inheritance.
    """
    from src.service.mcp.file_ops_server import list_files_by_thread_mcp
    from src.utils.context import thread_id_context

    seen: list[str] = []

    async def fake_coroutine(thread_id, file_type, limit):
        seen.append(thread_id_context.get() or "<empty>")
        return "ok"

    token = thread_id_context.set("propagation-test:conv-1")
    try:
        with patch(
            "src.service.mcp.file_ops_server._list_files_by_thread_coroutine",
            new=fake_coroutine,
        ):
            await list_files_by_thread_mcp.handler({})
    finally:
        thread_id_context.reset(token)

    assert seen == ["propagation-test:conv-1"]


@pytest.mark.asyncio
async def test_thread_id_context_survives_asyncio_gather():
    """ContextVar must propagate into concurrently-launched handlers."""
    from src.service.mcp.file_ops_server import list_files_by_thread_mcp
    from src.utils.context import thread_id_context

    async def _fire(tid: str, seen: dict[str, str]):
        token = thread_id_context.set(tid)
        try:
            async def fake_coroutine(thread_id, file_type, limit):
                seen[tid] = thread_id_context.get() or "<empty>"
                return "ok"

            with patch(
                "src.service.mcp.file_ops_server._list_files_by_thread_coroutine",
                new=fake_coroutine,
            ):
                await list_files_by_thread_mcp.handler({})
        finally:
            thread_id_context.reset(token)

    seen: dict[str, str] = {}
    await asyncio.gather(_fire("a", seen), _fire("b", seen), _fire("c", seen))
    assert seen == {"a": "a", "b": "b", "c": "c"}


@pytest.mark.asyncio
async def test_list_files_by_type_mcp_empty_file_type_returns_error():
    from src.service.mcp.file_ops_server import list_files_by_type_mcp

    result = await list_files_by_type_mcp.handler({})
    assert result["is_error"] is True
    assert "'file_type'" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_list_files_by_type_mcp_error_string_maps_to_is_error():
    from src.service.mcp.file_ops_server import list_files_by_type_mcp

    with patch(
        "src.service.mcp.file_ops_server._list_files_by_type_coroutine",
        new=AsyncMock(return_value="Error: Invalid file_type 'garbage'. Valid types: ..."),
    ):
        result = await list_files_by_type_mcp.handler({"file_type": "garbage"})

    assert result["is_error"] is True


def test_build_file_ops_server_registers_both_tools():
    from src.service.mcp.file_ops_server import build_file_ops_server

    server = build_file_ops_server()
    assert server["name"] == "file_ops"
    assert server["type"] == "sdk"
