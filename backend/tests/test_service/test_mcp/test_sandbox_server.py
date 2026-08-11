"""Tests for the in-process sandbox MCP server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_execute_code_mcp_delegates_to_sandbox(in_memory_span_exporter):
    from src.service.mcp.sandbox_server import execute_code_mcp

    with patch(
        "src.service.mcp.sandbox_server.call_sandbox",
        new=AsyncMock(return_value={"exit_code": 0, "stdout": "hello\n", "stderr": ""}),
    ) as mock_call, patch(
        "src.service.mcp.sandbox_server.format_sandbox_response",
        return_value="formatted-result",
    ) as mock_fmt:
        result = await execute_code_mcp.handler({"source": "print('hi')"})

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "formatted-result"
    mock_call.assert_awaited_once()
    mock_fmt.assert_called_once()

    spans = in_memory_span_exporter.get_finished_spans()
    assert any(s.name == "agent.tool.execute_code" for s in spans)


@pytest.mark.asyncio
async def test_execute_code_mcp_empty_source_returns_error():
    from src.service.mcp.sandbox_server import execute_code_mcp

    result = await execute_code_mcp.handler({"source": ""})
    assert result["is_error"] is True
    assert "non-empty 'source'" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_execute_code_mcp_sandbox_timeout_is_user_error(in_memory_span_exporter):
    import httpx

    from src.service.mcp.sandbox_server import execute_code_mcp

    with patch(
        "src.service.mcp.sandbox_server.call_sandbox",
        new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
    ):
        result = await execute_code_mcp.handler({"source": "print(1)"})

    assert result["is_error"] is True
    assert "timed out" in result["content"][0]["text"]

    spans = in_memory_span_exporter.get_finished_spans()
    # Error path — still emits the span, but tool.success=False
    matching = [s for s in spans if s.name == "agent.tool.execute_code"]
    assert matching and dict(matching[0].attributes)["tool.success"] is False


@pytest.mark.asyncio
async def test_execute_code_mcp_passes_optional_args_to_payload_builder():
    """Optional args (stdin/cmd_args/limits/s3_inputs/s3_outputs) flow through."""
    from src.service.mcp.sandbox_server import execute_code_mcp

    with patch(
        "src.service.mcp.sandbox_server.build_sandbox_payload",
        return_value={"source": "x"},
    ) as mock_build, patch(
        "src.service.mcp.sandbox_server.call_sandbox",
        new=AsyncMock(return_value={"exit_code": 0}),
    ), patch(
        "src.service.mcp.sandbox_server.format_sandbox_response",
        return_value="ok",
    ):
        await execute_code_mcp.handler({
            "source": "print(1)",
            "stdin": "input\n",
            "cmd_args": ["--flag"],
            "limits": {"wall_ms": 5000},
            "s3_inputs": [{"bucket": "b", "key": "k"}],
            "s3_outputs": [],  # explicitly empty — should be dropped
        })

    kwargs = mock_build.call_args.kwargs
    assert kwargs["source"] == "print(1)"
    assert kwargs["stdin"] == "input\n"
    assert kwargs["cmd_args"] == ["--flag"]
    assert kwargs["limits"] == {"wall_ms": 5000}
    assert kwargs["s3_inputs"] == [{"bucket": "b", "key": "k"}]
    assert kwargs["s3_outputs"] is None  # empty list -> None per _opt_list


@pytest.mark.asyncio
async def test_execute_r_code_mcp_delegates_to_r_sandbox(in_memory_span_exporter):
    from src.service.mcp.sandbox_server import execute_r_code_mcp

    with patch(
        "src.service.mcp.sandbox_server.call_sandbox",
        new=AsyncMock(return_value={"exit_code": 0, "stdout": "1\n"}),
    ) as mock_call, patch(
        "src.service.mcp.sandbox_server.format_sandbox_response",
        return_value="R-formatted",
    ):
        result = await execute_r_code_mcp.handler({"source": "print(1)"})

    assert result["is_error"] is False
    assert result["content"][0]["text"] == "R-formatted"
    spans = in_memory_span_exporter.get_finished_spans()
    assert any(s.name == "agent.tool.execute_r_code" for s in spans)


@pytest.mark.asyncio
async def test_execute_r_code_mcp_empty_source_returns_error():
    from src.service.mcp.sandbox_server import execute_r_code_mcp

    result = await execute_r_code_mcp.handler({"source": ""})
    assert result["is_error"] is True


def test_build_sandbox_server_registers_both_tools():
    from src.service.mcp.sandbox_server import build_sandbox_server

    server = build_sandbox_server()
    assert server["name"] == "sandbox"
    assert server["type"] == "sdk"
