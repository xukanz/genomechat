"""Pydantic models for Phase 0 trace documents.

The MongoDB `traces` collection stores one document per span. These models
describe the minimum-commitment schema — any analysis that needs more derives
from the parent-child tree + events + the LangGraph checkpoint, not from new
span attributes. See phase0_phase1_contract.md for the full contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class LLMSpanAttrs(BaseModel):
    """Required attributes on `gen_ai.chat` spans.

    Follows OTel GenAI semantic conventions so third-party dashboards (Langfuse,
    LangSmith, Phoenix) render without translation.
    """

    gen_ai_system: str = Field(alias="gen_ai.system")
    gen_ai_request_model: str = Field(alias="gen_ai.request.model")
    gen_ai_usage_input_tokens: int = Field(alias="gen_ai.usage.input_tokens")
    gen_ai_usage_output_tokens: int = Field(alias="gen_ai.usage.output_tokens")
    gen_ai_usage_cost_usd: float = Field(alias="gen_ai.usage.cost_usd")

    model_config = {"populate_by_name": True}


class ToolSpanAttrs(BaseModel):
    """Required attributes on `agent.tool.{name}` spans."""

    tool_name: str = Field(alias="tool.name")
    tool_args_hash: str = Field(alias="tool.args_hash")
    tool_success: bool = Field(alias="tool.success", default=True)

    model_config = {"populate_by_name": True}


class NodeSpanAttrs(BaseModel):
    """Required attributes on `agent.node.{name}` spans.

    `active_skills` is reserved for Phase 3 Skills; written as `[]` today so
    downstream consumers can rely on the key existing.
    """

    agent_name: str = Field(alias="agent.name")
    agent_thread_id: str = Field(alias="agent.thread_id", default="")
    agent_database_id: str = Field(alias="agent.database_id", default="")
    agent_research_mode: str = Field(alias="agent.research_mode", default="")
    agent_code_language: str = Field(alias="agent.code_language", default="")
    active_skills: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class SpanEvent(BaseModel):
    """A single event attached to a span (e.g. `langgraph.command`)."""

    name: str
    timestamp: int
    attributes: dict[str, Any] = Field(default_factory=dict)


class SpanStatus(BaseModel):
    code: Literal["UNSET", "OK", "ERROR"] = "UNSET"
    description: Optional[str] = None


class TraceSpan(BaseModel):
    """One MongoDB document in the `traces` collection.

    Mirrors the shape emitted by `MongoDBSpanExporter._to_document`. `active_skills`
    lives at the top level AND on node attrs — the top-level copy is the quick-
    filter index target; the attrs copy preserves OTel semantic fidelity.
    """

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str
    kind: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    status: SpanStatus = Field(default_factory=SpanStatus)
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)
    resource: dict[str, Any] = Field(default_factory=dict)
    active_skills: list[str] = Field(default_factory=list)
    schema_version: str = "1"
