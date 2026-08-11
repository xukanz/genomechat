# Phase 0 → Phase 1 Contract

This document locks in the concrete API surface Phase 0 ships so Phase 1 (SDK coder swap) can build against it without surprises. Changes to anything below require a version bump on `traces.schema_version` and a companion migration note.

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
- `agent.backend: str` — `"langchain"` today; `"sdk"` reserved for Phase 1
- `agent.thread_id: str`
- `agent.database_id: str`
- `agent.research_mode: str`
- `agent.code_language: str`
- `active_skills: list[str]` — empty list today; Phase 3 Skills work populates

### Node span events (NOT attributes)

- `langgraph.command` with attribute `{goto: str}` — emitted exactly once per node return when the node returns a `Command(goto=...)` value
- `orchestrator.override_fired` with attribute `{reason: str}` — emitted exactly once when the orchestrator's defensive override code path runs (Phase 1+ callers can count these to quantify orchestrator reliability)

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

Any analysis that needs "plan completion rate," "retry count," "override fire count," "tool call sequence," etc. **derives from the parent-child span tree + events + the LangGraph MongoDB checkpoint**. Phase 1+ must NOT add new derived attributes to node spans without updating this contract and bumping `schema_version`.

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

## Feature flag resolver

```python
from src.config.agent_backends import AgentBackend, resolve_agent_backend

backend: AgentBackend = resolve_agent_backend("coder")    # AgentBackend.LANGCHAIN | AgentBackend.SDK
# Unknown agent names (coordinator, sql_agent, summarizer) always return LANGCHAIN.
# Invalid settings values fall back to LANGCHAIN with a warning log.
```

Phase 1 dispatch lives in `coder_node`; Phase 0 only reads the flag for span attribution.

## Trajectory replay harness public API

```python
from backend.evaluation.harness import replay, ReplayResult

result: ReplayResult = await replay(query_record, backend="langchain")
# query_record fields read: query, thread_id, database_id, project_id
# result fields: response, spans, duration_ms, cost_usd, backend, model_versions
```

`spans` is a `list[dict]` matching the trajectory JSONL record shape below. `replay` never writes to production MongoDB; it uses an `AsyncSqliteSaver(":memory:")` checkpointer and a contextvar-scoped TracerProvider that is restored on exit.

Phase 1 must not change this signature.

## Trajectory JSONL record schema

One line per replay in `backend/evaluation/baselines/*.jsonl`:

```json
{
  "query_record": {
    "query": "...",
    "thread_id": "...",
    "database_id": "...",
    "project_id": "...",
    "user_id": "...",
    "source_conversation_id": "...",
    "captured_at": "2026-05-01T12:34:56Z"
  },
  "response": "...",
  "spans": [
    {
      "trace_id": "...", "span_id": "...", "parent_span_id": null,
      "name": "agent.node.coder", "kind": "INTERNAL",
      "start_time_ns": 1745000000000000000, "end_time_ns": 1745000001000000000,
      "duration_ms": 1000.0,
      "status": {"code": "OK", "description": null},
      "attributes": {"agent.name": "coder", "agent.backend": "langchain", ...},
      "events": [{"name": "langgraph.command", "timestamp": ..., "attributes": {"goto": "orchestrator"}}]
    }
  ],
  "duration_ms": 12345.67,
  "cost_usd": 0.0123,
  "backend": "langchain",
  "model_versions": {"coder": "portkey_bedrock:us.anthropic.claude-sonnet-4-6", ...},
  "captured_at": "2026-05-01T12:34:56Z"
}
```

Failed replays include `"error": "<exception message>"` and empty `response` + `spans` so downstream consumers can filter deterministically.

## Run manifest schema

Every `cli run` writes `<output>.manifest.json`:

```json
{
  "backend": "langchain",
  "commit_sha": "e38ea41...",
  "settings_hash": "<sha256 of non-secret settings snapshot>",
  "model_versions": {"coder": "portkey_bedrock:us.anthropic.claude-sonnet-4-6", ...},
  "total_queries": 200,
  "captured_at": "2026-05-01T12:34:56Z",
  "schema_version": "1"
}
```

`settings_hash` deliberately excludes every setting containing `key`, `secret`, `password`, `token`, or `auth` so the manifest can be shared without leaking credentials.

## Phase 0 exit smoke check

The `cli run` command ends with an automatic smoke check that validates the committed baseline JSONL:

- every line parses as JSON
- `response` is non-empty
- at least one span with `name` matching `agent.node.*`
- at least one span with `name == "gen_ai.chat"`
- no record carries an `error` field

Any failure prints `smoke check: {passed}/{total} trajectories valid` and exits non-zero. This is the Phase 0 exit gate for baseline capture.

## Stability guarantees

- **Span names** — stable through Phase 1; adding new names is allowed, renaming or removing requires a `schema_version` bump.
- **Required attributes** — stable through Phase 1; adding new attributes is allowed (if narrowly scoped), removing or renaming requires a `schema_version` bump.
- **Feature flag resolver signature** — stable through Phase 1; Phase 1 may add new backends (e.g. `AgentBackend.HYBRID`) but not change the function signature.
- **Replay harness signature** — stable through Phase 1; Phase 1 adds an `sdk` branch by implementing the `backend='sdk'` code path, not by changing the external interface.

## What Phase 1 does NOT get from Phase 0

- A comparison API (`/internal/traces/comparison`) — dropped per 2026-04-30 scope revision. Phase 1's SDK vs LangChain comparison uses the harness output JSONL directly.
- An LLM judge / rubric framework / scoring aggregator — deferred to Phase 1+ when we have two backends.
- A raw transcript API — `/internal/traces/raw` returns 501 until a `traces:raw` scope implementation lands in a later phase.
- A synthetic dataset — per user decision, the consented historical corpus is the only Phase 0 dataset.
