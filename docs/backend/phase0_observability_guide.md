# Phase 0 Observability Operator Guide

## Overview

Phase 0 adds a custom OpenTelemetry trace pipeline:

- Every LangGraph node, tool call, and LLM call emits a span
- Spans land in MongoDB `traces` collection via a custom `SpanExporter`
- A daily APScheduler job mirrors spans to S3 (`s3://<bucket>/traces/YYYY-MM-DD/spans.jsonl`)
- Internal API (`/internal/traces`) exposes scope-gated, audit-logged, rate-limited reads

All new behavior is disabled by default. Flipping the feature flags restores pre-Phase-0 behavior instantly.

## Enabling

Minimum env for production tracing:

```bash
OTEL_ENABLED=true
TRACE_STORAGE_ENABLED=true
# defaults: OTEL_SERVICE_NAME=genomechat-backend, TRACE_MONGODB_COLLECTION=traces,
#           TRACE_TTL_DAYS=90
```

Optional S3 archive (daily job at 02:00 local):

```bash
TRACE_S3_ARCHIVE_ENABLED=true
TRACE_S3_PREFIX=traces/
AWS_DEFAULT_BUCKET=<your-bucket>
```

Optional forward-compat Langfuse OTLP export (Phase 2 decision gate; default off):

```bash
LANGFUSE_ENABLED=false                 # default
LANGFUSE_OTLP_ENDPOINT=https://langfuse.internal/api/public/otel
LANGFUSE_AUTH_HEADER=<base64(public_key:secret_key)>
```

Internal endpoints are on by default for authenticated users (scope-gated):

```bash
INTERNAL_OBSERVABILITY_ENABLED=true   # default
INTERNAL_OBSERVABILITY_RATE_LIMIT_PER_HOUR=1000
```

## Trace document schema

One MongoDB document per span. Minimum-commitment shape:

| Field | Type | Notes |
|---|---|---|
| `trace_id` | `str` | hex |
| `span_id` | `str` | hex |
| `parent_span_id` | `str \| null` | hex of parent |
| `name` | `str` | `agent.node.{name}`, `agent.tool.{name}`, `gen_ai.chat`, or auto-instrumentor |
| `kind` | `str` | OTel SpanKind enum name |
| `start_time` | `datetime` | UTC; TTL-indexed |
| `end_time` | `datetime` | UTC |
| `duration_ms` | `float` | |
| `status` | `{code, description}` | `OK \| ERROR \| UNSET` |
| `attributes` | `dict` | See minimum-commitment schema below |
| `events` | `list[{name, timestamp, attributes}]` | `langgraph.command`, `orchestrator.override_fired` |
| `resource` | `dict` | service.name, service.version, deployment.environment |
| `active_skills` | `list[str]` | reserved for Phase 3; empty list today |
| `thread_id` | `str` | top-level indexed copy of `attributes["agent.thread_id"]` |
| `tenant_id` | `str` | derived from thread_id (`<user_id>:<conv_id>` → `<user_id>`) |
| `schema_version` | `str` | `"1"` |

### Attribute schema per span kind (the only attributes written)

**Node spans (`agent.node.{name}`):**
- `agent.name`
- `agent.thread_id`
- `agent.database_id`
- `agent.research_mode`
- `agent.code_language`
- `active_skills: []` (reserved)

Node span events:
- `langgraph.command` (with `goto: str` attribute) — emitted on node return
- `orchestrator.override_fired` (with `reason: str` attribute) — only when override path runs

**Tool spans (`agent.tool.{name}`):**
- `tool.name`
- `tool.args_hash` (sha256 prefix — never raw args)
- `tool.success`

**LLM spans (`gen_ai.chat`, follows OTel GenAI semantic conventions):**
- `gen_ai.system` (`anthropic` | `openai` | ...)
- `gen_ai.request.model`
- `gen_ai.usage.input_tokens`
- `gen_ai.usage.output_tokens`
- `gen_ai.usage.cost_usd` (platform-specific extension)

No other attributes are written. Any analysis that needs "plan completion rate," "override count," etc. derives it from the parent-child tree + events + the LangGraph MongoDB checkpoint. See [phase0_phase1_contract.md](phase0_phase1_contract.md) for the full contract.

## Querying traces

### Via the API (recommended)

Every call must supply a JWT with the `traces:read:own` scope (granted by default to every authenticated user).

```bash
# Your own spans (non-admins restricted to their own tenant_id)
curl -s "http://localhost:8000/internal/traces?limit=50" \
  -H "Authorization: Bearer $JWT" | jq '.spans | length'

# By thread_id (your own)
curl -s "http://localhost:8000/internal/traces?thread_id=<your_user_id>:<conv_id>" \
  -H "Authorization: Bearer $JWT"
```

Cross-tenant read (admin only; see scope grant procedure below):

```bash
curl -s "http://localhost:8000/internal/traces?thread_id=other_user:conv-9" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

### Via mongosh (bypassing audit log — use sparingly)

```javascript
// Count spans for a thread
db.traces.countDocuments({thread_id: "user-42:conv-123"})

// Latest spans for a user
db.traces.find({tenant_id: "user-42"}).sort({start_time: -1}).limit(10)

// Slow node invocations
db.traces.find({name: /^agent\.node\./, duration_ms: {$gt: 5000}}).limit(20)

// Errors
db.traces.find({"status.code": "ERROR"}).limit(20)

// Audit log inspection
db.observability_access_log.find().sort({timestamp: -1}).limit(10)
```

## Granting `traces:admin:cross-tenant`

The scope lets a named engineer query any tenant's traces. There is no admin UI in Phase 0; grants are manual MongoDB updates with an audit log entry.

1. Identify the user's `id` in the `users` collection.
2. Update the user record (preserve existing scopes):

   ```javascript
   db.users.updateOne(
     {id: "<user_id>"},
     {$addToSet: {scopes: "traces:admin:cross-tenant"}}
   )
   ```

3. Record the grant in the access log (include a business justification):

   ```javascript
   db.observability_access_log.insertOne({
     caller_user_id: "<grantor_user_id>",
     caller_email: "<grantor_email>",
     target_tenant: "<user_id>",
     target_thread_id: null,
     scopes_used: ["admin:grant"],
     path: "/internal/admin/scope-grant",
     query: {scope: "traces:admin:cross-tenant", reason: "incident #1234"},
     row_count: 1,
     response_status: 200,
     timestamp: new Date()
   })
   ```

4. Communicate to infosec — every grant is reviewed quarterly.

## Revoking a scope

```javascript
db.users.updateOne(
  {id: "<user_id>"},
  {$pull: {scopes: "traces:admin:cross-tenant"}}
)
```

Then log the revocation with the same audit-row template (`scopes_used: ["admin:revoke"]`).

## Token and cost accuracy

- **OpenAI / Azure Portkey path** — tokens reported by `response.usage_metadata` or `response_metadata["token_usage"]`. Accuracy is post-call authoritative (±0% when present). `tiktoken` is used only for pre-call estimation paths (±2% on list-priced models).
- **Anthropic / Bedrock path** — same `usage_metadata` source; verified in the pre-phase spike. No `tiktoken` involvement.
- **Cost** — derived from `compute_cost(model, input_tokens, output_tokens)` with a per-model USD table in `observability/cost.py`. Unknown models return `$0.00` (logged at DEBUG); update the price table alongside any model rollout.

Trust cost numbers only post-call. The operator guide notes accuracy bounds in the cost module docstring.

## S3 daily archive

`run_daily_archive()` runs at 02:00 (APScheduler cron job) when `TRACE_S3_ARCHIVE_ENABLED=true`.

- Writes `s3://<bucket>/traces/YYYY-MM-DD/spans.jsonl` with one span per line.
- Uses `get_s3_client()` singleton (same boto3 credential chain as file storage).
- On failure, logs + continues — does not halt the scheduler.

Manual trigger (for initial setup or gap recovery):

```python
# From a Python REPL in the backend env
from src.service.observability.s3_archive import run_daily_archive
from datetime import datetime, timezone
run_daily_archive(datetime(2026, 5, 1, tzinfo=timezone.utc))
```

## Rollback

### Instant (one restart)

```bash
OTEL_ENABLED=false
INTERNAL_OBSERVABILITY_ENABLED=false
```

After restart: decorators no-op (they delegate to a NoOp tracer), `/internal/*` routes unregister, S3 archive job stops.

### Data cleanup (optional)

`traces` and `observability_access_log` collections persist after flag flip. To reclaim storage:

```javascript
// Keep at least 1 year of access log per PRD §11 retention
db.observability_access_log.find({timestamp: {$lt: ISODate("2025-05-01T00:00:00Z")}}).deleteMany({})

// Traces TTL-expire automatically at settings.trace_ttl_days (default 90).
// Force immediate drop only if absolutely necessary:
db.traces.drop()
```

S3 archives (if enabled) are retained independently of MongoDB state.

## Common pitfalls

- **Hanging pytest integration tests** — the `internal_traces` fixtures rely on mongomock; production mongomock doesn't implement TTL indexes (we handle the warning gracefully) or `$regex` on dotted attribute keys (why we store `thread_id` / `tenant_id` as top-level fields).
- **Decorator order** — always `@trace_tool` ABOVE `@tool` / `@trace_node` ABOVE the node function. Python applies decorators bottom-up so `@tool` produces the `StructuredTool` first, which `@trace_tool` then instruments.
- **TTL index on fresh MongoDB** — the exporter creates it idempotently on init. If you see no trace expiry, verify the index exists (`db.traces.getIndexes()`) — a permission issue will surface in startup logs.
- **Cost comes out as $0** — the model name wasn't in the canonical table. Add it to `observability/cost.py::_PRICE_TABLE_USD_PER_MTOK` + `_MODEL_ALIASES`.
- **Langfuse OTLP unreachable** — `setup_tracing` catches the import/connection failure and continues with MongoDB export only. The startup log will include `setup_tracing: failed to initialize Langfuse exporter; skipping`.

## Testing before production

```bash
# Start backend with observability enabled
OTEL_ENABLED=true TRACE_STORAGE_ENABLED=true \
  uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Fire a chat turn
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"List the 5 genes with the most pathogenic variants in ClinVar","thread_id":"alice:test-phase0"}'

# Verify spans landed
mongosh "$MONGODB_URI" --eval 'db.traces.find({thread_id: "alice:test-phase0"}).count()'
# Expect: ≥ 5 (nodes + tools + LLM)

# Check access log
mongosh "$MONGODB_URI" --eval 'db.observability_access_log.find().sort({timestamp:-1}).limit(1).pretty()'
```
