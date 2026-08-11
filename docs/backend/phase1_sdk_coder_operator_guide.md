# Phase 1 SDK Coder — Operator Guide

**Status:** Phase 1 implementation shipped (see `.agents/plans/phase-1-claude-agent-sdk-coder-swap.md`)
**Default backend:** `langchain` — SDK path is opt-in via a single env var
**Rollback time:** ≤ 60s (env var flip + pod restart)

This document covers: enabling the SDK coder, verifying it's live, rolling back, and the known operational considerations. For implementation context see the plan; for the Phase 0 span contract see [`phase0_phase1_contract.md`](phase0_phase1_contract.md).

---

## 1. Enabling the SDK coder

Set in the service's environment (via env var, Compose `.env`, or Vault Secrets):

```bash
CODER_BACKEND=sdk
```

No other env var changes are strictly required — the Phase 0 `PORTKEY_BEDROCK_API_KEY` / `PORTKEY_BEDROCK_SLUG` / `PORTKEY_BASE_URL` values already populated for Haiku also work for Sonnet on the SDK path.

> **`PORTKEY_BASE_URL` normalization note** — keep `PORTKEY_BASE_URL` set to the same `/v1`-suffixed value the LangChain path uses (e.g. `https://your-gateway.example.com/v1`). The SDK path consumes it via `settings.portkey_anthropic_base_url`, which strips the trailing `/v1` before passing it to the bundled Claude Agent SDK CLI. This is required because the CLI appends `/v1/messages` itself — a `/v1`-suffixed base produces a broken `/v1/v1/messages` path that Portkey forwards to Bedrock as an AWS Coral `UnknownOperationException` (HTTP 200 with an unparseable body). No operator action required; just don't change `PORTKEY_BASE_URL` to drop the `/v1` manually, or the LangChain path breaks.

Optional Phase 1 tunables (all have safe defaults in [`backend/src/config/settings.py`](../../backend/src/config/settings.py)):

| Env var | Default | Purpose |
|---|---|---|
| `SDK_TRANSCRIPT_ROOT` | `/tmp/genomechat-sdk` | Anchor dir for per-request transcripts (see §4) |
| `SDK_ORPHAN_CLEANUP_MAX_AGE_SECONDS` | `3600` | Age threshold for orphan sweep |
| `SDK_ORPHAN_CLEANUP_INTERVAL_MINUTES` | `30` | Sweep cadence |
| `CODER_SDK_MAX_TURNS` | `20` | Max tool-use turns per `query()` call |
| `CODER_SDK_PERMISSION_MODE` | `bypassPermissions` | SDK permission mode — **production must stay on `bypassPermissions`** |
| `CODER_SDK_MODEL` | `us.anthropic.claude-sonnet-4-6` | Bedrock-flavored model ID (short aliases rejected by Portkey) |
| `INSTANCE_ID` / `POD_NAME` / `HOSTNAME` | auto-resolved | Per-container identifier for transcript isolation |

Restart the backend container / pod for `CODER_BACKEND` changes to take effect. The lifespan hook picks up the change on next start.

## 2. Verifying the SDK path is live

**Check the active backend via /internal/health/agent-backends:**

```bash
curl -s -H "Authorization: Bearer $INTERNAL_JWT" https://<host>/internal/health/agent-backends
# {"coder": "sdk", "orchestrator": "langchain"}
```

**Trigger a coder-style request and inspect the trace:**

```bash
curl -s -X POST https://<host>/chat \
  -H "Authorization: Bearer $USER_JWT" \
  -H "Content-Type: application/json" \
  -d '{"message":"Run python: print(sum(range(10)))","thread_id":"test-phase1-verify"}'
```

Then query the `/internal/traces` endpoint for that `thread_id` and confirm:

- An `agent.node.coder` span exists
- Its `attributes.agent.backend == "sdk"`
- A child `gen_ai.chat` span with `gen_ai.request.model == "us.anthropic.claude-sonnet-4-6"` and non-zero `gen_ai.usage.input_tokens`
- A child `agent.tool.execute_code` span (or similar MCP tool)

Direct MongoDB check (dev only):

```js
db.traces.find({
  name: "agent.node.coder",
  "attributes.agent.backend": "sdk",
  thread_id: /test-phase1-verify/,
}).sort({start_time: -1}).limit(1).pretty()
```

## 3. Rollback

Flipping the flag is instant and scoped to the coder worker only — the orchestrator, SQL agent, and coordinator remain on LangChain throughout.

```bash
# Via env var (Compose / local)
CODER_BACKEND=langchain
docker compose restart backend

# Kubernetes
kubectl set env deploy/genomechat-backend CODER_BACKEND=langchain
# Rollout is automatic; new pods come up with the LangChain path
```

New requests land on LangChain within ~60s of pod restart. In-flight SDK requests complete on the old path — no mid-turn migration is attempted. Checkpoints are backend-agnostic, so conversation continuity is preserved across the flip.

## 4. Transcript storage — where the bytes actually live

**Important finding from Phase 1 Spike 2:** the Claude Agent SDK does **not** write its transcript JSONLs into the `cwd` directory we pass in `ClaudeAgentOptions`. It writes to:

```
~/.claude/projects/<sanitized-cwd-path>/<session_id>.jsonl
```

where `<sanitized-cwd-path>` is the absolute `cwd` with non-alphanumeric characters replaced by `-`. The cwd we pass — `${SDK_TRANSCRIPT_ROOT}/${INSTANCE_ID}/${thread_id}/${request_id}/` — is used only as a unique namespace anchor so every concurrent request gets its own `~/.claude/projects/` subdirectory.

Implications for operators:

- **The home volume (`$HOME/.claude/projects/`) grows with SDK traffic.** Each completed request's dir is swept in a `finally` block, but crashed requests can leak. The periodic `cleanup_orphans()` job (APScheduler, 30-min cadence) sweeps stale entries. Make sure `$HOME` is writable and has enough free space for bursts of concurrent requests (~tens of KB per transcript).
- **Do not mount `${SDK_TRANSCRIPT_ROOT}` expecting to see transcripts there.** It will only contain the empty anchor directories.
- **For forensics / replay**, the JSONLs live under `~/.claude/projects/<project_key>/`. Deriving the key from a thread_id is nontrivial (the SDK sanitizes the full `cwd`); the safer path is to stream `SystemMessage.cwd` on capture.

## 5. Cost, latency, streaming UX

- **Model:** `us.anthropic.claude-sonnet-4-6` (richer than Phase 0's Haiku smoke).
- **Per-call cost in Spike 1:** `$0.0292` on a single tool-use round-trip (cache-creation dominant on first turn; amortizes on warm sessions).
- **Latency:** Spike 1 showed ~13s for one tool_use turn end-to-end. Production latency on real coder workloads will vary with tool-call count and Portkey queueing.
- **Streaming UX delta (known):** The SDK subprocess's internal token / tool_use stream does **not** propagate through LangGraph's `astream_events`. Users on SDK-backed coder see the coder node appear to pause for the full turn then dump a single block; LangChain-path coder streams tokens as they arrive. This is MVP-acceptable; revisit in Phase 2 if user feedback demands it.

## 6. Governance (Portkey)

Every SDK LLM call routes through Portkey Bedrock exactly like the LangChain path — governance, rate limits, and cost attribution are preserved.

**Auth mechanism:** `ANTHROPIC_AUTH_TOKEN` header (→ `Authorization: Bearer <key>`) + `ANTHROPIC_CUSTOM_HEADERS=x-portkey-slug: <slug>`. `ANTHROPIC_API_KEY` MUST remain blank — setting it non-empty causes the bundled Anthropic CLI to send `x-api-key` which Portkey rejects with HTTP 401. A runtime assertion in `coder_sdk.py` blocks any future env refactor that would silently re-enable this.

**Verifying attribution in Portkey:** sample logs should show requests with:
- Matching `x-portkey-slug` header
- Correct model ID (`us.anthropic.claude-sonnet-4-6`)
- User / project context as configured by the platform's Portkey headers

## 7. Follow-up evaluation phase

The harness SDK branch is dormant-ready — running a comparison is a matter of populating the consented-user roster (`EVAL_CONSENTED_USER_IDS` env var, already shipped in Phase 0.5) and executing:

```bash
# 1. Populate dataset once consent roster is live
cd backend && EVAL_CONSENTED_USER_IDS=<user1>,<user2> uv run python -m evaluation.cli bootstrap \
  --out evaluation/datasets/baseline.jsonl

# 2. LangChain baseline
cd backend && CODER_BACKEND=langchain uv run python -m evaluation.cli run \
  --dataset evaluation/datasets/baseline.jsonl \
  --backend langchain \
  --out evaluation/baselines/v1_langchain_baseline.jsonl \
  --concurrency 4

# 3. SDK candidate (same dataset, mandatory)
cd backend && CODER_BACKEND=sdk uv run python -m evaluation.cli run \
  --dataset evaluation/datasets/baseline.jsonl \
  --backend sdk \
  --out evaluation/baselines/v2_sdk_candidate.jsonl \
  --concurrency 4
```

No coder-path code changes are required to enable evaluation — the SDK branch ships in Phase 1 and waits.

## 8. Known issues

- **Thinking blocks on Sonnet.** `AssistantMessage.content` routinely contains a `ThinkingBlock` before the `ToolUseBlock` or `TextBlock`. `coder_sdk._extract_final_text` pulls the final `TextBlock`; thinking content is never surfaced (by design).
- **`ResultMessage.result` can be empty.** On `max_turns` reached or unusual stops, `.result` is empty and we fall back to the last `AssistantMessage` text blocks — see `_extract_final_text`.
- **gen_ai.chat span is one per coder turn.** Even if the SDK made multiple internal tool-use cycles within a single `query()`, we emit one `gen_ai.chat` span aggregating usage. Per-cycle granularity would require consuming intermediate `AssistantMessage.usage` values; not implemented in Phase 1 MVP.
- **`~/.claude/projects/` cleanup relies on the SDK's `project_key_for_directory` being importable.** We use the SDK's own function from `_internal.sessions`; if a future SDK release renames it, we have a test (`test_transcript_projects_dir_matches_sdk_encoding`) that fails loudly and a local fallback encoder that preserves isolation (but not always cleanup completeness for very long paths).

## 9. Runbook snippets

**Count SDK vs LangChain coder traffic last 24h:**

```js
db.traces.aggregate([
  {$match: {name: "agent.node.coder", start_time: {$gt: new Date(Date.now() - 24*3600_000)}}},
  {$group: {_id: "$attributes.agent.backend", n: {$sum: 1}}},
])
```

**Spot-check per-call cost distribution (SDK path):**

```js
db.traces.aggregate([
  {$match: {name: "gen_ai.chat", start_time: {$gt: new Date(Date.now() - 3600_000)}}},
  {$group: {_id: null, p50: {$percentile: {input: "$attributes.gen_ai.usage.cost_usd", p: [0.5], method: "approximate"}}, p95: {$percentile: {input: "$attributes.gen_ai.usage.cost_usd", p: [0.95], method: "approximate"}}, n: {$sum: 1}}},
])
```

**Re-run connectivity spikes any time** (cheap, no side effects):

```bash
cd backend
uv run python scripts/spike_sdk_tool_use.py                       # ~15s, ~$0.03
uv run python scripts/spike_sdk_transcript_isolation.py --n 50    # ~35s, ~$0.10
uv run python scripts/audit_phase1_spans.py                        # ~1s, free
```

---

_Last updated: 2026-05-07 as part of Phase 1 SDK Coder Swap. Maintain alongside plan + contract._
