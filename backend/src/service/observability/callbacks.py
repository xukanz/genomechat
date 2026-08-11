"""LangChain callback handler that emits `gen_ai.chat` spans.

One span per LLM call. Streaming: `on_llm_start` fires once, `on_llm_end`
fires once with aggregated usage — do NOT start/end spans per
`on_llm_new_token`. Errors bubble up as ERROR status; we never swallow the
underlying exception, but we do swallow observability-internal errors so
instrumentation can never break the user's LLM call.
"""

from __future__ import annotations

import logging
import threading
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.trace import Status, StatusCode

from src.config.settings import settings
from src.service.observability.cost import compute_cost
from src.service.observability.decorators import _serialize_payload
from src.utils.context import thread_id_context

logger = logging.getLogger(__name__)


# Module-level tracer handle, mirroring the pattern in
# `src.service.observability.decorators.tracer`. The evaluation harness swaps
# BOTH handles for the duration of `replay()` so LLM spans land in the same
# in-memory exporter as node and tool spans. Tests / production paths that
# need to override the provider should do so by reassigning this attribute,
# not by patching `trace.get_tracer`.
tracer = trace.get_tracer("genomechat.platform")


class OTelCallbackHandler(BaseCallbackHandler):
    """Emit one `gen_ai.chat` span per LangChain LLM invocation.

    Supports concurrent calls: `run_id` from LangChain uniquely identifies
    each call, and we keep a thread-safe dict of active spans keyed by it.
    """

    def __init__(self) -> None:
        self._spans: dict[UUID, tuple[Any, object]] = {}
        self._lock = threading.Lock()

    # LangChain passes **kwargs that differ between versions — accept liberally.
    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        try:
            model, system = _extract_model_and_system(serialized, kwargs)
            attrs = {
                "gen_ai.system": system,
                "gen_ai.request.model": model,
                "agent.thread_id": thread_id_context.get() or "",
            }
            if settings.trace_capture_payloads:
                attrs["langfuse.observation.input"] = _serialize_payload(prompts)
            span = tracer.start_span("gen_ai.chat", attributes=attrs)
            # Make the span the current span so child tool calls nest properly.
            ctx = trace.set_span_in_context(span)
            token = attach(ctx)
            with self._lock:
                self._spans[run_id] = (span, token)
        except Exception:
            logger.debug("OTelCallbackHandler.on_llm_start: swallowed", exc_info=True)

    on_chat_model_start = on_llm_start  # langchain_core calls one or the other

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            with self._lock:
                entry = self._spans.pop(run_id, None)
            if entry is None:
                return
            span, token = entry
            try:
                model = (
                    span.attributes.get("gen_ai.request.model", "")
                    if hasattr(span, "attributes")
                    else ""
                )
                input_tokens, output_tokens = _extract_usage(response)
                cost = compute_cost(model, input_tokens, output_tokens)
                span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
                span.set_attribute("gen_ai.usage.cost_usd", cost)
                if settings.trace_capture_payloads:
                    span.set_attribute(
                        "langfuse.observation.output", _serialize_payload(_extract_text(response))
                    )
                span.set_status(Status(StatusCode.OK))
            finally:
                span.end()
                detach(token)
        except Exception:
            logger.debug("OTelCallbackHandler.on_llm_end: swallowed", exc_info=True)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            with self._lock:
                entry = self._spans.pop(run_id, None)
            if entry is None:
                return
            span, token = entry
            try:
                span.record_exception(error)
                span.set_status(Status(StatusCode.ERROR, str(error)))
            finally:
                span.end()
                detach(token)
        except Exception:
            logger.debug("OTelCallbackHandler.on_llm_error: swallowed", exc_info=True)


def _extract_model_and_system(
    serialized: dict[str, Any], kwargs: dict[str, Any]
) -> tuple[str, str]:
    """Best-effort extraction of model ID and provider from callback args."""
    model = ""
    # LangChain serializes the chat model class; kwargs can include 'invocation_params'
    invocation_params = kwargs.get("invocation_params") or {}
    model = (
        invocation_params.get("model")
        or invocation_params.get("model_name")
        or (serialized or {}).get("name", "")
        or ""
    )
    # kwargs metadata is a common carrier for provider hints
    metadata = kwargs.get("metadata") or {}
    system = metadata.get("ls_provider") or metadata.get("provider") or ""
    if not system:
        m = (model or "").lower()
        if "anthropic" in m or "claude" in m:
            system = "anthropic"
        elif "gpt" in m or "openai" in m:
            system = "openai"
        else:
            system = "unknown"
    return model or "unknown", system


def _extract_usage(response: Any) -> tuple[int, int]:
    """Pull (input_tokens, output_tokens) from an LLMResult.

    Prefers the spike-validated `usage_metadata` shape (LangChain v1 BaseMessage
    attribute) over `response_metadata["token_usage"]` aliases.
    """
    # LLMResult.generations -> list[list[ChatGeneration]]
    generations = getattr(response, "generations", None) or []
    for row in generations:
        for gen in row:
            msg = getattr(gen, "message", None)
            if msg is None:
                continue
            usage = getattr(msg, "usage_metadata", None)
            if isinstance(usage, dict):
                return (
                    int(usage.get("input_tokens", 0) or 0),
                    int(usage.get("output_tokens", 0) or 0),
                )
            meta = getattr(msg, "response_metadata", None) or {}
            token_usage = meta.get("token_usage") if isinstance(meta, dict) else None
            if isinstance(token_usage, dict):
                return (
                    int(token_usage.get("prompt_tokens", 0) or 0),
                    int(token_usage.get("completion_tokens", 0) or 0),
                )
    # Fallback: LLMResult.llm_output["token_usage"]
    llm_output = getattr(response, "llm_output", None) or {}
    if isinstance(llm_output, dict):
        token_usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if isinstance(token_usage, dict):
            return (
                int(token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0)) or 0),
                int(token_usage.get("completion_tokens", token_usage.get("output_tokens", 0)) or 0),
            )
    return 0, 0


def _extract_text(response: Any) -> list[str]:
    """Pull completion text from an LLMResult for payload capture."""
    out: list[str] = []
    for row in getattr(response, "generations", None) or []:
        for gen in row:
            msg = getattr(gen, "message", None)
            text = getattr(msg, "content", None) if msg is not None else getattr(gen, "text", None)
            if text:
                out.append(text if isinstance(text, str) else str(text))
    return out
