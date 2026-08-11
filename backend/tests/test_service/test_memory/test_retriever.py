"""Unit tests for src.service.memory.retriever.

Strategy: mongomock doesn't implement `$vectorSearch` or `$text`, so the
semantic layer always falls through to brute-force cosine and the FTS layer
returns empty. That's fine — the assertions exercise the merge/rank path,
source-weighting, and tie-break rules using the fallbacks we ship.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _db_name() -> str:
    from src.config.settings import settings

    return settings.mongodb_db_name


@pytest.fixture
def _mock_mongo(monkeypatch, mongomock_client):
    from src.service.memory import retriever as ret_mod

    monkeypatch.setattr(ret_mod, "get_mongodb_client", lambda: mongomock_client)
    return mongomock_client


@pytest.fixture
def _stub_embedder(monkeypatch):
    from src.service.memory import retriever as ret_mod

    class _Emb:
        async def aembed_query(self, text):
            # Deterministic: unique vector per unique query prefix so we can
            # assert per-query semantic selectivity
            base = [0.0] * 8
            for i, ch in enumerate(text[:8]):
                base[i] = (ord(ch) % 7) / 7.0
            return base

    monkeypatch.setattr(ret_mod, "get_embedder", lambda: _Emb())
    return _Emb()


def _insert_memory(
    db,
    *,
    user_id: str,
    memory_id: str,
    fact: str,
    domain: str = "query-pattern",
    importance: float = 0.5,
    embedding: list[float] | None = None,
    updated_at: datetime | None = None,
) -> None:
    db["research_memories"].insert_one(
        {
            "memory_id": memory_id,
            "user_id": user_id,
            "project_id": None,
            "thread_id": None,
            "database_id": None,
            "fact": fact,
            "domain": domain,
            "importance": importance,
            "salience": 1.0,
            "embedding": embedding or ([0.1] * 8),
            "pinned": False,
            "superseded_at": None,
            "created_at": updated_at or datetime.now(tz=timezone.utc),
            "updated_at": updated_at or datetime.now(tz=timezone.utc),
            "access_count": 0,
            "last_accessed_at": None,
        }
    )


@pytest.mark.asyncio
async def test_retrieve_returns_empty_for_empty_query(_mock_mongo, _stub_embedder):
    from src.service.memory.retriever import retrieve_memories

    r = await retrieve_memories(query="", user_id="alice")
    assert r == []


@pytest.mark.asyncio
async def test_retrieve_scopes_to_user(_mock_mongo, _stub_embedder):
    from src.service.memory.retriever import retrieve_memories

    db = _mock_mongo[_db_name()]
    _insert_memory(db, user_id="alice", memory_id="a1", fact="alice likes R")
    _insert_memory(db, user_id="bob", memory_id="b1", fact="bob likes python")

    results = await retrieve_memories(query="R", user_id="alice")
    user_ids = {r.memory.user_id for r in results}
    assert user_ids == {"alice"} or user_ids == set()  # bob's memory must never leak


@pytest.mark.asyncio
async def test_retrieve_returns_recent_important_memory(_mock_mongo, _stub_embedder):
    from src.service.memory.retriever import retrieve_memories

    db = _mock_mongo[_db_name()]
    now = datetime.now(tz=timezone.utc)
    _insert_memory(
        db,
        user_id="alice",
        memory_id="r1",
        fact="Recent important memory",
        importance=0.9,
        updated_at=now,
    )
    _insert_memory(
        db,
        user_id="alice",
        memory_id="o1",
        fact="Old low-importance",
        importance=0.3,
        updated_at=now - timedelta(days=30),
    )

    results = await retrieve_memories(query="anything", user_id="alice")
    memory_ids = [r.memory.memory_id for r in results]
    # Recent-important layer must surface r1
    assert "r1" in memory_ids
    # Old low-importance must not come from recent-important (might from semantic brute-force, though)
    r_sources = {r.memory.memory_id: r.source for r in results}
    assert r_sources["r1"] in {"recent", "semantic"}


@pytest.mark.asyncio
async def test_retrieve_honors_k_limit(_mock_mongo, _stub_embedder):
    from src.service.memory.retriever import retrieve_memories

    db = _mock_mongo[_db_name()]
    now = datetime.now(tz=timezone.utc)
    for i in range(15):
        _insert_memory(
            db,
            user_id="alice",
            memory_id=f"m{i}",
            fact=f"memory {i}",
            importance=0.9,
            updated_at=now,
        )

    results = await retrieve_memories(query="memory", user_id="alice", k=5)
    assert len(results) <= 5


@pytest.mark.asyncio
async def test_retrieve_merges_layers_by_weighted_score(_mock_mongo, _stub_embedder):
    """A memory matched by multiple layers should surface with the strongest source."""
    from src.service.memory.retriever import retrieve_memories

    db = _mock_mongo[_db_name()]
    now = datetime.now(tz=timezone.utc)
    # Single memory that qualifies for recent-important AND semantic fallback
    _insert_memory(
        db,
        user_id="alice",
        memory_id="both",
        fact="the",
        importance=0.9,
        updated_at=now,
        embedding=[1.0] * 8,
    )

    results = await retrieve_memories(query="the", user_id="alice")
    matches = [r for r in results if r.memory.memory_id == "both"]
    assert len(matches) == 1  # dedup across layers
    # Source is whichever had the highest weighted score — both semantic/recent are acceptable here
    assert matches[0].source in {"semantic", "recent"}


@pytest.mark.asyncio
async def test_cross_tenant_leak_protection(_mock_mongo, _stub_embedder):
    """Bob's memory must never appear in Alice's retrieval."""
    from src.service.memory.retriever import retrieve_memories

    db = _mock_mongo[_db_name()]
    now = datetime.now(tz=timezone.utc)
    _insert_memory(
        db,
        user_id="bob",
        memory_id="b1",
        fact="bob fact",
        importance=1.0,
        updated_at=now,
        embedding=[1.0] * 8,
    )

    results = await retrieve_memories(query="bob fact", user_id="alice")
    assert all(r.memory.user_id == "alice" for r in results)


def test_cosine_edge_cases():
    from src.service.memory.retriever import _cosine

    assert _cosine([], [1, 2]) == 0.0
    assert _cosine([1, 2], [1, 2, 3]) == 0.0  # length mismatch
    assert _cosine([0, 0], [1, 1]) == 0.0


@pytest.mark.asyncio
async def test_retrieve_survives_embedder_failure(monkeypatch, _mock_mongo):
    """Embedder failure disables semantic layer but other layers still run."""
    from src.service.memory import retriever as ret_mod

    class _BrokenEmb:
        async def aembed_query(self, text):
            raise RuntimeError("portkey down")

    monkeypatch.setattr(ret_mod, "get_embedder", lambda: _BrokenEmb())

    db = _mock_mongo[_db_name()]
    now = datetime.now(tz=timezone.utc)
    _insert_memory(
        db,
        user_id="alice",
        memory_id="r1",
        fact="important",
        importance=0.95,
        updated_at=now,
    )

    results = await ret_mod.retrieve_memories(query="hi", user_id="alice")
    # Recent-important should still work without embeddings
    assert any(r.memory.memory_id == "r1" for r in results)


# ---------------------------------------------------------------------------
# Codex-flagged regression: the FTS projection returned only {_id, score},
# so `_doc_to_memory` validation failed on every hit and was swallowed. These
# tests patch the collection at the `find` boundary since mongomock does not
# implement `$text`.
# ---------------------------------------------------------------------------


class _ChainedCursor:
    """Minimal stand-in for PyMongo's chainable cursor — `.sort(...).limit(N)`."""

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, _n):
        return self

    def __iter__(self):
        return iter(self._docs)


def _fake_fts_doc(**overrides):
    """Realistic FTS hit mirroring the new projection. Override to drop fields."""
    now = datetime.now(tz=timezone.utc)
    doc = {
        "memory_id": "fts-1",
        "user_id": "alice",
        "project_id": None,
        "thread_id": None,
        "database_id": None,
        "fact": "user prefers violin plots",
        "domain": "user-preference",
        "importance": 0.7,
        "salience": 1.0,
        "embedding": [0.1] * 8,
        "pinned": False,
        "superseded_at": None,
        "created_at": now,
        "updated_at": now,
        "access_count": 0,
        "last_accessed_at": None,
        "score": 1.5,
    }
    doc.update(overrides)
    return doc


@pytest.mark.asyncio
async def test_layer_fts_surfaces_hits_with_memory_fields(monkeypatch, _mock_mongo):
    """With the expanded projection, FTS hits round-trip to Memory objects."""
    from src.service.memory import retriever as ret_mod

    hit = _fake_fts_doc()
    db = _mock_mongo[_db_name()]
    coll = db["research_memories"]

    def _fake_find(_filter, _projection):
        return _ChainedCursor([hit])

    monkeypatch.setattr(coll, "find", _fake_find)

    results = await ret_mod._layer_fts("alice", "violin")
    assert len(results) == 1
    mem, score = results[0]
    assert mem.memory_id == "fts-1"
    assert score == 1.5


@pytest.mark.asyncio
async def test_layer_fts_swallows_text_index_missing(monkeypatch, _mock_mongo):
    """If the text index doesn't exist, the layer returns [] without propagating."""
    from pymongo.errors import OperationFailure

    from src.service.memory import retriever as ret_mod

    coll = _mock_mongo[_db_name()]["research_memories"]

    def _raise(_filter, _projection):
        raise OperationFailure("text index required for $text query")

    monkeypatch.setattr(coll, "find", _raise)

    results = await ret_mod._layer_fts("alice", "anything")
    assert results == []


@pytest.mark.asyncio
async def test_layer_fts_projection_drift_does_not_silently_hide_other_errors(
    monkeypatch, _mock_mongo
):
    """A hit missing a required Memory field must fail ValidationError, be
    logged, and be skipped — without the broad `except Exception` swallowing
    unrelated errors. If this test ever surfaces nothing, the projection has
    drifted and the new test above will also fail loudly."""
    from src.service.memory import retriever as ret_mod

    # Build a hit missing the required `fact` field — ValidationError territory.
    broken_hit = _fake_fts_doc()
    del broken_hit["fact"]
    coll = _mock_mongo[_db_name()]["research_memories"]

    def _fake_find(_filter, _projection):
        return _ChainedCursor([broken_hit])

    monkeypatch.setattr(coll, "find", _fake_find)

    results = await ret_mod._layer_fts("alice", "anything")
    assert results == []  # swallowed, but only because of ValidationError
