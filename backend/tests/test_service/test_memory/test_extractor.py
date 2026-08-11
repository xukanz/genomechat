"""Unit tests for src.service.memory.extractor.

Strategy: mock (a) the LLM call so we control the JSON output, (b) the
embedder so we return deterministic vectors, and (c) the MongoDB client via
mongomock so we can assert what was inserted.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _db_name() -> str:
    from src.config.settings import settings

    return settings.mongodb_db_name


@pytest.fixture
def _mock_mongo(monkeypatch, mongomock_client):
    from src.service.memory import extractor as ext_mod

    monkeypatch.setattr(ext_mod, "get_mongodb_client", lambda: mongomock_client)
    return mongomock_client


@pytest.fixture
def _mock_embedder(monkeypatch):
    """Deterministic 4-dim embedder. Returns identical vector per fact so dedup is testable."""
    from src.service.memory import extractor as ext_mod

    class _Emb:
        async def aembed_documents(self, texts):
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

        async def aembed_query(self, text):
            return [1.0, 0.0, 0.0, 0.0]

    monkeypatch.setattr(ext_mod, "get_embedder", lambda: _Emb())
    return _Emb()


def _llm_mock(json_response: str):
    mock = AsyncMock()
    mock.ainvoke = AsyncMock(return_value=SimpleNamespace(content=json_response))
    return mock


@pytest.mark.asyncio
async def test_extractor_inserts_memory_and_redacts_before_llm(
    _mock_mongo, _mock_embedder, monkeypatch, in_memory_span_exporter
):
    from src.service.memory import extractor as ext_mod

    seen_prompts: list[str] = []

    async def _capture_ainvoke(prompt):
        seen_prompts.append(prompt)
        return SimpleNamespace(
            content='{"memories": [{"fact": "User prefers violin plots for TMB distributions.", "importance": 0.7, "domain": "user-preference"}]}'
        )

    llm = MagicMock()
    llm.ainvoke = _capture_ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    result = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id="p1",
        database_id="clinvar",
        user_message="My email is jane@example.com; show me PD-L1 positive patients",
        assistant_message="Here are the results (patient_id 987654 was excluded).",
    )

    assert len(result) == 1
    mem = result[0]
    assert mem.user_id == "alice"
    assert mem.domain == "user-preference"
    assert mem.importance == 0.7
    assert len(mem.embedding) == 4

    # Verify the prompt Haiku saw had redactions applied (no raw email, no raw patient_id)
    assert len(seen_prompts) == 1
    prompt_text = seen_prompts[0]
    assert "jane@example.com" not in prompt_text
    assert "987654" not in prompt_text
    assert "[REDACTED:email]" in prompt_text
    assert "[REDACTED:patient_id_like]" in prompt_text

    # Verify MongoDB state
    coll = _mock_mongo[_db_name()]["research_memories"]
    assert coll.count_documents({"user_id": "alice"}) == 1
    audit = _mock_mongo[_db_name()]["memory_redaction_log"]
    audit_rows = list(audit.find())
    assert len(audit_rows) == 1
    # Patterns recorded but no raw values
    pattern_names = {h["pattern_name"] for h in audit_rows[0]["hits"]}
    assert "email" in pattern_names
    assert "patient_id_like" in pattern_names
    # No raw value anywhere in the audit row
    assert "jane@example.com" not in str(audit_rows[0])

    # Span emitted with agent.thread_id propagated
    spans = in_memory_span_exporter.get_finished_spans()
    node_span = next(s for s in spans if s.name == "agent.node.memory_extractor")
    assert node_span.attributes["agent.thread_id"] == "alice:c1"


@pytest.mark.asyncio
async def test_extractor_drops_duplicates(_mock_mongo, _mock_embedder, monkeypatch):
    """Second call with the same fact must dedup against the first."""
    from src.service.memory import extractor as ext_mod

    llm_response = (
        '{"memories": [{"fact": "User wants counts grouped by species.", '
        '"importance": 0.6, "domain": "query-pattern"}]}'
    )

    async def _ainvoke(_):
        return SimpleNamespace(content=llm_response)

    llm = MagicMock()
    llm.ainvoke = _ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    first = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id=None,
        database_id="clinvar",
        user_message="Count by species?",
        assistant_message="Human ~82%, mouse ~18%.",
    )
    assert len(first) == 1

    second = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c2",
        user_id="alice",
        project_id=None,
        database_id="clinvar",
        user_message="Another count by species?",
        assistant_message="Same distribution.",
    )
    assert second == []  # duplicate dropped

    coll = _mock_mongo[_db_name()]["research_memories"]
    assert coll.count_documents({"user_id": "alice"}) == 1


@pytest.mark.asyncio
async def test_extractor_handles_malformed_json_without_crashing(
    _mock_mongo, _mock_embedder, monkeypatch
):
    from src.service.memory import extractor as ext_mod

    async def _ainvoke(_):
        return SimpleNamespace(content="not valid json at all")

    llm = MagicMock()
    llm.ainvoke = _ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    result = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id=None,
        database_id=None,
        user_message="hi",
        assistant_message="hello",
    )
    assert result == []


@pytest.mark.asyncio
async def test_extractor_strips_code_fences_from_llm_output(
    _mock_mongo, _mock_embedder, monkeypatch
):
    """Haiku sometimes wraps JSON in ```json fences despite the prompt."""
    from src.service.memory import extractor as ext_mod

    fenced = (
        '```json\n{"memories": [{"fact": "X", "importance": 0.5, "domain": "query-pattern"}]}\n```'
    )

    async def _ainvoke(_):
        return SimpleNamespace(content=fenced)

    llm = MagicMock()
    llm.ainvoke = _ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    result = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id=None,
        database_id=None,
        user_message="hi",
        assistant_message="hello",
    )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_extractor_drops_candidates_with_invalid_domain(
    _mock_mongo, _mock_embedder, monkeypatch
):
    from src.service.memory import extractor as ext_mod

    async def _ainvoke(_):
        return SimpleNamespace(
            content=(
                '{"memories": ['
                '{"fact": "good one", "importance": 0.5, "domain": "user-preference"},'
                '{"fact": "bad", "importance": 0.5, "domain": "not-a-domain"}]}'
            )
        )

    llm = MagicMock()
    llm.ainvoke = _ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    result = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id=None,
        database_id=None,
        user_message="hi",
        assistant_message="hello",
    )
    assert len(result) == 1
    assert result[0].fact == "good one"


@pytest.mark.asyncio
async def test_parse_candidates_caps_at_five():
    from src.service.memory.extractor import _parse_candidates

    raw = (
        '{"memories": ['
        + ",".join(
            f'{{"fact": "f{i}", "importance": 0.5, "domain": "query-pattern"}}' for i in range(10)
        )
        + "]}"
    )
    candidates = _parse_candidates(raw)
    assert len(candidates) == 5


def test_cosine_zero_vector_returns_zero():
    from src.service.memory.extractor import _cosine

    assert _cosine([0, 0, 0], [1, 1, 1]) == 0.0
    assert _cosine([1, 0], [1, 0]) == 1.0


# ---------------------------------------------------------------------------
# Codex-flagged regression: extractor used `model_dump(mode="json")` which
# stringified datetimes. This broke the TTL index on `updated_at` and the
# recency retrieval layer. These two tests guard the fix end-to-end.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extractor_persists_datetimes_as_bson_not_iso_strings(
    _mock_mongo, _mock_embedder, monkeypatch
):
    """The stored doc must keep real `datetime` objects so the TTL index fires
    and the retriever's recency filter ($gte datetime_cutoff) matches rows.
    """
    from datetime import datetime

    from src.service.memory import extractor as ext_mod

    async def _ainvoke(_):
        return SimpleNamespace(
            content='{"memories": [{"fact": "x", "importance": 0.5, "domain": "query-pattern"}]}'
        )

    llm = MagicMock()
    llm.ainvoke = _ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id=None,
        database_id=None,
        user_message="hi",
        assistant_message="hello",
    )

    doc = _mock_mongo[_db_name()]["research_memories"].find_one({"user_id": "alice"})
    assert doc is not None
    # The load-bearing assertion: BSON datetime, not an ISO string. MongoDB's
    # TTL index and `$gte: datetime_cutoff` queries both require this type.
    # (Real MongoDB with default `tz_aware=False` returns naive datetimes on
    # read, so we don't assert tzinfo — it's an artifact of the round trip.)
    assert isinstance(doc["created_at"], datetime), (
        f"created_at must be a datetime, got {type(doc['created_at']).__name__}"
    )
    assert isinstance(doc["updated_at"], datetime), (
        f"updated_at must be a datetime, got {type(doc['updated_at']).__name__}"
    )
    assert not isinstance(doc["created_at"], str)
    assert not isinstance(doc["updated_at"], str)


@pytest.mark.asyncio
async def test_extracted_memory_surfaces_through_recent_important_layer(
    _mock_mongo, _mock_embedder, monkeypatch
):
    """Regression for the extractor→retriever handoff. Under ISO strings, the
    retriever's {'$gte': datetime_cutoff} filter drops every extracted memory.
    With real datetimes, the memory surfaces via the recent-important layer.
    """
    from src.service.memory import extractor as ext_mod
    from src.service.memory import retriever as ret_mod

    # Extractor + retriever must share the same mongomock client to exercise
    # the full round trip.
    monkeypatch.setattr(ret_mod, "get_mongodb_client", lambda: _mock_mongo)
    monkeypatch.setattr(ret_mod, "get_embedder", lambda: _mock_embedder)

    async def _ainvoke(_):
        return SimpleNamespace(
            content=(
                '{"memories": [{"fact": "prefers violin plots for TMB", '
                '"importance": 0.95, "domain": "user-preference"}]}'
            )
        )

    llm = MagicMock()
    llm.ainvoke = _ainvoke
    monkeypatch.setattr(ext_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    inserted = await ext_mod.extract_memories_for_turn(
        thread_id="alice:c1",
        user_id="alice",
        project_id=None,
        database_id=None,
        user_message="plot this",
        assistant_message="here you go",
    )
    assert len(inserted) == 1

    results = await ret_mod.retrieve_memories(query="violin plots", user_id="alice")
    matching = [r for r in results if r.memory.memory_id == inserted[0].memory_id]
    assert matching, "extracted memory did not surface through the retriever"
    assert matching[0].source in {"recent", "semantic"}
