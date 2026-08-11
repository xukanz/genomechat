"""Phase 1 SDK-based coder worker.

Routes through the Claude Agent SDK instead of LangChain ``create_agent``.
The system prompt, toolset (MCP-wrapped), and governance path (Portkey
Bedrock) all mirror the LangChain coder for an honest A/B comparison when
the evaluation phase runs.

Contract (must match the LangChain path):

- Same system prompt — built via ``compose_coder_system_prompt``
  (task 12b single source of truth)
- Same toolset — ``mcp__{sandbox,s3,file_ops}__*`` (LangChain path exposes the
  same 6 tools via ``coder.py`` tool list)
- Empty-string return on ANY failure — ``coder_node`` converts empty
  content to the "⚠️ CODER TASK FAILED" marker so the orchestrator replans
  identically on either backend

Exception handling: SDK subprocess errors (``CLINotFoundError``,
``CLIConnectionError``, ``ProcessError``, ``CLIJSONDecodeError``,
``asyncio.TimeoutError``) are logged at distinct levels and mapped to the
empty-string return; they NEVER propagate to ``@trace_node`` because the
LangChain path also swallows them via ``result['messages'][-1].content``
defaulting to empty when the agent fails.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from src.agents.coder import compose_coder_system_prompt
from src.config.code_language import CodeLanguageType
from src.config.settings import settings
from src.service.mcp import build_all_coder_servers, mcp_tool_names
from src.service.sdk_runtime import build_transcript_dir, cleanup_request_artifacts
import src.service.observability.decorators as _dec
from src.service.observability.cost import compute_cost

logger = logging.getLogger(__name__)


def _serialize_messages_for_sdk(messages: list[Any]) -> str:
    """Serialize the full LangGraph message history into a single SDK prompt.

    The LangChain path passes the remapped message list to the worker agent;
    the SDK's ``query()`` takes a single prompt string. We flatten with
    explicit role tags so the model sees turn order and speaker roles,
    matching the conversation shape the LangChain wrapper would serialize
    over the wire.

    Continuity across coder invocations comes from the LangGraph
    checkpoint (stateless query() per PRD §6), not the SDK's session
    machinery — each ``query()`` gets the full history fresh.
    """
    if not messages:
        return ""
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", None) or getattr(msg, "role", None) or "unknown"
        content = getattr(msg, "content", "") or ""
        name = getattr(msg, "name", None)
        tag = f"{role}:{name}" if name else role
        lines.append(f"<<<{tag}>>>\n{content}")
    return "\n\n".join(lines)


def _build_options(
    system_prompt: str,
    transcript_dir: Path,
    code_language: CodeLanguageType,
) -> Any:
    """Construct ClaudeAgentOptions for a coder invocation.

    ``code_language`` is threaded into ``mcp_tool_names`` so the tool
    surface exposed to the SDK matches the LangChain coder for the same
    session (Python-only / R-only / auto). This is the parity invariant
    Codex flagged in the Phase 1 review.

    Imported at call time to make mocking in tests trivial (no module-level
    SDK import to patch away).
    """
    from claude_agent_sdk import ClaudeAgentOptions

    portkey_headers = f"x-portkey-slug: {settings.portkey_bedrock_slug}"

    # Env overlay for the SDK subprocess. Two invariants:
    #
    #   1. ``ANTHROPIC_API_KEY`` must stay empty so the bundled Anthropic CLI
    #      sends ``Authorization: Bearer`` instead of ``x-api-key`` (Portkey
    #      rejects ``x-api-key`` with HTTP 401).
    #
    #   2. ``ANTHROPIC_BASE_URL`` must be the Portkey gateway ROOT — NOT the
    #      ``/v1``-suffixed form LangChain uses. The bundled CLI appends
    #      ``/v1/messages`` itself; a ``/v1``-suffixed base produces the
    #      broken ``/v1/v1/messages`` path that Portkey forwards to Bedrock
    #      as a Coral ``UnknownOperationException``. ``settings.portkey_anthropic_base_url``
    #      is the normalized form.
    env = {
        "ANTHROPIC_BASE_URL": settings.portkey_anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.portkey_bedrock_api_key or "",
        "ANTHROPIC_CUSTOM_HEADERS": portkey_headers,
        "ANTHROPIC_API_KEY": "",
    }

    # Governance parity guard: a future refactor that re-enables
    # ANTHROPIC_API_KEY silently re-routes traffic onto the x-api-key path
    # which Portkey rejects — fail loud instead.
    assert env["ANTHROPIC_API_KEY"] == "", (
        "ANTHROPIC_API_KEY must be blank for Portkey Bedrock path; "
        "presence of a non-empty value causes x-api-key header to be sent."
    )

    return ClaudeAgentOptions(
        model=settings.coder_sdk_model,
        env=env,
        tools=[],  # strip Claude Code builtins from LLM context
        allowed_tools=mcp_tool_names(code_language),
        mcp_servers=build_all_coder_servers(),
        system_prompt=system_prompt,
        permission_mode=settings.coder_sdk_permission_mode,
        max_turns=settings.coder_sdk_max_turns,
        cwd=str(transcript_dir),
        setting_sources=[],  # Phase 3 Skills work re-enables
        include_partial_messages=False,
    )


def _extract_final_text(result_message: Any, last_assistant_blocks: list[Any]) -> str:
    """Pull the final response text from the SDK message stream.

    Precedence:
      1. ``ResultMessage.result`` when populated (SDK's own final answer)
      2. Concatenated TextBlocks from the last AssistantMessage (fallback
         when ResultMessage.result is empty — e.g. stopped-at-max-turns)
    """
    result = getattr(result_message, "result", None) if result_message else None
    if isinstance(result, str) and result.strip():
        return result
    texts: list[str] = []
    for block in last_assistant_blocks or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            texts.append(text)
    return "\n".join(t for t in texts if t).strip()


def _emit_gen_ai_chat_span(
    usage: dict[str, Any] | None,
    total_cost_usd: float | None,
    model: str,
) -> None:
    """Emit one ``gen_ai.chat`` span per coder invocation.

    The SDK does not route through LangChain's callback manager, so the
    OTelCallbackHandler never fires. We emit the span manually from
    ResultMessage data so downstream observability sees the same shape
    the LangChain path produces.

    Attribute shape follows the Phase 0 contract and OTel GenAI semconv:
      gen_ai.system, gen_ai.request.model, gen_ai.usage.input_tokens,
      gen_ai.usage.output_tokens, gen_ai.usage.cost_usd.
    """
    usage = usage or {}
    input_tokens = int(usage.get("input_tokens") or usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("outputTokens") or 0)

    # Prefer the SDK's own cost computation when present — it knows about
    # cache tokens our compute_cost() table doesn't model.
    cost_usd = total_cost_usd
    if cost_usd is None:
        cost_usd = compute_cost(model, input_tokens, output_tokens)

    with _dec.tracer.start_as_current_span(
        "gen_ai.chat",
        attributes={
            "gen_ai.system": "anthropic",
            "gen_ai.request.model": model,
            "gen_ai.usage.input_tokens": input_tokens,
            "gen_ai.usage.output_tokens": output_tokens,
            "gen_ai.usage.cost_usd": round(cost_usd or 0.0, 6),
        },
    ) as span:
        span.set_status(Status(StatusCode.OK))


def _record_failure_on_parent_span(reason: str, exc: Exception | None = None) -> None:
    """Attach error state to the enclosing ``agent.node.coder`` span.

    Because ``coder_sdk`` catches SDK exceptions and returns "" (matching
    LangChain-path semantics), the ``@trace_node("coder")`` decorator never
    sees the failure. We reach the enclosing span directly so the trace
    still records what went wrong.
    """
    span = trace.get_current_span()
    if span is not None and span.is_recording():
        span.set_attribute("coder.sdk.failure_reason", reason)
        if exc is not None:
            span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, reason))


async def invoke_coder_sdk(
    user_id: Optional[str],
    project_snippets: list[dict] | None,
    code_language: CodeLanguageType,
    state: dict,
    thread_id: str,
) -> str:
    """Run one coder turn through the Claude Agent SDK.

    Returns the final text response, or "" on failure (matching the
    LangChain path's empty-response semantics so ``coder_node`` converts
    it to the standard failure marker).

    Never raises — all SDK / subprocess errors are logged at a level that
    reflects severity and converted to "". A ``gen_ai.chat`` span is
    emitted whenever ResultMessage.usage is available, even on partial
    failures.
    """
    # Imports deferred to call time: (a) keeps module-level imports cheap,
    # (b) lets tests mock the SDK without touching coder_sdk module symbols
    # at import time.
    from claude_agent_sdk import (
        CLIConnectionError,
        CLIJSONDecodeError,
        CLINotFoundError,
        ProcessError,
        query,
    )

    system_prompt = compose_coder_system_prompt(
        user_id=user_id,
        project_snippets=project_snippets,
        code_language=code_language,
    )
    prompt = _serialize_messages_for_sdk(state.get("messages", []))
    if not prompt:
        logger.warning("coder_sdk: empty message history — returning empty response")
        return ""

    transcript_dir = build_transcript_dir(thread_id or "")
    usage: dict[str, Any] | None = None
    total_cost_usd: float | None = None
    result_message: Any = None
    last_assistant_blocks: list[Any] = []

    try:
        options = _build_options(system_prompt, transcript_dir, code_language)

        async for msg in query(prompt=prompt, options=options):
            cls_name = type(msg).__name__
            if cls_name == "AssistantMessage":
                # Replace — we want the LAST assistant message's content as
                # the fallback for ResultMessage.result.
                last_assistant_blocks = list(getattr(msg, "content", None) or [])
            elif cls_name == "ResultMessage":
                result_message = msg
                usage = getattr(msg, "usage", None) or usage
                cost = getattr(msg, "total_cost_usd", None)
                if cost is not None:
                    total_cost_usd = cost

        final = _extract_final_text(result_message, last_assistant_blocks)
        return final

    except CLINotFoundError as e:
        logger.error("coder_sdk: Claude Code CLI not found: %s", e)
        _record_failure_on_parent_span("sdk.cli_not_found", e)
        return ""
    except CLIConnectionError as e:
        logger.error("coder_sdk: CLI connection error: %s", e)
        _record_failure_on_parent_span("sdk.connection_error", e)
        return ""
    except ProcessError as e:
        logger.error("coder_sdk: subprocess error: %s", e)
        _record_failure_on_parent_span("sdk.process_error", e)
        return ""
    except CLIJSONDecodeError as e:
        logger.error("coder_sdk: JSON decode error from CLI: %s", e)
        _record_failure_on_parent_span("sdk.json_decode_error", e)
        return ""
    except asyncio.TimeoutError as e:
        logger.error("coder_sdk: query timed out")
        _record_failure_on_parent_span("sdk.timeout", e)
        return ""
    except Exception as e:  # noqa: BLE001
        logger.exception("coder_sdk: unexpected error — treating as failure")
        _record_failure_on_parent_span("sdk.unexpected_error", e)
        return ""
    finally:
        # Always emit gen_ai.chat when we have ANY usage data — even on
        # partial failures the upstream cost/observability should see it.
        if usage is not None:
            try:
                _emit_gen_ai_chat_span(usage, total_cost_usd, settings.coder_sdk_model)
            except Exception:  # noqa: BLE001
                logger.exception("coder_sdk: gen_ai.chat span emission failed")
        # Always clean up — transcript dir OR projects dir, whichever exists.
        try:
            cleanup_request_artifacts(transcript_dir)
        except Exception:  # noqa: BLE001
            logger.exception("coder_sdk: cleanup_request_artifacts failed")


__all__ = ["invoke_coder_sdk"]
