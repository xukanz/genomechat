"""Unit tests for src.service.memory.schema."""

from __future__ import annotations

import pytest

from src.service.memory.schema import (
    Memory,
    MemoryInsight,
    memory_index_specs,
    vector_search_index_spec,
)


def test_memory_requires_core_fields():
    m = Memory(
        memory_id="abc",
        user_id="alice",
        fact="User prefers Python over R for plotting.",
        domain="user-preference",
        importance=0.7,
    )
    assert m.salience == 1.0
    assert m.pinned is False
    assert m.superseded_at is None
    assert m.created_at.tzinfo is not None


def test_memory_rejects_out_of_range_importance():
    with pytest.raises(ValueError):
        Memory(
            memory_id="abc",
            user_id="alice",
            fact="x",
            domain="user-preference",
            importance=1.5,
        )


def test_memory_rejects_unknown_domain():
    with pytest.raises(ValueError):
        Memory(
            memory_id="abc",
            user_id="alice",
            fact="x",
            domain="not-a-domain",  # type: ignore[arg-type]
            importance=0.5,
        )


def test_memory_rejects_extra_fields():
    # extra="forbid" — catches typos at model-validation time
    with pytest.raises(ValueError):
        Memory(
            memory_id="abc",
            user_id="alice",
            fact="x",
            domain="user-preference",
            importance=0.5,
            zzz_extra="oops",  # type: ignore[call-arg]
        )


def test_memory_insight_minimal():
    i = MemoryInsight(
        insight_id="i1",
        user_id="alice",
        summary="Alice asks about PD-L1 + CD8 + TMB frequently.",
        domain="query-pattern",
        member_memory_ids=["m1", "m2"],
    )
    assert i.embedding is None
    assert i.member_memory_ids == ["m1", "m2"]


def test_index_specs_include_ttl_for_memories():
    specs = memory_index_specs(dimensions=1024, ttl_days=180)
    mem_specs = specs["research_memories"]
    ttl_specs = [s for s in mem_specs if s.get("name") == "memory_ttl_idx"]
    assert len(ttl_specs) == 1
    assert ttl_specs[0]["expireAfterSeconds"] == 180 * 86400


def test_index_specs_include_unique_memory_id():
    specs = memory_index_specs(dimensions=1024, ttl_days=180)
    names = {s["name"] for s in specs["research_memories"]}
    assert "memory_id_unique" in names
    assert "insight_id_unique" in {s["name"] for s in specs["memory_insights"]}


def test_index_specs_include_redaction_log():
    specs = memory_index_specs(dimensions=1024, ttl_days=180)
    assert "memory_redaction_log" in specs
    assert any(s["name"] == "user_timestamp_idx" for s in specs["memory_redaction_log"])


def test_vector_search_index_spec_matches_dimensions():
    spec = vector_search_index_spec(dimensions=1024)
    field = spec["definition"]["mappings"]["fields"]["embedding"]
    assert field["dimensions"] == 1024
    assert field["similarity"] == "cosine"
    assert field["type"] == "knnVector"
