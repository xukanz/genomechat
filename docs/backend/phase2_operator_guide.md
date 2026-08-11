# Langfuse Operator Guide

> **Scope:** how to stand up Langfuse locally, wire the backend to it, and
> navigate a trace. Deployment of Langfuse to the cluster is gated on the
> Phase 2 observation window — see
> `.agents/decisions/phase2-langfuse-gate.md`. For the span schema itself,
> see `phase0_observability_guide.md`.

## 1. Stand up Langfuse locally

Langfuse ships a self-hosted Docker image. The simplest setup uses
Langfuse's compose file:

```bash
# One-shot local install — separate directory, not in this repo
git clone https://github.com/langfuse/langfuse.git /tmp/langfuse
cd /tmp/langfuse
docker compose up -d
# Langfuse UI lands on http://localhost:3000
```

**Port note:** the genomechat frontend runs on `localhost:3100` in
dev (moved from 3000 precisely so Langfuse can have 3000). If you
hit a port conflict, stop any stale `genomechat-frontend-dev`
container first.

Create a project in the Langfuse UI, grab the public + secret keys
from *Project Settings → API Keys*, then build the base64 auth
header:

```bash
echo -n "pk-lf-xxx:sk-lf-xxx" | base64
# → cGstbGYt...==
```

## 2. Wire the genomechat backend to Langfuse

In `backend/.env`:

```bash
LANGFUSE_ENABLED=true
# Container → host Langfuse. host.containers.internal is Podman's
# host-gateway alias (== host.docker.internal on Docker Desktop).
LANGFUSE_OTLP_ENDPOINT=http://host.containers.internal:3000/api/public/otel/v1/traces
LANGFUSE_AUTH_HEADER=<the base64 blob from §1>

# Optional — attaches prompt + completion text to Langfuse's Input/Output
# columns. DEV-ONLY: payloads can be large / contain sensitive data.
TRACE_CAPTURE_PAYLOADS=true
# Optional — cap per-attribute serialized payload size.
TRACE_PAYLOAD_MAX_CHARS=8000
```

Restart the backend container:

```bash
cd docker && docker compose restart backend
```

## 3. Navigate a trace in the Langfuse UI

A single `/chat/stream` request produces one Langfuse trace with the
following structure:

- **Trace** — grouped by `langfuse.session.id` (= the conversation's
  `thread_id`). Title is the first user message, truncated to 80
  chars, with a `· tN` turn label and a `[deep]` suffix on
  deep-research turns. Tags carry `research_mode:*`,
  `code_language:*`, `database:*`.
- **Root observation** (`agent.request`) — the stream_chat span.
- **Node observations** (`agent.node.<name>`) — one per LangGraph
  node per turn (Coordinator → Orchestrator → Coder / SQL Agent).
- **Tool observations** (`agent.tool.<name>`) — one per LangChain tool
  invocation. `tool.success=true|false` on close.
- **LLM observations** (`gen_ai.chat`) — one per LLM round trip.
  `gen_ai.usage.input_tokens`, `output_tokens`, `cost_usd`.

**Common debugging flows:**

- *"What did user X run yesterday?"* — Langfuse UI → *Users* →
  select user → scroll conversations.
- *"Find all failing coder runs in the last day"* — Langfuse UI
  → *Tracing* → add a `level=ERROR` filter on child observations and
  scope to `agent.node.coder`.
- *"Diff two orchestrator prompts"* — once prompt management lands
  (gated on the Workstream C criterion 2 decision), right-click
  a `gen_ai.chat` observation → *Show Prompt*.
- *"Total cost per conversation"* — Langfuse rolls `gen_ai.usage.cost_usd`
  up the trace automatically; see the trace header badge.

## 4. Querying Langfuse attributes in MongoDB — dot-in-key gotcha

Langfuse's span-attribute keys contain literal dots (`langfuse.session.id`,
`langfuse.trace.name`, `langfuse.tags`). This means you **cannot** query
them with MongoDB's standard dotted-path syntax, because MongoDB
interprets the dots as nested-object navigation:

```js
// ❌ Returns zero docs — Mongo looks for attributes.langfuse → session → id
db.traces.find({"attributes.langfuse.session.id": "anonymous:abc"})
```

Use `$expr` + `$getField` to reach keys that contain literal dots:

```js
// ✅ Works — $getField treats "langfuse.session.id" as a literal key name
db.traces.find({
  "name": "agent.request",
  "$expr": {
    "$eq": [
      {"$getField": {"field": "langfuse.session.id", "input": "$attributes"}},
      "anonymous:abc"
    ]
  }
})
```

Alternative for pattern matches: regex. MongoDB can regex-match the
value of a dot-containing key if you query via `$expr` + `$regexMatch`
on the extracted field. In practice, the Langfuse UI itself is the
primary query surface for these attributes — the MongoDB route is only
useful for bulk aggregations the UI doesn't expose (e.g., counting
unique `session_id` values across all traces of a day).

## 5. Cost & privacy cautions

- **`TRACE_CAPTURE_PAYLOADS=true` is DEV ONLY by default.** Production
  traces should carry only token counts + cost, not raw prompts. A
  security review is required before flipping this on in prod — tenant
  SQL often contains PHI-adjacent data.
- **Payload truncation is per-attribute, not per-trace.** A single
  long tool output gets truncated; multiple large payloads across a
  trace compound. Watch Langfuse's ingest backlog if you enable
  payload capture under load.
- **Langfuse retention is your responsibility.** The local Docker
  setup defaults to forever retention. Before running it for > a
  week, configure `LANGFUSE_RETENTION_DAYS` or a Postgres GC job.

## 6. What this guide is NOT

- Not the Workstream C gate decision — that lives at
  `.agents/decisions/phase2-langfuse-gate.md`
  and is pending the observation window + Task 26 evaluation data.
  This guide documents how to USE Langfuse today in local dev; the
  ADR records whether we deploy it to the cluster.
