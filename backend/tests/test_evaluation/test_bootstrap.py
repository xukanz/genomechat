"""Unit tests for evaluation/datasets/bootstrap.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from evaluation.datasets import bootstrap as bootstrap_mod


def test_missing_consented_user_ids_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(bootstrap_mod.settings, "eval_consented_user_ids", "")
    with pytest.raises(RuntimeError, match="eval_consented_user_ids is empty"):
        import asyncio

        asyncio.run(bootstrap_mod.build_dataset(tmp_path / "baseline.jsonl"))


def test_parse_consented_user_ids(monkeypatch):
    monkeypatch.setattr(bootstrap_mod.settings, "eval_consented_user_ids", "u1, u2 , u3")
    assert bootstrap_mod._parse_consented_user_ids() == ["u1", "u2", "u3"]


def test_parse_consented_user_ids_empty_segments_dropped(monkeypatch):
    monkeypatch.setattr(bootstrap_mod.settings, "eval_consented_user_ids", "u1,,u2, ")
    assert bootstrap_mod._parse_consented_user_ids() == ["u1", "u2"]


class _FakeCheckpointer:
    """Minimal async checkpointer replicating the `alist` iteration shape."""

    def __init__(self, messages: list):
        self._messages = messages

    async def alist(self, config, limit=1):
        yield SimpleNamespace(checkpoint={"channel_values": {"messages": self._messages}})


def _install_checkpointer(monkeypatch, messages: list):
    from src.graph import checkpointer as cp_mod

    @asynccontextmanager
    async def _fake_cm():
        yield _FakeCheckpointer(messages)

    monkeypatch.setattr(cp_mod, "create_checkpointer", _fake_cm)


@pytest.mark.asyncio
async def test_extract_final_user_query_skips_coordinator_synthetic_message(monkeypatch):
    """Regression for Codex Finding 3 — coordinator's direct-response HumanMessage(name='coordinator')
    must not be returned as the user query. The last *genuinely user-authored*
    HumanMessage (empty `name`) is the right answer.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    # Realistic direct-response conversation sequence per coordinator_node:
    # 1. User's actual question (no name)
    # 2. Coordinator's inner-thought reasoning as SystemMessage (not a human type)
    # 3. Coordinator's answer as HumanMessage(name="coordinator")
    user_q = HumanMessage(content="What is the pathogenicity distribution in ClinVar?")
    coord_reasoning = AIMessage(content="User wants a simple count.")
    coord_answer = HumanMessage(
        content="ClinVar contains pathogenic (~18%) and benign (~82%) submissions.",
        name="coordinator",
    )
    messages = [user_q, coord_reasoning, coord_answer]
    _install_checkpointer(monkeypatch, messages)

    result = await bootstrap_mod._extract_final_user_query(
        {"thread_id": "alice:c1", "conversation_id": "c1"}
    )
    assert result == "What is the pathogenicity distribution in ClinVar?"


@pytest.mark.asyncio
async def test_extract_final_user_query_skips_orchestrator_task_rewrite(monkeypatch):
    """The _prepare_worker_messages path rewrites orchestrator output as
    HumanMessage(name='orchestrator_task'). Those must also be skipped."""
    from langchain_core.messages import HumanMessage

    user_q = HumanMessage(content="Compare diversity across cohorts.")
    worker_task = HumanMessage(
        content="[Orchestrator Task]\nCall SQL agent on clinvar.",
        name="orchestrator_task",
    )
    messages = [user_q, worker_task]
    _install_checkpointer(monkeypatch, messages)

    result = await bootstrap_mod._extract_final_user_query(
        {"thread_id": "bob:c2", "conversation_id": "c2"}
    )
    assert result == "Compare diversity across cohorts."


@pytest.mark.asyncio
async def test_extract_final_user_query_returns_none_when_only_synthetic_humans(monkeypatch):
    """Defensive: no genuine user message → None (dropped by caller), not the synthetic one."""
    from langchain_core.messages import HumanMessage

    synthetic_only = [
        HumanMessage(content="coordinator direct response", name="coordinator"),
        HumanMessage(content="another synthetic", name="orchestrator_task"),
    ]
    _install_checkpointer(monkeypatch, synthetic_only)

    result = await bootstrap_mod._extract_final_user_query(
        {"thread_id": "alice:c3", "conversation_id": "c3"}
    )
    assert result is None
