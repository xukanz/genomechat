"""Trajectory replay harness.

`replay(query_record, backend='langchain')` runs one query end-to-end through
a fresh in-memory-checkpointed graph with a contextvar-scoped TracerProvider.
Returns the response, captured spans, wall-clock duration, and total LLM cost.

Two isolation guarantees:

1. The replay never writes to production MongoDB checkpoints — we use
   `AsyncSqliteSaver(":memory:")` exclusively.
2. Spans emitted during replay never leak to the production TracerProvider —
   we install a local `InMemorySpanExporter`-backed provider on the
   decorators' module-level `tracer` and restore it on exit. This also means
   concurrent replays in the same process must use the same lock-stepped
   mechanism; Phase 0 ships with a semaphore in `cli.py` to serialize calls.

Phase 0 intentionally does no scoring — the JSONL output IS the report.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.config.settings import settings
from src.graph.builder import build_graph
from src.utils.context import thread_id_context

logger = logging.getLogger(__name__)


@dataclass
class ReplayResult:
    response: str
    spans: list[dict[str, Any]]
    duration_ms: float
    cost_usd: float
    backend: str
    model_versions: dict[str, str] = field(default_factory=dict)


def _serialize_span(span: Any) -> dict[str, Any]:
    """Convert an OTel ReadableSpan to the committed Phase 0 JSONL shape."""
    ctx = span.get_span_context()
    parent = span.parent
    return {
        "trace_id": format(ctx.trace_id, "032x"),
        "span_id": format(ctx.span_id, "016x"),
        "parent_span_id": format(parent.span_id, "016x") if parent else None,
        "name": span.name,
        "kind": span.kind.name,
        "start_time_ns": span.start_time,
        "end_time_ns": span.end_time,
        "duration_ms": (span.end_time - span.start_time) / 1_000_000,
        "status": {
            "code": span.status.status_code.name,
            "description": span.status.description,
        },
        "attributes": {k: _attr_value(v) for k, v in (span.attributes or {}).items()},
        "events": [
            {
                "name": e.name,
                "timestamp": e.timestamp,
                "attributes": {k: _attr_value(v) for k, v in (e.attributes or {}).items()},
            }
            for e in span.events
        ],
    }


def _attr_value(v: Any) -> Any:
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)


async def replay(
    query_record: dict[str, Any],
    backend: str = "langchain",
    orchestrator_backend: str = "langchain",
) -> ReplayResult:
    """Run the graph once against `query_record['query']` with per-replay tracer isolation.

    ``backend`` selects the **coder** worker backend for this replay.
    ``orchestrator_backend`` selects the **orchestrator** backend
    independently, enabling the 2x2 evaluation matrix the Phase 2
    Workstream B ADR requires: ``(coder=LC,  orch=LC)``,
    ``(coder=SDK, orch=LC)``, ``(coder=LC,  orch=SDK)``,
    ``(coder=SDK, orch=SDK)``.

    Valid values for both parameters: ``"langchain"`` | ``"sdk"``.
    Backend dispatch happens inside ``graph.nodes.coder_node`` /
    ``graph.nodes.orchestrator_node`` via the respective
    ``resolve_agent_backend(...)`` calls, which read their ContextVar
    overrides first. Overrides are set/reset on the per-task ContextVars
    so concurrent replays with different backend combinations don't race
    on shared settings.
    """
    if backend not in ("langchain", "sdk"):
        raise ValueError(f"Unsupported backend '{backend}'. Valid: 'langchain' | 'sdk'.")
    if orchestrator_backend not in ("langchain", "sdk"):
        raise ValueError(
            f"Unsupported orchestrator_backend '{orchestrator_backend}'. "
            "Valid: 'langchain' | 'sdk'."
        )

    # Local tracer + exporter — do NOT touch the global TracerProvider.
    # We swap the two module-level tracer handles (decorators, callbacks) that
    # all of our Phase 0 span-emitting code uses. Global TracerProvider swap
    # is deliberately avoided: it would pollute concurrent prod traffic and
    # OTel only permits one set_tracer_provider() per process.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    import src.service.observability.callbacks as cb_mod
    import src.service.observability.decorators as dec_mod

    replay_tracer = provider.get_tracer("genomechat.platform.replay")
    original_dec_tracer = dec_mod.tracer
    original_cb_tracer = cb_mod.tracer
    dec_mod.tracer = replay_tracer
    cb_mod.tracer = replay_tracer

    # Ensure OTel is logically enabled so decorators emit; settings may still be False globally.
    original_otel_enabled = settings.otel_enabled
    settings.otel_enabled = True

    # Select the coder + orchestrator backends for this replay via per-task
    # ContextVars so concurrent replays with different backend combinations
    # don't race on shared settings. Each resolver
    # (``resolve_agent_backend("coder")`` / ``...("orchestrator")``) reads
    # the respective ContextVar first and falls back to
    # ``settings.<agent>_backend`` in production code paths.
    from src.config.agent_backends import (
        AgentBackend,
        coder_backend_context,
        orchestrator_backend_context,
    )

    coder_token = coder_backend_context.set(AgentBackend(backend))
    orch_token = orchestrator_backend_context.set(AgentBackend(orchestrator_backend))

    # Set the request-scoped ContextVar so tool + LLM spans carry thread_id
    # without requiring call-site plumbing.
    tid_token = thread_id_context.set(query_record.get("thread_id") or "eval-replay")

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        builder = build_graph()

        t0 = time.perf_counter()
        async with AsyncSqliteSaver.from_conn_string(":memory:") as checkpointer:
            agent = builder.compile(checkpointer=checkpointer)
            config = {
                "configurable": {
                    "thread_id": query_record.get("thread_id") or "eval-replay",
                }
            }
            initial_state = {
                "messages": [
                    {"role": "user", "content": query_record["query"]},
                ],
                "thread_id": query_record.get("thread_id") or "",
                "database_id": query_record.get("database_id") or "",
                "project_id": query_record.get("project_id") or "",
                "research_mode": "",
                "code_language": "python",
            }
            try:
                result = await agent.ainvoke(initial_state, config=config)
            except Exception:
                logger.exception("replay: graph ainvoke failed")
                raise
        duration_ms = (time.perf_counter() - t0) * 1000.0

        provider.force_flush()
        provider.shutdown()

        spans_raw = list(exporter.get_finished_spans())
        spans = [_serialize_span(s) for s in spans_raw]

        # Aggregate cost from gen_ai.chat spans; each already carries cost_usd.
        total_cost = 0.0
        for s in spans:
            if s["name"] == "gen_ai.chat":
                total_cost += float(s["attributes"].get("gen_ai.usage.cost_usd", 0.0) or 0.0)
        # If the callback didn't run (no OTel wiring), fall back to 0.

        response = _extract_response_text(result)
        model_versions = _snapshot_agent_models()

        return ReplayResult(
            response=response,
            spans=spans,
            duration_ms=duration_ms,
            cost_usd=round(total_cost, 6),
            backend=backend,
            model_versions=model_versions,
        )
    finally:
        dec_mod.tracer = original_dec_tracer
        cb_mod.tracer = original_cb_tracer
        settings.otel_enabled = original_otel_enabled
        coder_backend_context.reset(coder_token)
        orchestrator_backend_context.reset(orch_token)
        thread_id_context.reset(tid_token)


def _extract_response_text(state: dict[str, Any]) -> str:
    """Pull the last assistant-visible message text from the graph's final state."""
    messages = state.get("messages", []) if isinstance(state, dict) else []
    for msg in reversed(messages):
        content = None
        msg_type = None
        if isinstance(msg, dict):
            msg_type = msg.get("type") or msg.get("role")
            content = msg.get("content")
        else:
            msg_type = getattr(msg, "type", None)
            content = getattr(msg, "content", None)
        if isinstance(content, str) and content.strip():
            if msg_type in ("ai", "assistant", "tool"):
                return content.strip()
            # Human message without an assistant reply — keep scanning but fall back to this
            if msg_type in ("human", "user"):
                continue
            return content.strip()
    return ""


def _snapshot_agent_models() -> dict[str, str]:
    """Record the current AGENT_LLM_MAP so the manifest is reproducible."""
    try:
        from src.config.agents import AGENT_LLM_MAP

        return {agent: f"{prov}:{model}" for agent, (prov, model) in AGENT_LLM_MAP.items()}
    except Exception:
        return {}
