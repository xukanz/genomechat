"""Tests for the in-process S3 MCP server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_read_file_from_s3_mcp_success(in_memory_span_exporter):
    from src.service.mcp.s3_server import read_file_from_s3_mcp

    with patch(
        "src.service.mcp.s3_server._read_file_coroutine",
        new=AsyncMock(return_value="file contents here"),
    ) as mock_read:
        result = await read_file_from_s3_mcp.handler(
            {"bucket": "my-bucket", "key": "path/to/file.csv"}
        )

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "file contents here"
    mock_read.assert_awaited_once_with(bucket="my-bucket", key="path/to/file.csv")

    spans = in_memory_span_exporter.get_finished_spans()
    assert any(s.name == "agent.tool.read_file_from_s3" for s in spans)


@pytest.mark.asyncio
async def test_read_file_from_s3_mcp_empty_key_error():
    from src.service.mcp.s3_server import read_file_from_s3_mcp

    result = await read_file_from_s3_mcp.handler({"bucket": "b", "key": ""})
    assert result["is_error"] is True
    assert "non-empty 'key'" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_read_file_from_s3_mcp_default_bucket_fallback():
    """When bucket is omitted, the underlying coroutine is called with bucket=None.

    The LangChain tool itself performs the default-bucket lookup via
    ``settings.aws_default_bucket`` — we just need to confirm we pass through.
    """
    from src.service.mcp.s3_server import read_file_from_s3_mcp

    with patch(
        "src.service.mcp.s3_server._read_file_coroutine",
        new=AsyncMock(return_value="data"),
    ) as mock_read:
        await read_file_from_s3_mcp.handler({"key": "some/key"})

    mock_read.assert_awaited_once_with(bucket=None, key="some/key")


@pytest.mark.asyncio
async def test_read_file_from_s3_mcp_error_string_maps_to_is_error(in_memory_span_exporter):
    """A LangChain 'Error: ...' return must flip is_error=True + span error status."""
    from opentelemetry.trace import StatusCode

    from src.service.mcp.s3_server import read_file_from_s3_mcp

    with patch(
        "src.service.mcp.s3_server._read_file_coroutine",
        new=AsyncMock(return_value="Error: bucket not in allowed list"),
    ):
        result = await read_file_from_s3_mcp.handler({"bucket": "x", "key": "k"})

    assert result["is_error"] is True
    spans = in_memory_span_exporter.get_finished_spans()
    matching = [s for s in spans if s.name == "agent.tool.read_file_from_s3"]
    assert matching
    assert matching[0].status.status_code == StatusCode.ERROR


@pytest.mark.asyncio
async def test_list_s3_files_mcp_success(in_memory_span_exporter):
    from src.service.mcp.s3_server import list_s3_files_mcp

    with patch(
        "src.service.mcp.s3_server._list_s3_files_coroutine",
        new=AsyncMock(return_value="key1, key2, key3"),
    ):
        result = await list_s3_files_mcp.handler({"bucket": "b", "prefix": "data/"})

    assert result["is_error"] is False
    assert "key1" in result["content"][0]["text"]
    spans = in_memory_span_exporter.get_finished_spans()
    assert any(s.name == "agent.tool.list_s3_files" for s in spans)


@pytest.mark.asyncio
async def test_list_s3_files_mcp_empty_prefix_allowed():
    """Prefix is optional; empty string is the tool's documented default."""
    from src.service.mcp.s3_server import list_s3_files_mcp

    with patch(
        "src.service.mcp.s3_server._list_s3_files_coroutine",
        new=AsyncMock(return_value="k1"),
    ) as mock_list:
        await list_s3_files_mcp.handler({"bucket": "b"})

    mock_list.assert_awaited_once_with(bucket="b", prefix="")


def test_build_s3_server_registers_both_tools():
    from src.service.mcp.s3_server import build_s3_server

    server = build_s3_server()
    assert server["name"] == "s3"
    assert server["type"] == "sdk"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        "Error occurred at line 42 of the script\nstack trace follows...",
        "Error code: 17\n[INFO] retrying\n",
        "Error-handling notes for the operator\n=====",
    ],
)
async def test_read_file_from_s3_mcp_preserves_content_starting_with_bare_Error(content):
    """A legitimate file whose content starts with the bare word 'Error' must
    NOT be reclassified as a tool failure. Regression for the Codex
    adversarial review finding.
    """
    from src.service.mcp.s3_server import read_file_from_s3_mcp

    with patch(
        "src.service.mcp.s3_server._read_file_coroutine",
        new=AsyncMock(return_value=content),
    ):
        result = await read_file_from_s3_mcp.handler(
            {"bucket": "b", "key": "logs/file.txt"}
        )

    assert result["is_error"] is False, (
        f"content starting with bare 'Error' was misclassified as a tool error: {content[:60]!r}"
    )
    # Content passes through verbatim
    assert result["content"][0]["text"] == content


@pytest.mark.asyncio
async def test_read_file_from_s3_mcp_known_error_prefix_still_mapped_to_error():
    """The stricter match must still catch the known error grammar — this is
    the forward-compat check so the fix doesn't loosen the error detection.
    """
    from src.service.mcp.s3_server import read_file_from_s3_mcp

    with patch(
        "src.service.mcp.s3_server._read_file_coroutine",
        new=AsyncMock(return_value="Error: bucket not in allowed list"),
    ):
        result = await read_file_from_s3_mcp.handler({"bucket": "x", "key": "k"})
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_list_s3_files_mcp_preserves_content_starting_with_bare_Error():
    """list_s3_files is a low-risk path but shares the same contract — pin it."""
    from src.service.mcp.s3_server import list_s3_files_mcp

    with patch(
        "src.service.mcp.s3_server._list_s3_files_coroutine",
        new=AsyncMock(return_value="Error_2024_logs/, Error_archive/, other_key"),
    ):
        result = await list_s3_files_mcp.handler({"bucket": "b", "prefix": ""})
    assert result["is_error"] is False
    assert "Error_2024_logs" in result["content"][0]["text"]
