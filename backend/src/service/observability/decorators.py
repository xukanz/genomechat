"""`@trace_node` / `@trace_tool` decorators.

- `@trace_node(agent_name)` wraps an async LangGraph node. Reads AgentState
  fields for span attributes without mutating state. When the wrapped node
  returns a `Command(goto=...)`, we emit a `langgraph.command` event so the
  transition is durably recorded on the span tree (per the plan's
  "capture what happened" principle). Attributes stay restricted to the
  minimum-commitment schema.

- `@trace_tool` wraps a LangChain `StructuredTool` by replacing its
  `.coroutine` attribute. Verified against langchain_core >= 1.0.7 —
  `.coroutine` is the async callable `.ainvoke({...})` delegates to, so
  wrapping it traces every public-API invocation.
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from src.config.settings import settings
from src.utils.context import thread_id_context

tracer = trace.get_tracer("genomechat.platform")


def _serialize_payload(value: Any) -> str:
    """Serialize a payload for span attributes, truncated to settings cap.

    Uses ``default=str`` so Pydantic models, datetimes, and other non-JSON
    types degrade to ``str(...)`` instead of raising. Truncation is marked
    so consumers know the value was clipped.
    """
    try:
        s = json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        s = str(value)
    cap = settings.trace_payload_max_chars
    if len(s) > cap:
        return s[:cap] + f"…[truncated {len(s) - cap} chars]"
    return s


def trace_node(agent_name: str) -> Callable:
    """Return a decorator that emits a span per LangGraph node invocation.

    Supports both sync and async nodes — LangGraph currently runs `coordinator_node`
    synchronously and the four workers asynchronously.
    """

    def _build_attrs(state: Any) -> dict[str, Any]:
        def read(key: str) -> str:
            if isinstance(state, dict):
                return str(state.get(key) or "")
            return ""

        return {
            "agent.name": agent_name,
            "agent.thread_id": read("thread_id"),
            "agent.database_id": read("database_id"),
            "agent.research_mode": read("research_mode"),
            "agent.code_language": read("code_language"),
        }

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
                attrs = _build_attrs(state)
                with tracer.start_as_current_span(
                    f"agent.node.{agent_name}", attributes=attrs
                ) as span:
                    span.set_attribute("active_skills", [])
                    if settings.trace_capture_payloads:
                        span.set_attribute("langfuse.observation.input", _serialize_payload(state))
                    try:
                        result = await func(state, *args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
                    if settings.trace_capture_payloads:
                        span.set_attribute(
                            "langfuse.observation.output", _serialize_payload(result)
                        )
                    goto = _extract_goto(result)
                    if goto is not None:
                        span.add_event("langgraph.command", attributes={"goto": goto})
                    # Don't clobber an ERROR status that the wrapped code (e.g.
                    # SDK paths' _record_failure_on_parent_span) already stamped
                    # on the parent span — they catch and return "" rather than
                    # re-raise, so the only failure signal is the prior status.
                    # Use getattr to support NonRecordingSpan (no .status attr)
                    # returned when OTel isn't configured.
                    prior_status = getattr(span, "status", None)
                    if prior_status is None or prior_status.status_code != StatusCode.ERROR:
                        span.set_status(Status(StatusCode.OK))
                    return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            attrs = _build_attrs(state)
            with tracer.start_as_current_span(f"agent.node.{agent_name}", attributes=attrs) as span:
                span.set_attribute("active_skills", [])
                if settings.trace_capture_payloads:
                    span.set_attribute("langfuse.observation.input", _serialize_payload(state))
                try:
                    result = func(state, *args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
                if settings.trace_capture_payloads:
                    span.set_attribute("langfuse.observation.output", _serialize_payload(result))
                goto = _extract_goto(result)
                if goto is not None:
                    span.add_event("langgraph.command", attributes={"goto": goto})
                prior_status = getattr(span, "status", None)
                if prior_status is None or prior_status.status_code != StatusCode.ERROR:
                    span.set_status(Status(StatusCode.OK))
                return result

        return sync_wrapper

    return decorator


def trace_tool(tool_obj: Any) -> Any:
    """Wrap a StructuredTool so every invocation emits an `agent.tool.{name}` span.

    Apply BELOW `@tool` so decorator order evaluates bottom-up:

        @trace_tool
        @tool
        async def execute_code(...): ...

    Handles both async (StructuredTool.coroutine) and sync (StructuredTool.func)
    tools — we wrap whichever is populated. Verified against langchain_core
    >= 1.0.7: `.ainvoke({...})` delegates to `.coroutine`; `.invoke({...})`
    delegates to `.func`.
    """
    tool_name = getattr(tool_obj, "name", "unknown")
    original_coroutine = getattr(tool_obj, "coroutine", None)
    original_func = getattr(tool_obj, "func", None)

    if original_coroutine is None and original_func is None:
        raise ValueError(
            f"trace_tool requires a StructuredTool with .func or .coroutine; "
            f"'{tool_name}' exposes neither."
        )

    def _hash_args(args: tuple, kwargs: dict) -> str:
        return hashlib.sha256(
            json.dumps({"args": args, "kwargs": kwargs}, default=str, sort_keys=True).encode()
        ).hexdigest()[:16]

    def _build_attrs(args: tuple, kwargs: dict) -> dict[str, Any]:
        # agent.thread_id hoists onto the span so MongoDB-side tenant scoping
        # can filter tool spans by thread, matching what @trace_node already
        # emits for node spans. Read the platform's existing ContextVar set
        # per-request by chat.py — never introduce a parallel propagation.
        return {
            "tool.name": tool_name,
            "tool.args_hash": _hash_args(args, kwargs),
            "agent.thread_id": thread_id_context.get() or "",
        }

    if original_coroutine is not None:

        @functools.wraps(original_coroutine)
        async def async_wrapped(*args: Any, **kwargs: Any) -> Any:
            attrs = _build_attrs(args, kwargs)
            with tracer.start_as_current_span(f"agent.tool.{tool_name}", attributes=attrs) as span:
                if settings.trace_capture_payloads:
                    span.set_attribute(
                        "langfuse.observation.input",
                        _serialize_payload({"args": args, "kwargs": kwargs}),
                    )
                try:
                    result = await original_coroutine(*args, **kwargs)
                    span.set_attribute("tool.success", True)
                    if settings.trace_capture_payloads:
                        span.set_attribute(
                            "langfuse.observation.output", _serialize_payload(result)
                        )
                    return result
                except Exception as e:
                    span.set_attribute("tool.success", False)
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        tool_obj.coroutine = async_wrapped

    if original_func is not None:

        @functools.wraps(original_func)
        def sync_wrapped(*args: Any, **kwargs: Any) -> Any:
            attrs = _build_attrs(args, kwargs)
            with tracer.start_as_current_span(f"agent.tool.{tool_name}", attributes=attrs) as span:
                if settings.trace_capture_payloads:
                    span.set_attribute(
                        "langfuse.observation.input",
                        _serialize_payload({"args": args, "kwargs": kwargs}),
                    )
                try:
                    result = original_func(*args, **kwargs)
                    span.set_attribute("tool.success", True)
                    if settings.trace_capture_payloads:
                        span.set_attribute(
                            "langfuse.observation.output", _serialize_payload(result)
                        )
                    return result
                except Exception as e:
                    span.set_attribute("tool.success", False)
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

        tool_obj.func = sync_wrapped

    return tool_obj


def _extract_goto(result: Any) -> str | None:
    """Return the `goto` field if result is a LangGraph Command; else None.

    Accepts anything with a `goto` attribute — avoids importing langgraph.types
    at decorator-import time to keep the module lightweight.
    """
    goto = getattr(result, "goto", None)
    if isinstance(goto, str):
        return goto
    return None
