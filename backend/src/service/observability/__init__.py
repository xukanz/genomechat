"""OpenTelemetry observability package.

Phase 0 public API:
    setup_tracing(app)              — called once from FastAPI lifespan startup
    tracer                           — module-level OTel tracer handle
    trace_node, trace_tool           — decorators for LangGraph nodes + LangChain tools
    OTelCallbackHandler              — LangChain BaseCallbackHandler for LLM spans
    MongoDBSpanExporter              — custom SpanExporter for MongoDB traces collection
    InMemorySpanExporter             — re-export for the eval harness
    compute_cost                     — per-model USD cost calculation
"""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.service.observability.callbacks import OTelCallbackHandler
from src.service.observability.cost import compute_cost
from src.service.observability.decorators import trace_node, trace_tool, tracer
from src.service.observability.mongodb_exporter import MongoDBSpanExporter
from src.service.observability.otel_setup import setup_tracing
from src.service.observability.trace_enrichment import (
    build_request_trace_attrs,
    build_request_trace_finalize_attrs,
    build_request_trace_output_attr,
)

__all__ = [
    "setup_tracing",
    "tracer",
    "trace_node",
    "trace_tool",
    "OTelCallbackHandler",
    "MongoDBSpanExporter",
    "InMemorySpanExporter",
    "compute_cost",
    "build_request_trace_attrs",
    "build_request_trace_finalize_attrs",
    "build_request_trace_output_attr",
]
