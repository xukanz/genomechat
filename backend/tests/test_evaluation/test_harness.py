"""Unit tests for evaluation/harness.py.

Strategy: mock `build_graph` and `AsyncSqliteSaver` to avoid real LangGraph
compilation. The test exercises the tracer-swap, OTel-enabled override, and
serialization paths in isolation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from evaluation import harness as harness_mod


class _FakeAgent:
    async def ainvoke(self, state, config=None):
        # Emit a trace via the swapped decorators tracer
        import src.service.observability.decorators as dec_mod

        with dec_mod.tracer.start_as_current_span("agent.node.coder") as s:
            s.set_attribute("agent.name", "coder")
        with dec_mod.tracer.start_as_current_span("gen_ai.chat") as s:
            s.set_attribute("gen_ai.request.model", "claude-haiku-4-5")
            s.set_attribute("gen_ai.usage.input_tokens", 100)
            s.set_attribute("gen_ai.usage.output_tokens", 50)
            s.set_attribute("gen_ai.usage.cost_usd", 0.00035)
        return {"messages": [{"type": "ai", "content": "done"}]}


class _FakeBuilder:
    def compile(self, checkpointer=None):
        return _FakeAgent()


@asynccontextmanager
async def _fake_saver(conn_string: str):
    yield object()


@pytest.mark.asyncio
async def test_replay_captures_node_and_llm_spans(monkeypatch):
    from langgraph.checkpoint.sqlite import aio as saver_mod

    monkeypatch.setattr(harness_mod, "build_graph", lambda: _FakeBuilder())
    monkeypatch.setattr(saver_mod.AsyncSqliteSaver, "from_conn_string", staticmethod(_fake_saver))

    record = {"query": "hi", "thread_id": "t1", "database_id": "clinvar"}
    result = await harness_mod.replay(record)

    span_names = [s["name"] for s in result.spans]
    assert any(n.startswith("agent.node.") for n in span_names)
    assert "gen_ai.chat" in span_names
    assert result.response == "done"
    assert result.backend == "langchain"
    # cost is aggregated from gen_ai.chat spans
    assert pytest.approx(result.cost_usd, rel=1e-3) == 0.00035


@pytest.mark.asyncio
async def test_replay_unsupported_backend_rejected():
    # Phase 1: 'sdk' is now supported. Only truly unknown backends are rejected.
    with pytest.raises(ValueError):
        await harness_mod.replay({"query": "x"}, backend="unknown-backend")


@pytest.mark.asyncio
async def test_replay_does_not_leak_to_parallel_tracer(monkeypatch):
    """Ensure a replay's TracerProvider swap is scoped and restored."""
    from langgraph.checkpoint.sqlite import aio as saver_mod

    import src.service.observability.callbacks as cb_mod
    import src.service.observability.decorators as dec_mod

    monkeypatch.setattr(harness_mod, "build_graph", lambda: _FakeBuilder())
    monkeypatch.setattr(saver_mod.AsyncSqliteSaver, "from_conn_string", staticmethod(_fake_saver))

    before_dec = dec_mod.tracer
    before_cb = cb_mod.tracer
    await harness_mod.replay({"query": "q"})
    assert dec_mod.tracer is before_dec, "decorators tracer was not restored after replay"
    assert cb_mod.tracer is before_cb, "callbacks tracer was not restored after replay"


class _CallbackEmittingAgent:
    """Simulates an LLM call by invoking OTelCallbackHandler directly.

    Regression for Codex Finding 1 — before the fix, `OTelCallbackHandler`
    resolved its tracer via `trace.get_tracer(...)` against the global
    provider, so the replay's in-memory exporter never saw LLM spans even
    though the decorator tracer was swapped.
    """

    async def ainvoke(self, state, config=None):
        from uuid import uuid4

        from src.service.observability.callbacks import OTelCallbackHandler

        handler = OTelCallbackHandler()
        run_id = uuid4()
        handler.on_llm_start(
            serialized={"name": "ChatBedrock"},
            prompts=["hi"],
            run_id=run_id,
            invocation_params={"model": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
        )
        # Fake a response with usage_metadata
        from types import SimpleNamespace

        message = SimpleNamespace(
            usage_metadata={"input_tokens": 42, "output_tokens": 21},
            response_metadata={},
        )
        response = SimpleNamespace(generations=[[SimpleNamespace(message=message)]], llm_output={})
        handler.on_llm_end(response, run_id=run_id)
        return {"messages": [{"type": "ai", "content": "done"}]}


class _CallbackEmittingBuilder:
    def compile(self, checkpointer=None):
        return _CallbackEmittingAgent()


@pytest.mark.asyncio
async def test_replay_captures_llm_span_from_callback_handler(monkeypatch):
    """Regression: the real OTelCallbackHandler must emit into the replay exporter.

    The fake agent drives `on_llm_start`/`on_llm_end` directly. Before the
    Fix-1 change to make `callbacks.tracer` a swappable module-level handle,
    this span would have landed on the global NoOp provider and been lost.
    """
    from langgraph.checkpoint.sqlite import aio as saver_mod

    monkeypatch.setattr(harness_mod, "build_graph", lambda: _CallbackEmittingBuilder())
    monkeypatch.setattr(saver_mod.AsyncSqliteSaver, "from_conn_string", staticmethod(_fake_saver))

    result = await harness_mod.replay({"query": "hi", "thread_id": "alice:c1"})

    llm_spans = [s for s in result.spans if s["name"] == "gen_ai.chat"]
    assert len(llm_spans) == 1, "callback-emitted LLM span missing from replay output"
    attrs = llm_spans[0]["attributes"]
    assert attrs["gen_ai.usage.input_tokens"] == 42
    assert attrs["gen_ai.usage.output_tokens"] == 21
    # Fix 2: the LLM span carries the replay's thread_id from thread_id_context
    assert attrs["agent.thread_id"] == "alice:c1"


def test_smoke_check_passes_for_valid_records(tmp_path):
    from evaluation.cli import _smoke_check

    out = tmp_path / "out.jsonl"
    import json

    rec = {
        "response": "hello",
        "spans": [
            {"name": "agent.node.coder", "attributes": {}},
            {"name": "gen_ai.chat", "attributes": {"gen_ai.usage.cost_usd": 0.0}},
        ],
    }
    out.write_text(json.dumps(rec) + "\n")
    passed, failed = _smoke_check(out)
    assert (passed, failed) == (1, 0)


def test_smoke_check_fails_on_missing_llm_span(tmp_path):
    from evaluation.cli import _smoke_check

    out = tmp_path / "out.jsonl"
    import json

    rec = {
        "response": "hello",
        "spans": [{"name": "agent.node.coder", "attributes": {}}],
    }
    out.write_text(json.dumps(rec) + "\n")
    passed, failed = _smoke_check(out)
    assert (passed, failed) == (0, 1)


def test_smoke_check_fails_on_empty_response(tmp_path):
    from evaluation.cli import _smoke_check

    out = tmp_path / "out.jsonl"
    import json

    rec = {
        "response": "",
        "spans": [
            {"name": "agent.node.coder", "attributes": {}},
            {"name": "gen_ai.chat", "attributes": {}},
        ],
    }
    out.write_text(json.dumps(rec) + "\n")
    passed, failed = _smoke_check(out)
    assert (passed, failed) == (0, 1)


def test_smoke_check_fails_on_malformed_json(tmp_path):
    from evaluation.cli import _smoke_check

    out = tmp_path / "out.jsonl"
    out.write_text("not-json\n")
    passed, failed = _smoke_check(out)
    assert (passed, failed) == (0, 1)
