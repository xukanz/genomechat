"""Phase 2 Workstream B — SDK orchestrator prototype (branch-only).

An alternative orchestrator implementation using the Claude Agent SDK's
``AgentDefinition`` + built-in ``TodoWrite`` primitives instead of the
LangChain ``create_agent(response_format=OrchestratorResponse)`` +
``manage_plan`` + LangGraph-loop pattern.

**This module is a PROTOTYPE.** It is expected to live only on
``feat/phase-2b-orchestrator-prototype`` and be evaluated against the
LangChain orchestrator for the Workstream B ADR. It is NEVER merged into
the integration branch in Phase 2; promoting it is a Phase 3 decision
that depends on the eval outcome.

## Architectural delta vs. the LangChain orchestrator

LangChain path (``orchestrator.py`` + ``graph/nodes.py:orchestrator_node``):
  - Stateless planner: produces a routing decision (``OrchestratorResponse``)
    per LangGraph loop iteration.
  - The graph is the scheduler — it re-invokes the orchestrator after
    each worker, passing the full accumulated state.
  - ~130 lines of defensive override code at
    ``graph/nodes.py:469-533`` compensate for cases where the LLM's
    routing contradicts its own plan (e.g., routing to ``__end__`` with
    pending steps).

SDK path (this module):
  - Self-driving: ``query()`` runs a single multi-turn conversation that
    calls sub-agents via ``AgentDefinition`` until the orchestrator's
    ``TodoWrite`` plan is complete.
  - Scheduling is internal to the SDK — no graph re-entry between
    worker calls.
  - The ADR evaluates whether this eliminates the defensive-override code
    in exchange for acceptable plan-completion parity.

## Contract

Same as ``coder_sdk.invoke_coder_sdk``:

- Never raises. All SDK subprocess / connection / JSON-decode errors are
  logged and mapped to an empty-string return so ``orchestrator_node``
  can convert to the same failure marker the LangChain path would
  produce.
- Emits one ``gen_ai.chat`` span per invocation with
  ``gen_ai.request.model``, token usage, cost. Outer ``@trace_node
  ("orchestrator")`` span covers both backends and records
  ``agent.backend=sdk`` when this function runs.
- Reuses Phase 1 infrastructure: ``portkey_anthropic_base_url`` (MUST —
  skipping reintroduces the ``/v1/v1/messages`` Coral error),
  ``build_transcript_dir`` / ``cleanup_request_artifacts`` for per-request
  SDK artifact isolation, the exception-to-empty-string pattern.

## Known open questions (captured in the ADR after evaluation)

- ``TodoWrite`` vs ``manage_plan`` lifecycle semantics — the SDK builtin
  may not model ``failed`` step state the way ``manage_plan`` does.
- Cost envelope — multi-turn SDK conversations with sub-agents may
  consume more tokens than discrete LangGraph loop iterations.
- Structured routing — evaluation measures whether the prototype's
  free-form plan narration yields correct tool-call sequences at
  parity with the LangChain path's ``OrchestratorResponse.next`` decisions.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from src.agents.orchestrator import compose_orchestrator_system_prompt
from src.config.research_mode import ResearchModeType
from src.config.settings import settings
from src.service.mcp import (
    build_all_orchestrator_servers,
    orchestrator_mcp_tool_names,
)
from src.service.sdk_runtime import build_transcript_dir, cleanup_request_artifacts
from src.service.observability.cost import compute_cost
import src.service.observability.decorators as _dec

logger = logging.getLogger(__name__)


def _serialize_messages_for_sdk(messages: list[Any]) -> str:
    """Flatten the LangGraph message history into a single SDK prompt.

    Mirrors ``coder_sdk._serialize_messages_for_sdk`` verbatim. Kept as a
    separate function here so future refactors of one path don't silently
    change the other — any change that needs to apply to both backends
    should be made in both files intentionally.
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


def _build_agent_definitions() -> dict[str, Any]:
    """Return the per-worker ``AgentDefinition`` map for the orchestrator.

    Each worker gets its own system prompt + allowed-tools subset so the
    SDK's ``TodoWrite`` + ``@agent`` handoff pattern can route cleanly.
    Worker prompts are intentionally terse — the heavy lifting (database
    schema context, code-language preference, etc.) still flows through
    the same state the LangChain workers see, but the orchestrator SDK
    can't delegate mid-query to a real LangGraph subgraph, so these
    ``AgentDefinition`` stubs approximate the coder / sql personas
    internally.

    Imported lazily because ``AgentDefinition`` is an SDK symbol and tests
    mock the SDK import surface wholesale.
    """
    from claude_agent_sdk import AgentDefinition

    coder_tools = [
        "mcp__sandbox__execute_code",
        "mcp__sandbox__execute_r_code",
        "mcp__s3__read_file_from_s3",
        "mcp__s3__list_s3_files",
        "mcp__file_ops__list_files_by_thread",
        "mcp__file_ops__list_files_by_type",
    ]
    sql_tools = [
        "mcp__database__execute_sql_query",
        "mcp__database__execute_sql_query_and_save",
        "mcp__database__get_database_schema",
        "mcp__database__get_random_subsamples",
        "mcp__s3__read_file_from_s3",
    ]

    return {
        "coder": AgentDefinition(
            description=(
                "Executes Python or R code in the sandbox. Can read/list S3 "
                "files and track generated artifacts. Use for calculations, "
                "data analysis, visualizations, and file-producing steps."
            ),
            prompt=(
                "You are the Coder worker. Execute Python/R code in the "
                "sandbox to fulfill the orchestrator's task. Read S3 files "
                "when referenced. Produce clear, commented code and explain "
                "your results."
            ),
            tools=coder_tools,
        ),
        "sql_agent": AgentDefinition(
            description=(
                "Runs SQL queries against the active database. Use for "
                "structured queries, schema inspection, and data extraction "
                "that downstream coder steps will analyze."
            ),
            prompt=(
                "You are the SQL Agent. Inspect the schema with "
                "get_database_schema first, sample with get_random_subsamples "
                "when unsure of values, then run the query. Use "
                "execute_sql_query_and_save when the full dataset matters to "
                "downstream analysis."
            ),
            tools=sql_tools,
        ),
    }


def _allowed_tools_for_mode(mode: str) -> list[str]:
    """Return ``allowed_tools`` for the orchestrator based on the tool mode.

    ``delegated`` (default): empty list. The orchestrator can only call
    ``TodoWrite`` + ``AgentDefinition`` sub-agents — all MCP tools are
    invoked inside the scoped conversation of whichever sub-agent the
    orchestrator delegates to. This keeps the orchestrator's token
    footprint small (no tool results accumulate in its context) and
    mirrors the LangChain orchestrator's delegation contract.

    ``flat``: full 14-tool surface. The orchestrator sees every MCP tool
    directly AND the sub-agents; Sonnet usually picks direct calls on
    simple queries. Faster per-turn but less context-efficient on
    multi-step plans where tool results compound.

    Unknown values fall back to ``delegated`` with a warning so a typo
    in the env never hard-fails the request path.
    """
    normalized = (mode or "").lower().strip()
    if normalized == "flat":
        return orchestrator_mcp_tool_names()
    if normalized != "delegated":
        logger.warning(
            "orchestrator_sdk: unknown ORCHESTRATOR_SDK_TOOL_MODE=%r — falling back to 'delegated'",
            mode,
        )
    return []


def _build_options(
    system_prompt: str,
    transcript_dir: Path,
) -> Any:
    """Construct ``ClaudeAgentOptions`` for an orchestrator invocation.

    Mirrors ``coder_sdk._build_options``. Two non-negotiables:

    1. ``ANTHROPIC_API_KEY=""`` — forces ``Authorization: Bearer`` header
       (Portkey rejects ``x-api-key``).
    2. ``ANTHROPIC_BASE_URL=settings.portkey_anthropic_base_url`` — the
       ``/v1``-stripped form. Using the raw ``portkey_base_url`` here
       reintroduces the ``/v1/v1/messages`` Coral bug that Phase 1 caught.
    """
    from claude_agent_sdk import ClaudeAgentOptions

    portkey_headers = f"x-portkey-slug: {settings.portkey_bedrock_slug}"

    env = {
        "ANTHROPIC_BASE_URL": settings.portkey_anthropic_base_url,
        "ANTHROPIC_AUTH_TOKEN": settings.portkey_bedrock_api_key or "",
        "ANTHROPIC_CUSTOM_HEADERS": portkey_headers,
        "ANTHROPIC_API_KEY": "",
    }

    assert env["ANTHROPIC_API_KEY"] == "", (
        "ANTHROPIC_API_KEY must be blank for Portkey Bedrock path; "
        "presence of a non-empty value causes x-api-key header to be sent."
    )

    # Per Phase 2 scope note: the SDK builtin TodoWrite replaces our
    # custom manage_plan. Do NOT add ``manage_plan`` to the tool list —
    # the orchestrator prototype's whole point is that TodoWrite is
    # sufficient and the defensive override code can go away.
    #
    # ``allowed_tools`` is gated by ORCHESTRATOR_SDK_TOOL_MODE so the
    # Workstream B evaluation can A/B the two delegation strategies.
    # Either mode keeps ``mcp_servers`` fully registered because the
    # sub-agents need them — ``allowed_tools`` is the only gate.
    return ClaudeAgentOptions(
        model=settings.orchestrator_sdk_model,
        env=env,
        tools=["TodoWrite"],  # SDK builtin — replaces custom manage_plan
        allowed_tools=_allowed_tools_for_mode(settings.orchestrator_sdk_tool_mode),
        mcp_servers=build_all_orchestrator_servers(),
        system_prompt=system_prompt,
        permission_mode=settings.coder_sdk_permission_mode,
        max_turns=settings.orchestrator_sdk_max_turns,
        cwd=str(transcript_dir),
        setting_sources=[],
        include_partial_messages=False,
        agents=_build_agent_definitions(),
    )


def _extract_final_text(result_message: Any, last_assistant_blocks: list[Any]) -> str:
    """Pull the final response text from the SDK message stream.

    Identical precedence rule to ``coder_sdk._extract_final_text``:
    ``ResultMessage.result`` first, falling back to the last
    ``AssistantMessage``'s concatenated text blocks when the SDK stopped
    before producing a terminal result (e.g., max_turns).
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
    """Emit one ``gen_ai.chat`` span per orchestrator invocation.

    Mirrors ``coder_sdk._emit_gen_ai_chat_span`` exactly — same attribute
    shape, same Phase 0 contract. Kept as a separate function here for
    the same reason as ``_serialize_messages_for_sdk``: future refactors
    to one backend should not silently drift the other.
    """
    usage = usage or {}
    input_tokens = int(usage.get("input_tokens") or usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("outputTokens") or 0)

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
    """Attach error state to the enclosing ``agent.node.orchestrator`` span."""
    span = trace.get_current_span()
    if span is not None and span.is_recording():
        span.set_attribute("orchestrator.sdk.failure_reason", reason)
        if exc is not None:
            span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, reason))


async def invoke_orchestrator_sdk(
    state: dict,
    thread_id: str,
    research_mode: ResearchModeType = "standard",
) -> str:
    """Run one orchestrator turn through the Claude Agent SDK.

    Returns the synthesized final response text, or "" on failure so the
    orchestrator node converts to the standard failure marker and the
    graph terminates with a visible error state.

    Unlike the LangChain orchestrator which is re-invoked per LangGraph
    loop, this call drives the entire multi-worker conversation internally
    via ``AgentDefinition`` sub-agents and ``TodoWrite`` plan tracking.
    The graph node that calls this function is expected to route directly
    to ``__end__`` after it returns (no loop-back).

    Args:
        state: LangGraph agent state — ``messages`` is the only required key.
        thread_id: Conversation identifier; flows through to the per-request
            transcript directory for SDK artifact isolation.
        research_mode: ``"standard"`` | ``"deep_research"``. Inherits the
            research_mode-tagged prompt section through the shared
            ``compose_orchestrator_system_prompt`` helper.
    """
    from claude_agent_sdk import (
        CLIConnectionError,
        CLIJSONDecodeError,
        CLINotFoundError,
        ProcessError,
        query,
    )

    system_prompt = compose_orchestrator_system_prompt(research_mode=research_mode)
    prompt = _serialize_messages_for_sdk(state.get("messages", []))
    if not prompt:
        logger.warning("orchestrator_sdk: empty message history — returning empty response")
        return ""

    transcript_dir = build_transcript_dir(thread_id or "")
    usage: dict[str, Any] | None = None
    total_cost_usd: float | None = None
    result_message: Any = None
    last_assistant_blocks: list[Any] = []

    try:
        options = _build_options(system_prompt, transcript_dir)

        async for msg in query(prompt=prompt, options=options):
            cls_name = type(msg).__name__
            if cls_name == "AssistantMessage":
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
        logger.error("orchestrator_sdk: Claude Code CLI not found: %s", e)
        _record_failure_on_parent_span("sdk.cli_not_found", e)
        return ""
    except CLIConnectionError as e:
        logger.error("orchestrator_sdk: CLI connection error: %s", e)
        _record_failure_on_parent_span("sdk.connection_error", e)
        return ""
    except ProcessError as e:
        logger.error("orchestrator_sdk: subprocess error: %s", e)
        _record_failure_on_parent_span("sdk.process_error", e)
        return ""
    except CLIJSONDecodeError as e:
        logger.error("orchestrator_sdk: JSON decode error from CLI: %s", e)
        _record_failure_on_parent_span("sdk.json_decode_error", e)
        return ""
    except asyncio.TimeoutError as e:
        logger.error("orchestrator_sdk: query timed out")
        _record_failure_on_parent_span("sdk.timeout", e)
        return ""
    except Exception as e:  # noqa: BLE001
        logger.exception("orchestrator_sdk: unexpected error — treating as failure")
        _record_failure_on_parent_span("sdk.unexpected_error", e)
        return ""
    finally:
        if usage is not None:
            try:
                _emit_gen_ai_chat_span(usage, total_cost_usd, settings.orchestrator_sdk_model)
            except Exception:  # noqa: BLE001
                logger.exception("orchestrator_sdk: gen_ai.chat span emission failed")
        try:
            cleanup_request_artifacts(transcript_dir)
        except Exception:  # noqa: BLE001
            logger.exception("orchestrator_sdk: cleanup_request_artifacts failed")


__all__ = ["invoke_orchestrator_sdk"]
