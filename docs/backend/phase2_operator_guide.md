# Phase 2 — Per-Request Coder + Orchestrator Backend Operator Guide

> **Scope:** Phase 2 Workstreams A + B share the same per-request binary toggle
> pattern. Workstream A exposes `coder_backend`; Workstream B mirrors the same
> surface for `orchestrator_backend`. Workstream C (Langfuse gate) is a decision
> doc. Workstream D (badge) rides on Phase 1 MR !4 infrastructure and needs no
> operator action.
>
> **Workstream B status note:** the orchestrator SDK path is a **prototype** —
> it lives on `feat/phase-2b-orchestrator-prototype` only, is gated by the
> per-request toggle + `ORCHESTRATOR_BACKEND` env, and is evaluated via
> `.agents/decisions/phase2-orchestrator-sdk.md`.
> Enabling it in production is a Phase 3 decision.

## 1. What it does

Two **binary, per-request** overrides, one per worker-class agent:

- `coder_backend` (Phase 2 Workstream A) — flips the coder agent between
  the LangChain path and the Phase 1 SDK path for a single chat turn.
- `orchestrator_backend` (Phase 2 Workstream B, prototype) — flips the
  orchestrator between the LangChain path and the SDK prototype for a
  single chat turn.

Callers opt in by sending the field on the `/chat/stream` request body.
Omitting a field (or sending `null`) falls back to the server's
configured default (`CODER_BACKEND` / `ORCHESTRATOR_BACKEND` env, both
default to `langchain`).

The switches are delivered by the ContextVar primitives already used by
the evaluation harness (`coder_backend_context`,
`orchestrator_backend_context`). No new settings, no restart, no hash
bucketing, no percentage ramp.

## 2. Enabling

### From the UI (primary path)

The chat composer has TWO pills next to the code-language toggle:

- **"Coder: Default" / "Coder: SDK"** (Sparkles icon) — coder override
- **"Orch: Default" / "Orch: SDK"** (Workflow icon) — orchestrator override

Click to flip each independently. Selections are session-scoped in the
`useUIStore` Zustand store — **not persisted** across refreshes, so a
reload resets to the server defaults. Intentional: prevents the toggles
from leaking into project/conversation settings where they don't belong.

When either toggle is ON and the corresponding worker runs, the agent
activity panel renders the Phase 1 `✨ SDK` badge on that worker's
pill — zero new badge code; the existing MR !4 infrastructure handles it
once the ContextVar resolves the worker to SDK.

**2x2 matrix for side-by-side evaluation:** toggle both backends
independently to exercise each cell of `(coder=LC/SDK) × (orch=LC/SDK)`
without restarting or touching env vars.

### From a direct API call (useful for CI / curl)

```bash
# Coder on SDK, orchestrator on default
curl -sS -X POST https://<host>/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"print 1+1","coder_backend":"sdk"}' \
  | grep agent_backend

# Both workers on SDK — full prototype path
curl -sS -X POST https://<host>/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"analyze the TCR data",
       "coder_backend":"sdk",
       "orchestrator_backend":"sdk"}' \
  | grep agent_backend

# Orchestrator on SDK, coder on LangChain — isolates orchestrator behavior
curl -sS -X POST https://<host>/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"plan a multi-step analysis",
       "orchestrator_backend":"sdk","coder_backend":"langchain"}'
```

Valid values for either field: `"langchain"`, `"sdk"`, or `null` /
omitted. Any other string is rejected at the pydantic boundary with
`422`.

## 3. System-wide default

Still controlled by `CODER_BACKEND` (values: `langchain` | `sdk`). A
per-request `coder_backend` override wins over this default for the request
it's attached to. To flip the system default:

```bash
# .env or secrets manifest
CODER_BACKEND=sdk
# Restart the backend pod/container for the env change to take effect.
```

## 4. Rollback

- **Per-request** — user flips the UI toggle back to "Default", or the
  caller stops sending `coder_backend` on the body. Effective immediately;
  no restart.
- **System-wide** — set `CODER_BACKEND=langchain` and restart backend pods.
  Per-request overrides still work and will still route that request to
  SDK; the default for everyone else reverts to LangChain.

## 5. Verifying the toggle in traces

Every worker node emits an `agent.node.*` span. When SDK is active for a
turn, the coder span carries `agent.backend=sdk`:

```js
// mongosh — find all SDK coder turns in the last 24h
db.traces.find({
  "spans.name": "agent.node.coder",
  "spans.attributes.agent.backend": "sdk",
  "created_at": { $gte: new Date(Date.now() - 24*60*60*1000) }
}).count()
```

And the SSE stream events for those turns carry `agent_backend: "sdk"` on
`agent_start` / `agent_end` for the Coder node, which is what drives the UI
badge.

## 6. Known issues / gotchas

- **Streaming UX delta is unchanged from Phase 1.** The SDK coder does not
  emit token-level deltas the way the LangChain coder does (LangGraph's
  `astream_events` fires on each LLM chunk; the SDK path emits one final
  message). Users may perceive a longer "empty" period before the response
  lands. See Phase 1 operator guide §8 for the same guidance.
- **`/v1` URL gotcha still applies.** The SDK path uses
  `settings.portkey_anthropic_base_url` (strips the trailing `/v1` from
  `PORTKEY_BASE_URL`). If you're standing up a new environment, make sure
  `PORTKEY_BASE_URL` is the versioned Portkey root (with `/v1`), not the
  bare gateway root. LangChain wants the versioned value, SDK strips it.
- **Refresh resets the toggle.** Intentional — prevents the override from
  leaking into a project or conversation doc in Mongo. If a user wants SDK
  for every new chat, they re-toggle; or the operator flips the system
  default.

## 6a. Orchestrator SDK tool-exposure mode (prototype-only)

When the orchestrator is running on the SDK (either via the per-request
toggle or `ORCHESTRATOR_BACKEND=sdk`), a further env flag controls how
it exposes tools:

- `ORCHESTRATOR_SDK_TOOL_MODE=delegated` (default, recommended) — the
  orchestrator has NO direct MCP tools. It can only call `TodoWrite`
  and delegate to the `coder` / `sql_agent`
  `AgentDefinition` sub-agents. All actual tool calls happen inside a
  sub-agent's isolated conversation. **Use this for the Workstream B
  A/B evaluation** — it's the architecturally honest comparison with
  the LangChain path.
- `ORCHESTRATOR_SDK_TOOL_MODE=flat` — the orchestrator sees all 14 MCP
  tools directly AND the sub-agents. Sonnet usually picks direct calls
  on simple queries; faster per-turn, less context-efficient on
  multi-step plans. Useful as a supplementary data point: "if
  delegation overhead turns out to cost too much, does flat still beat
  LangChain?"

Invalid values fall back to `delegated` with a warning. The setting
only affects the SDK orchestrator; it's ignored when the orchestrator
runs on LangChain.

## 7. Debugging with Langfuse (local dev)

Workstream C ships the groundwork for using Langfuse as a trace UI so
incident-response archaeology stops meaning "write `mongosh` queries
by hand". Deployment of Langfuse to the cluster is gated on the Phase 2
observation window — see
`.agents/decisions/phase2-langfuse-gate.md`.
For **local development** right now, here's how to use it.

### 7a. Stand up Langfuse locally

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

### 7b. Wire the genomechat backend to Langfuse

In `backend/.env`:

```bash
LANGFUSE_ENABLED=true
# Container → host Langfuse. host.containers.internal is Podman's
# host-gateway alias (== host.docker.internal on Docker Desktop).
LANGFUSE_OTLP_ENDPOINT=http://host.containers.internal:3000/api/public/otel/v1/traces
LANGFUSE_AUTH_HEADER=<the base64 blob from §7a>

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

### 7c. Navigate a trace in the Langfuse UI

A single `/chat/stream` request produces one Langfuse trace with the
following structure:

- **Trace** — grouped by `langfuse.session.id` (= the conversation's
  `thread_id`). Title is the first user message, truncated to 80
  chars. Tags carry `research_mode:*`, `code_language:*`,
  `database:*`, `coder_backend:*`, `orchestrator_backend:*`.
- **Root observation** (`agent.request`) — the stream_chat span.
- **Node observations** (`agent.node.<name>`) — one per LangGraph
  node per turn (Coordinator → Orchestrator → Coder / SQL Agent).
  Carry `agent.backend=langchain|sdk` so you can filter
  to just the SDK-path turns.
- **Tool observations** (`agent.tool.<name>`) — one per MCP tool /
  LangChain tool invocation. `tool.success=true|false` on close.
- **LLM observations** (`gen_ai.chat`) — one per LLM round trip.
  `gen_ai.usage.input_tokens`, `output_tokens`, `cost_usd`.

**Common debugging flows:**

- *"What did user X run yesterday?"* — Langfuse UI → *Users* →
  select user → scroll conversations.
- *"Find all failing SDK coder runs in the last day"* — Langfuse UI
  → *Tracing* → filter `tags` contains `coder_backend:sdk` + add a
  `level=ERROR` filter on child observations.
- *"Diff two orchestrator prompts"* — once prompt management lands
  (gated on the Workstream C criterion 2 decision), right-click
  a `gen_ai.chat` observation → *Show Prompt*.
- *"Total cost per conversation"* — Langfuse rolls `gen_ai.usage.cost_usd`
  up the trace automatically; see the trace header badge.

### 7d. Querying Langfuse attributes in MongoDB — dot-in-key gotcha

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

### 7e. Cost & privacy cautions

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

## 8. What this guide is NOT

- Not a canary rollout guide. Phase 2's original spec was a percentage
  canary (5% → 25% → 50% → 100%); the 2026-05-11 scope revision replaced it
  with a per-request binary toggle. There's no ramp schedule, no auto-
  rollback tripwire, no `canary_alerts` collection. See
  `.agents/decisions/phase2-per-request-backend.md` for rationale.
- Not the Workstream C gate decision — that lives at
  `.agents/decisions/phase2-langfuse-gate.md`
  and is pending the observation window + Task 26 evaluation data.
  This guide §7 documents how to USE Langfuse today in local dev; the
  ADR records whether we deploy it to the cluster.
- Not the authoritative Workstream B ADR — that lives at
  `.agents/decisions/phase2-orchestrator-sdk.md`
  and records the evaluation plan + go/no-go call. This guide only
  documents the operator surface (the `orchestrator_backend` request
  field, the `ORCHESTRATOR_BACKEND` env, and the
  `ORCHESTRATOR_SDK_TOOL_MODE` env).
