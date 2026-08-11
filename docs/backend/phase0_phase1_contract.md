# Trace Schema Contract

This document locks in the concrete span/document surface the observability layer emits. Changes to anything below require a version bump on `traces.schema_version` and a companion migration note.

## Span names

| Span name | Emitted by | Cardinality |
|---|---|---|
| `agent.node.{coordinator,orchestrator,coder,sql_agent}` | `@trace_node` wrapper on graph nodes | 1 per node invocation |
| `agent.tool.{tool_name}` | `@trace_tool` wrapper on `@tool`-decorated functions | 1 per tool call |
| `gen_ai.chat` | `OTelCallbackHandler` on every `LLMService.create_llm` instance | 1 per LLM invocation |

Additional spans come from `opentelemetry.instrumentation.fastapi` and `opentelemetry.instrumentation.pymongo` — those follow upstream conventions and are Phase 0 best-effort (not part of this contract).

## Required span attributes (minimum-commitment schema)

### Node spans

- `agent.name: str`
- `agent.thread_id: str`
- `agent.database_id: str`
- `agent.research_mode: str`
- `agent.code_language: str`
- `active_skills: list[str]` — empty list today; Phase 3 Skills work populates

### Node span events (NOT attributes)

- `langgraph.command` with attribute `{goto: str}` — emitted exactly once per node return when the node returns a `Command(goto=...)` value
- `orchestrator.override_fired` with attribute `{reason: str}` — emitted exactly once when the orchestrator's defensive override code path runs (count these to quantify orchestrator reliability)

### Tool spans

- `tool.name: str`
- `tool.args_hash: str` — 16-char sha256 prefix; never raw args
- `tool.success: bool`

### LLM spans (OTel GenAI semantic conventions)

- `gen_ai.system: str` — `"anthropic" | "openai" | "unknown"` (best-effort)
- `gen_ai.request.model: str`
- `gen_ai.usage.input_tokens: int`
- `gen_ai.usage.output_tokens: int`
- `gen_ai.usage.cost_usd: float` — platform-specific extension, derived from `observability/cost.py`

### Schema principle

Any analysis that needs "plan completion rate," "retry count," "override fire count," "tool call sequence," etc. **derives from the parent-child span tree + events + the LangGraph MongoDB checkpoint**. Do NOT add new derived attributes to node spans without updating this contract and bumping `schema_version`.

## Top-level trace document fields (MongoDB)

Beyond OTel span attributes, each document carries these hoisted fields for indexable queries:

| Field | Type | Purpose |
|---|---|---|
| `trace_id` | `str` (hex) | OTel trace ID |
| `span_id` | `str` (hex) | OTel span ID |
| `parent_span_id` | `str \| null` | |
| `name` | `str` | span name |
| `start_time` | `datetime` | UTC, TTL-indexed |
| `end_time` | `datetime` | UTC |
| `duration_ms` | `float` | |
| `status` | `{code, description}` | |
| `attributes` | `dict` | see per-kind schema above |
| `events` | `list` | `{name, timestamp, attributes}` |
| `resource` | `dict` | service.name, service.version, deployment.environment |
| `active_skills` | `list[str]` | reserved for Phase 3 |
| `thread_id` | `str` | copy of `attributes["agent.thread_id"]`; indexed |
| `tenant_id` | `str` | `thread_id.split(":", 1)[0]`; indexed |
| `schema_version` | `str` | currently `"1"` |

## Stability guarantees

- **Span names** — adding new names is allowed; renaming or removing requires a `schema_version` bump.
- **Required attributes** — adding new attributes is allowed (if narrowly scoped); removing or renaming requires a `schema_version` bump.

## Deliberately out of scope

- A comparison API (`/internal/traces/comparison`) — dropped per 2026-04-30 scope revision.
- An LLM judge / rubric framework / scoring aggregator.
- A raw transcript API — `/internal/traces/raw` returns 501 until a `traces:raw` scope implementation lands.
