# Phase 0.5 Memory Governance Guide

## Overview

Phase 0.5 adds a per-turn memory-extraction pipeline that persists structured
facts to `research_memories` and derived summaries to `memory_insights`. The
pipeline is pilot-gated and default-off: flipping `MEMORY_EXTRACTION_ENABLED=true`
without also populating `MEMORY_PILOT_USER_IDS` is a no-op — extraction fires
only for users in the allowlist.

This guide covers operator procedures that live outside the code: pilot
enrollment, redaction audit, hard-delete until the Phase 4 API ships.

## Pilot enrollment checklist

Before adding a user to `MEMORY_PILOT_USER_IDS`:

- [ ] User sent explicit opt-in email; reply archived
- [ ] Data Processing Agreement section §7.4 signed (see Risk 7 in PRD)
- [ ] Infosec approval recorded (create a signoff tracker when pilot enrollment begins — deferred indefinitely as of 2026-05-06)
- [ ] Pilot user count still ≤ 5 (or explicit exemption from infosec)
- [ ] Retention window (`MEMORY_TTL_DAYS`) matches the DPA term — default 180
- [ ] User record updated in staging or production `users` collection
- [ ] First 10 turns reviewed manually by platform lead via `/internal/memory`

Any item skipped leaves compliance exposure. Do NOT backfill.

## Enabling in an environment

Minimum env for pilot extraction:

```bash
MEMORY_EXTRACTION_ENABLED=true
MEMORY_PILOT_USER_IDS=user-id-1,user-id-2
MEMORY_CONSOLIDATION_ENABLED=true        # optional; recommended
MEMORY_CONSOLIDATION_INTERVAL_MINUTES=30 # default; drop to 1-2 for staging
```

Required Phase 0 prerequisites still apply:

```bash
OTEL_ENABLED=true
TRACE_STORAGE_ENABLED=true
INTERNAL_OBSERVABILITY_ENABLED=true
```

## Redaction pattern list (as of Phase 0.5)

Every ingestion runs through [`redaction.py`](../../backend/src/service/memory/redaction.py).
Current patterns:

| Pattern | Example match |
|---|---|
| aws_access_key | `AKIA` + 16 uppercase alphanumerics |
| anthropic_key | `sk-ant-api03-...` |
| openai_key | `sk-abc123...` (32+ chars) |
| jwt | `eyJ<header>.<payload>.<sig>` |
| private_key | `-----BEGIN ... PRIVATE KEY-----` blocks |
| email | `jane.doe@example.com` |
| us_phone | `415-555-0199`, `+1 415 555 0199` |
| ssn | `123-45-6789` |
| mrn_like | `MRN: 123456`, `mrn#9876543210` |
| patient_id_like | `patient_id 987654` |

What does NOT get caught today (known gaps — patch in follow-up tickets as
we learn from pilot traffic):

- Free-form SSNs without hyphens (e.g. `123456789`)
- International phone numbers outside the US format
- DoB strings (`1985-03-14`) — high false-positive risk against trial dates
- Cohort codes under 6 digits

When you observe a gap, add the pattern + test case in
[`test_redaction.py`](../../backend/tests/test_service/test_memory/test_redaction.py)
and bump the `redaction.py` version comment. Do NOT loosen existing patterns.

## Viewing what was redacted (audit only)

Every redaction event writes one row to `memory_redaction_log`:

```javascript
// mongosh
db.memory_redaction_log.find({user_id: "pilot-user-id"}).sort({timestamp: -1}).limit(10)
```

The row stores `pattern_name` + `span` in the *original* text (the text
itself is never persisted). A reviewer can reconstruct the match by
re-running the pattern against a live turn — but once the turn is
completed, the raw string is gone.

## Hard-delete procedure (Phase 0.5 — manual)

The Phase 4 API will wrap this. Until then, infosec-initiated deletes
run via mongosh with an audit-log entry:

```javascript
// 1. Identify the user
const USER = "pilot-user-id";

// 2. Log the deletion with business justification
db.observability_access_log.insertOne({
  caller_user_id: "<grantor>",
  caller_email: "<grantor>@example.com",
  target_tenant: USER,
  scopes_used: ["memory:admin:delete"],
  path: "manual:hard_delete",
  query: {reason: "<DPA withdrawal / incident #NNNN / pilot exit>"},
  row_count: 0,
  response_status: 200,
  timestamp: new Date(),
});

// 3. Hard delete
db.research_memories.deleteMany({user_id: USER});
db.memory_insights.deleteMany({user_id: USER});
db.memory_redaction_log.deleteMany({user_id: USER});

// 4. Confirm counts
print("memories:", db.research_memories.countDocuments({user_id: USER}));
print("insights:", db.memory_insights.countDocuments({user_id: USER}));
print("redaction rows:", db.memory_redaction_log.countDocuments({user_id: USER}));
```

Every hard-delete requires infosec confirmation and is reviewed in the same
quarterly cadence as `traces:admin:cross-tenant` grants.

## Rollback

To stop extraction entirely without touching data:

```bash
MEMORY_EXTRACTION_ENABLED=false
MEMORY_CONSOLIDATION_ENABLED=false
# Restart backend
```

Existing memories remain in MongoDB. Deletion is a governed procedure, not
an automatic rollback step — document the decision in the access log.

Full emergency rollback:

```bash
MEMORY_EXTRACTION_ENABLED=false
MEMORY_CONSOLIDATION_ENABLED=false
INTERNAL_OBSERVABILITY_ENABLED=false    # also kills /internal/memory
# Restart backend
```

## Atlas Vector Search entitlement

Phase 0.5 defaults `MEMORY_ATLAS_VECTOR_SEARCH_ENABLED=true`. If your
MongoDB cluster does not have Atlas Search entitled, the startup log will
contain:

```
ensure_indexes: Atlas $vectorSearch unavailable — falling back to brute-force cosine retrieval
```

Fallback works — the retriever and dedup logic each detect missing search
indexes and switch to in-process cosine. Performance degrades linearly with
per-user memory count, which is fine at pilot scale (≤ 5 users, each with
hundreds of memories). Flip the flag off if you want to skip the failed
startup command:

```bash
MEMORY_ATLAS_VECTOR_SEARCH_ENABLED=false
```

Request entitlement before broad rollout.

## /internal/memory endpoints

Wired behind `INTERNAL_OBSERVABILITY_ENABLED=true`:

```bash
# Own memories
curl -s "http://localhost:8000/internal/memory" \
  -H "Authorization: Bearer $JWT" | jq .

# Retrieval preview
curl -s "http://localhost:8000/internal/memory?query=PD-L1" \
  -H "Authorization: Bearer $JWT" | jq .

# Manual consolidation (own)
curl -s -X POST "http://localhost:8000/internal/memory/consolidate" \
  -H "Authorization: Bearer $JWT"

# Admin cross-tenant (requires memory:admin scope)
curl -s "http://localhost:8000/internal/memory?user_id=other-user" \
  -H "Authorization: Bearer $ADMIN_JWT"
```

Embeddings are never returned — the response projection drops them by design.

## Granting `memory:admin` scope

Same procedure as `traces:admin:cross-tenant` (see Phase 0 guide):

```javascript
db.users.updateOne(
  {id: "<user_id>"},
  {$addToSet: {scopes: "memory:admin"}}
);

db.observability_access_log.insertOne({
  caller_user_id: "<grantor_user_id>",
  caller_email: "<grantor_email>",
  target_tenant: "<user_id>",
  scopes_used: ["admin:grant"],
  path: "/internal/admin/scope-grant",
  query: {scope: "memory:admin", reason: "pilot oversight"},
  row_count: 1,
  response_status: 200,
  timestamp: new Date()
});
```

Revocation: `$pull` instead of `$addToSet` and an `admin:revoke` audit row.

## Out of scope for Phase 0.5

These will be added in later phases; tracked in the Data Governance
Hardening backlog (see PRD §14 Risk 7):

- Consent UI — pilot enrollment is via email + settings allowlist only
- Hard-delete API endpoint — Phase 4 deliverable
- Per-turn PHI extraction toggle — ingestion-level filter only today
- Relevance feedback loop — Phase 3
- Memory surfacing to end users — Phase 3+
- Cross-project memory — Phase 3+
