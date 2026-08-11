"""Unit tests for src.service.memory.consolidator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _db_name() -> str:
    from src.config.settings import settings

    return settings.mongodb_db_name


@pytest.fixture
def _mock_mongo(monkeypatch, mongomock_client):
    from src.service.memory import consolidator as cons_mod

    monkeypatch.setattr(cons_mod, "get_mongodb_client", lambda: mongomock_client)
    return mongomock_client


@pytest.fixture
def _stub_embedder(monkeypatch):
    from src.service.memory import consolidator as cons_mod

    class _Emb:
        async def aembed_query(self, text):
            return [0.5] * 4

    monkeypatch.setattr(cons_mod, "get_embedder", lambda: _Emb())
    return _Emb()


def _insert(db, **kwargs) -> None:
    defaults = {
        "memory_id": kwargs["memory_id"],
        "user_id": kwargs["user_id"],
        "project_id": None,
        "thread_id": None,
        "database_id": None,
        "fact": kwargs.get("fact", "f"),
        "domain": kwargs.get("domain", "query-pattern"),
        "importance": kwargs.get("importance", 0.5),
        "salience": kwargs.get("salience", 1.0),
        "embedding": kwargs.get("embedding", [1.0, 0.0, 0.0, 0.0]),
        "pinned": kwargs.get("pinned", False),
        "superseded_at": None,
        "created_at": kwargs.get("created_at", datetime.now(tz=timezone.utc)),
        "updated_at": kwargs.get("updated_at", datetime.now(tz=timezone.utc)),
        "access_count": 0,
        "last_accessed_at": kwargs.get("last_accessed_at"),
    }
    db["research_memories"].insert_one(defaults)


@pytest.mark.asyncio
async def test_consolidation_empty_user_is_noop(_mock_mongo, _stub_embedder):
    from src.service.memory.consolidator import run_consolidation

    counters = await run_consolidation(user_id="nobody")
    assert counters["clusters"] == 0
    assert counters["insights"] == 0


@pytest.mark.asyncio
async def test_consolidation_creates_insight_for_multi_member_cluster(
    _mock_mongo, _stub_embedder, monkeypatch
):
    from src.service.memory import consolidator as cons_mod

    # Bypass the Haiku contradiction call — not what we're asserting here
    async def _no_llm(*_args, **_kwargs):
        raise RuntimeError("no LLM in this test")

    fake_llm = MagicMock()
    fake_llm.ainvoke = _no_llm
    monkeypatch.setattr(
        cons_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: fake_llm)
    )

    db = _mock_mongo[_db_name()]
    same_vec = [1.0, 0.0, 0.0, 0.0]
    _insert(db, memory_id="a", user_id="alice", fact="uses violin plots", embedding=same_vec)
    _insert(db, memory_id="b", user_id="alice", fact="prefers violin layout", embedding=same_vec)

    counters = await cons_mod.run_consolidation(user_id="alice")
    assert counters["clusters"] == 1
    assert counters["insights"] == 1
    insights = list(db["memory_insights"].find({"user_id": "alice"}))
    assert len(insights) == 1
    assert set(insights[0]["member_memory_ids"]) == {"a", "b"}


@pytest.mark.asyncio
async def test_salience_decay_and_hard_delete(_mock_mongo, _stub_embedder):
    from src.service.memory.consolidator import run_consolidation

    db = _mock_mongo[_db_name()]
    now = datetime.now(tz=timezone.utc)

    # Very old unpinned memory with already-low salience → deleted
    _insert(
        db,
        memory_id="old-doomed",
        user_id="alice",
        salience=0.08,
        last_accessed_at=now - timedelta(days=60),
    )
    # Recent memory — decay skipped (days <= 0)
    _insert(
        db,
        memory_id="recent-stable",
        user_id="alice",
        salience=0.9,
        last_accessed_at=now,
    )
    # Pinned memory — never decays
    _insert(
        db,
        memory_id="pinned-forever",
        user_id="alice",
        salience=0.1,
        pinned=True,
        last_accessed_at=now - timedelta(days=365),
    )

    counters = await run_consolidation(user_id="alice")

    assert counters["deleted"] == 1
    remaining_ids = {d["memory_id"] for d in db["research_memories"].find({"user_id": "alice"})}
    assert "old-doomed" not in remaining_ids
    assert "pinned-forever" in remaining_ids
    # Pinned salience unchanged
    pinned = db["research_memories"].find_one({"memory_id": "pinned-forever"})
    assert pinned["salience"] == 0.1


@pytest.mark.asyncio
async def test_contradiction_detection_supersedes_older(_mock_mongo, _stub_embedder, monkeypatch):
    from src.service.memory import consolidator as cons_mod

    async def _contradicts(_):
        return SimpleNamespace(content='{"contradicts": true, "explanation": "x"}')

    llm = MagicMock()
    llm.ainvoke = _contradicts
    monkeypatch.setattr(cons_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: llm))

    db = _mock_mongo[_db_name()]
    same_vec = [1.0, 0.0, 0.0, 0.0]
    old_time = datetime.now(tz=timezone.utc) - timedelta(days=30)
    new_time = datetime.now(tz=timezone.utc)
    _insert(
        db,
        memory_id="old",
        user_id="alice",
        fact="prefers R",
        embedding=same_vec,
        created_at=old_time,
        importance=0.8,
        salience=1.0,
    )
    _insert(
        db,
        memory_id="new",
        user_id="alice",
        fact="prefers Python",
        embedding=same_vec,
        created_at=new_time,
        importance=0.8,
        salience=1.0,
    )

    counters = await cons_mod.run_consolidation(user_id="alice")
    assert counters["superseded"] >= 1
    old_doc = db["research_memories"].find_one({"memory_id": "old"})
    assert old_doc["importance"] < 0.8  # 0.8 * 0.3 = 0.24
    assert old_doc["superseded_at"] is not None


def test_parse_contradiction_handles_code_fences():
    from src.service.memory.consolidator import _parse_contradiction

    out = _parse_contradiction('```json\n{"contradicts": true, "explanation": "x"}\n```')
    assert out["contradicts"] is True

    out2 = _parse_contradiction("not-json")
    assert out2["contradicts"] is False


def test_greedy_cluster_groups_by_cosine_threshold():
    from src.service.memory.consolidator import _greedy_cluster

    v1 = [1.0, 0.0]
    v2 = [0.99, 0.01]  # close to v1
    v3 = [0.0, 1.0]  # orthogonal
    mems = [
        {"embedding": v1, "memory_id": "a"},
        {"embedding": v2, "memory_id": "b"},
        {"embedding": v3, "memory_id": "c"},
    ]
    clusters = _greedy_cluster(mems)
    # Two clusters: {a, b} and {c}
    cluster_sizes = sorted(len(c) for c in clusters)
    assert cluster_sizes == [1, 2]


# ---------------------------------------------------------------------------
# Codex-flagged regression: `_emit_insight` used `uuid.uuid4().hex` + unconditional
# `insert_one`, so the 30-minute APScheduler cadence duplicated insights for
# stable clusters forever. The fix derives `insight_id` from sorted
# member_memory_ids and upserts.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consolidation_is_idempotent_across_runs(_mock_mongo, _stub_embedder, monkeypatch):
    """Two runs over a stable cluster must produce exactly one insight row."""
    from src.service.memory import consolidator as cons_mod

    async def _no_llm(*_args, **_kwargs):
        raise RuntimeError("no LLM in this test")

    fake_llm = MagicMock()
    fake_llm.ainvoke = _no_llm
    monkeypatch.setattr(
        cons_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: fake_llm)
    )

    db = _mock_mongo[_db_name()]
    same_vec = [1.0, 0.0, 0.0, 0.0]
    _insert(db, memory_id="a", user_id="alice", fact="uses violin plots", embedding=same_vec)
    _insert(db, memory_id="b", user_id="alice", fact="prefers violin layout", embedding=same_vec)

    first = await cons_mod.run_consolidation(user_id="alice")
    second = await cons_mod.run_consolidation(user_id="alice")

    assert first["insights"] == 1
    assert second["insights"] == 0, "second run must not create a duplicate insight"
    assert db["memory_insights"].count_documents({"user_id": "alice"}) == 1


@pytest.mark.asyncio
async def test_consolidation_updates_insight_on_re_run(_mock_mongo, _stub_embedder, monkeypatch):
    """Upsert path refreshes $set fields when cluster contents change but
    membership stays the same (same memory_ids, different fact text)."""
    from src.service.memory import consolidator as cons_mod

    async def _no_llm(*_args, **_kwargs):
        raise RuntimeError("no LLM in this test")

    fake_llm = MagicMock()
    fake_llm.ainvoke = _no_llm
    monkeypatch.setattr(
        cons_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: fake_llm)
    )

    db = _mock_mongo[_db_name()]
    same_vec = [1.0, 0.0, 0.0, 0.0]
    _insert(db, memory_id="a", user_id="alice", fact="old fact A", embedding=same_vec)
    _insert(db, memory_id="b", user_id="alice", fact="old fact B", embedding=same_vec)

    await cons_mod.run_consolidation(user_id="alice")
    # Mutate one member's fact before the next run
    db["research_memories"].update_one({"memory_id": "a"}, {"$set": {"fact": "NEW fact A"}})
    await cons_mod.run_consolidation(user_id="alice")

    rows = list(db["memory_insights"].find({"user_id": "alice"}))
    assert len(rows) == 1
    assert "NEW fact A" in rows[0]["summary"]


@pytest.mark.asyncio
async def test_insight_id_changes_when_cluster_membership_changes(
    _mock_mongo, _stub_embedder, monkeypatch
):
    """Adding a memory to the cluster produces a new insight; the old one
    remains (subset-insight behavior — Phase 3 GC tracked separately)."""
    from src.service.memory import consolidator as cons_mod

    async def _no_llm(*_args, **_kwargs):
        raise RuntimeError("no LLM in this test")

    fake_llm = MagicMock()
    fake_llm.ainvoke = _no_llm
    monkeypatch.setattr(
        cons_mod.LLMService, "get_llm_by_agent", staticmethod(lambda *a, **k: fake_llm)
    )

    db = _mock_mongo[_db_name()]
    same_vec = [1.0, 0.0, 0.0, 0.0]
    _insert(db, memory_id="a", user_id="alice", fact="fa", embedding=same_vec)
    _insert(db, memory_id="b", user_id="alice", fact="fb", embedding=same_vec)

    await cons_mod.run_consolidation(user_id="alice")
    _insert(db, memory_id="c", user_id="alice", fact="fc", embedding=same_vec)
    await cons_mod.run_consolidation(user_id="alice")

    insights = list(db["memory_insights"].find({"user_id": "alice"}))
    assert len(insights) == 2
    memberships = sorted(tuple(sorted(i["member_memory_ids"])) for i in insights)
    assert memberships == [("a", "b"), ("a", "b", "c")]
