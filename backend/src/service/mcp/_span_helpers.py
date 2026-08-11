"""OpenTelemetry span emission for SDK MCP tool handlers.

The Phase 0 ``@trace_tool`` decorator wraps a LangChain ``StructuredTool.coroutine``
— it cannot wrap SDK-decorated functions because those have a different
signature (single ``dict`` arg) and are not exposed as tool objects. Phase 1
ships ``traced_mcp_tool`` as the parallel surface, emitting a span with the
same shape the Phase 0 contract locks in:

    span name: agent.tool.<tool_name>
    attributes:
        tool.name: <tool_name>
        tool.args_hash: sha256 of args dict (truncated to 16 hex chars)
        tool.success: True if handler returned is_error=False, else False
        agent.thread_id: current thread_id_context value (may be "")

Never log raw args — they contain tenant file paths and user data. The
args_hash is sufficient for cross-referencing spans with logs/debugging.

Import the decorators module by reference (``import ... as _dec``) so the
replay harness's tracer swap on ``_dec.tracer`` is honored for MCP spans.
Using ``from ... import tracer`` captures the handle at import time and
defeats the swap.
"""

from __future__ import annotations

import functools
import hashlib
import json
from typing import Any, Awaitable, Callable

from opentelemetry.trace import Status, StatusCode

import src.service.observability.decorators as _dec
from src.utils.context import thread_id_context


McpHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _hash_args(args: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(args, default=str, sort_keys=True).encode()).hexdigest()[:16]


def traced_mcp_tool(
    name: str | None = None,
) -> Callable[[McpHandler], McpHandler]:
    """Decorator factory emitting an ``agent.tool.<name>`` span per MCP tool call.

    Apply BELOW the SDK's ``@tool`` decorator. Pass the MCP tool name
    explicitly so the span matches the name the LLM sees (the SDK
    registers the tool at ``mcp__<server>__<tool_name>``; our span
    attribute ``tool.name`` is the bare ``<tool_name>``)::

        @tool("execute_code", "...", {...})
        @traced_mcp_tool("execute_code")
        async def execute_code_mcp(args: dict) -> dict:
            ...

    If ``name`` is omitted, the function's ``__name__`` is used (useful for
    tests and quick prototypes where a strip-``_mcp``-suffix convention is
    acceptable).
    """

    def decorator(fn: McpHandler) -> McpHandler:
        tool_name = name or _default_name_from_fn(fn)

        @functools.wraps(fn)
        async def wrapper(args: dict[str, Any]) -> dict[str, Any]:
            attrs = {
                "tool.name": tool_name,
                "tool.args_hash": _hash_args(args or {}),
                "agent.thread_id": thread_id_context.get() or "",
            }
            with _dec.tracer.start_as_current_span(
                f"agent.tool.{tool_name}", attributes=attrs
            ) as span:
                try:
                    result = await fn(args)
                except Exception as e:
                    span.set_attribute("tool.success", False)
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
                is_error = (
                    bool(result.get("is_error", False)) if isinstance(result, dict) else False
                )
                span.set_attribute("tool.success", not is_error)
                if is_error:
                    span.set_status(Status(StatusCode.ERROR, "MCP tool returned is_error=True"))
                return result

        return wrapper

    return decorator


def _default_name_from_fn(fn: Callable[..., Any]) -> str:
    """Strip common suffixes that MCP handler functions use in this codebase."""
    base = getattr(fn, "__name__", "") or "unknown"
    for suffix in ("_mcp", "_handler"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


__all__ = ["traced_mcp_tool"]
