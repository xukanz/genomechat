"""Harness tests for the SDK backend branch.

Strategy: patch the SDK ``query()`` so we can drive a controlled message
stream; the real graph + coder_node + coder_sdk stack run underneath. Tests
keep ``settings.coder_backend = 'langchain'`` throughout — the harness no
longer mutates settings; it uses a per-task ``coder_backend_context``
ContextVar override instead, so tests assert that settings is NEVER touched
while the ContextVar correctly dispatches to the SDK path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from evaluation import harness as harness_mod


class _TextBlock:
    def __init__(self, text: str):
        self.text = text


class AssistantMessage:  # noqa: N801
    def __init__(self, blocks):
        self.content = blocks


class ResultMessage:  # noqa: N801
    def __init__(self, result: str, usage: dict | None = None, total_cost_usd: float | None = None):
        self.result = result
        self.usage = usage
        self.total_cost_usd = total_cost_usd


def _canned_query(messages):
    async def fake_query(prompt, options):
        for m in messages:
            yield m

    return fake_query


@asynccontextmanager
async def _fake_saver(conn_string: str):
    yield object()


class _DirectCoderAgent:
    """Fake graph that invokes the real coder_node with the SDK backend.

    We sidestep ``build_graph()`` (which pulls in LangGraph compilation) by
    calling the coder node directly with a minimal AgentState. coder_node
    reads ``settings.coder_backend`` via ``resolve_agent_backend`` and
    dispatches to ``invoke_coder_sdk`` — that's the real Phase 1 path under
    test.
    """

    def __init__(self, query_text: str):
        self._query_text = query_text

    async def ainvoke(self, state, config=None):
        from langchain_core.messages import HumanMessage

        from src.graph.nodes import coder_node

        state_payload = {
            "messages": [HumanMessage(content=self._query_text)],
            "thread_id": state.get("thread_id", ""),
            "database_id": state.get("database_id", ""),
            "project_id": state.get("project_id", ""),
            "research_mode": "",
            "code_language": "python",
        }
        cmd = await coder_node(state_payload)
        # Pack the coder's output message into the terminal state
        coder_msg = cmd.update.get("messages", [])[0]
        return {"messages": [SimpleNamespace(type="ai", content=coder_msg.content)]}


class _DirectCoderBuilder:
    def __init__(self, query_text: str):
        self._query_text = query_text

    def compile(self, checkpointer=None):
        return _DirectCoderAgent(self._query_text)


@pytest.fixture
def _patch_mcp_and_saver(monkeypatch):
    """Prevent the real MCP servers from spinning up for each test."""
    from langgraph.checkpoint.sqlite import aio as saver_mod

    monkeypatch.setattr(saver_mod.AsyncSqliteSaver, "from_conn_string", staticmethod(_fake_saver))

    with patch(
        "src.agents.coder_sdk.build_all_coder_servers",
        return_value={"sandbox": {}, "s3": {}, "file_ops": {}},
    ), patch(
        "src.agents.coder_sdk.mcp_tool_names",
        return_value=["mcp__sandbox__execute_code"],
    ):
        yield


@pytest.mark.asyncio
async def test_replay_sdk_emits_node_and_gen_ai_chat_spans(
    monkeypatch, _patch_mcp_and_saver
):
    """The SDK replay must produce agent.node.coder (backend=sdk) + gen_ai.chat."""
    from src.config.settings import settings
    from src.service import sdk_runtime

    # Baseline: ensure the flag starts on langchain so we can prove the swap
    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(settings, "portkey_bedrock_slug", "bedrock")
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "harness-sdk-test")

    monkeypatch.setattr(
        harness_mod,
        "build_graph",
        lambda: _DirectCoderBuilder(query_text="run some python"),
    )

    canned = [
        AssistantMessage([_TextBlock("from sdk")]),
        ResultMessage(
            result="from sdk",
            usage={"input_tokens": 10, "output_tokens": 5},
            total_cost_usd=0.0002,
        ),
    ]

    with patch("claude_agent_sdk.query", new=_canned_query(canned)):
        result = await harness_mod.replay(
            {"query": "x", "thread_id": "t1"}, backend="sdk"
        )

    span_names = [s["name"] for s in result.spans]

    # Node span should be present AND carry agent.backend=sdk
    coder_node_spans = [s for s in result.spans if s["name"] == "agent.node.coder"]
    assert coder_node_spans, f"expected agent.node.coder span; got {span_names}"
    assert coder_node_spans[0]["attributes"].get("agent.backend") == "sdk"

    # LLM span must be emitted manually by coder_sdk (no LangChain callback)
    assert "gen_ai.chat" in span_names

    # Cost aggregation
    assert result.cost_usd == pytest.approx(0.0002, rel=1e-3)
    assert result.backend == "sdk"
    assert result.response == "from sdk"


@pytest.mark.asyncio
async def test_replay_does_not_mutate_settings_coder_backend(monkeypatch, _patch_mcp_and_saver):
    """settings.coder_backend must never be mutated during a replay.

    The harness uses the ``coder_backend_context`` ContextVar instead of
    flipping shared settings — this test pins that invariant so any future
    refactor that reintroduces the mutation is caught before it can corrupt
    concurrent replays.
    """
    from src.config.agent_backends import coder_backend_context
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(settings, "portkey_bedrock_slug", "bedrock")

    monkeypatch.setattr(
        harness_mod,
        "build_graph",
        lambda: _DirectCoderBuilder(query_text="x"),
    )

    canned = [
        ResultMessage(
            result="ok", usage={"input_tokens": 1, "output_tokens": 1}, total_cost_usd=0.0
        ),
    ]

    assert settings.coder_backend == "langchain"
    assert coder_backend_context.get() is None
    with patch("claude_agent_sdk.query", new=_canned_query(canned)):
        await harness_mod.replay({"query": "x"}, backend="sdk")
    assert settings.coder_backend == "langchain", "settings must be untouched by replay"
    assert coder_backend_context.get() is None, "ContextVar must be reset after replay"


@pytest.mark.asyncio
async def test_replay_resets_contextvar_on_exception(
    monkeypatch, _patch_mcp_and_saver
):
    """Even if the graph blows up, coder_backend_context must be reset."""
    from src.config.agent_backends import coder_backend_context
    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(settings, "portkey_bedrock_slug", "bedrock")

    class _Explosive:
        def compile(self, checkpointer=None):
            class _A:
                async def ainvoke(self, *a, **kw):
                    raise RuntimeError("graph boom")

            return _A()

    monkeypatch.setattr(harness_mod, "build_graph", lambda: _Explosive())

    assert coder_backend_context.get() is None
    with pytest.raises(RuntimeError, match="graph boom"):
        await harness_mod.replay({"query": "x"}, backend="sdk")
    assert settings.coder_backend == "langchain", "settings must be untouched"
    assert coder_backend_context.get() is None, "ContextVar must be reset even on failure"


@pytest.mark.asyncio
async def test_replay_unsupported_backend_raises_valueerror():
    with pytest.raises(ValueError, match="Unsupported backend"):
        await harness_mod.replay({"query": "x"}, backend="claude-magic")


@pytest.mark.asyncio
async def test_concurrent_replays_preserve_backend_isolation(
    monkeypatch, _patch_mcp_and_saver
):
    """Two replays running concurrently must not cross-contaminate.

    Regression for the Codex adversarial review finding: pre-fix, the harness
    mutated ``settings.coder_backend`` which is process-wide — an SDK replay
    and a LangChain replay gathered via ``asyncio.gather`` would race on
    that shared state. The ContextVar fix makes this deterministic.

    We fire both backends simultaneously via ``asyncio.gather`` and assert
    each result carries the expected ``agent.backend`` attribute on its
    ``agent.node.coder`` span. If a race existed, one task's backend swap
    could be visible to the other mid-flight and the assertion would be
    intermittent.
    """
    import asyncio

    from src.config.settings import settings

    monkeypatch.setattr(settings, "coder_backend", "langchain")
    monkeypatch.setattr(settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(settings, "portkey_bedrock_slug", "bedrock")

    monkeypatch.setattr(
        harness_mod,
        "build_graph",
        lambda: _DirectCoderBuilder(query_text="concurrent"),
    )

    # Canned SDK response for whichever task happens to take the SDK path.
    canned = [
        AssistantMessage([_TextBlock("from-sdk")]),
        ResultMessage(
            result="from-sdk",
            usage={"input_tokens": 1, "output_tokens": 1},
            total_cost_usd=0.0,
        ),
    ]

    # Canned LangChain agent — replaces the real LLMService-backed coder so
    # the "langchain" branch of coder_node doesn't hit Portkey. The
    # ContextVar dispatch logic doesn't care about the agent's content; we
    # just need coder_node to return some message and set agent.backend=
    # langchain on its span.
    class _FakeLangChainAgent:
        async def ainvoke(self, state, config=None):
            from langchain_core.messages import AIMessage
            return {"messages": [AIMessage(content="from-langchain")]}

    def _fake_create_coder_agent(**kwargs):
        return _FakeLangChainAgent()

    # Run concurrent SDK + LangChain replays. If a race existed, the
    # ContextVar from one task could leak to the other and the backend
    # attribute would be wrong intermittently.
    async def one_pair() -> tuple[str, str]:
        with patch("claude_agent_sdk.query", new=_canned_query(canned)), \
             patch("src.graph.nodes.create_coder_agent", new=_fake_create_coder_agent):
            sdk_task = harness_mod.replay(
                {"query": "x", "thread_id": "t-sdk"}, backend="sdk"
            )
            lc_task = harness_mod.replay(
                {"query": "x", "thread_id": "t-lc"}, backend="langchain"
            )
            sdk_result, lc_result = await asyncio.gather(sdk_task, lc_task)

        def _backend_on_coder_span(result) -> str:
            coder_spans = [s for s in result.spans if s["name"] == "agent.node.coder"]
            assert coder_spans, f"no coder span in {[s['name'] for s in result.spans]}"
            return coder_spans[0]["attributes"].get("agent.backend", "")

        return _backend_on_coder_span(sdk_result), _backend_on_coder_span(lc_result)

    # Run several rounds so scheduling variation has a chance to expose races.
    for _ in range(3):
        sdk_backend, lc_backend = await one_pair()
        assert sdk_backend == "sdk", f"sdk replay got {sdk_backend!r}"
        assert lc_backend == "langchain", f"langchain replay got {lc_backend!r}"

    # Settings must still be untouched and ContextVar cleared.
    from src.config.agent_backends import coder_backend_context

    assert settings.coder_backend == "langchain"
    assert coder_backend_context.get() is None
