"""Tests for agents.orchestrator_sdk.invoke_orchestrator_sdk (Phase 2 Workstream B).

Mirrors the test surface of ``test_coder_sdk.py`` because the two SDK paths
share structure (``_build_options`` + ``query()`` loop + exception →
empty-string + gen_ai.chat span emission + transcript cleanup). Pinning
identical invariants for both prevents drift between the two backends —
the Workstream B ADR's evaluation must compare like-for-like code paths.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# Fake SDK message classes — mirror the real classes by name so the SDK
# module's ``type(msg).__name__`` dispatch matches.
# ---------------------------------------------------------------------------


class _TextBlock:
    def __init__(self, text: str):
        self.text = text


class AssistantMessage:  # noqa: N801 — mirror SDK name
    def __init__(self, blocks):
        self.content = blocks


class ResultMessage:  # noqa: N801
    def __init__(self, result: str, usage: dict | None = None, total_cost_usd: float | None = None):
        self.result = result
        self.usage = usage
        self.total_cost_usd = total_cost_usd


def _make_mock_query(messages: list[Any]):
    async def fake_query(prompt: str, options: Any):
        for m in messages:
            yield m

    return fake_query


@pytest.fixture
def _patch_mcp_builders():
    """Avoid building the real MCP servers during tests.

    The orchestrator SDK wires four servers (sandbox + s3 + file_ops +
    database). We replace ``build_all_orchestrator_servers``
    wholesale with a minimal stub; same for ``orchestrator_mcp_tool_names``
    so the parametrised allowed_tools invariant tests don't need the full
    tool surface.
    """
    with (
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={
                "sandbox": {},
                "s3": {},
                "file_ops": {},
                "database": {},
            },
        ),
        patch(
            "src.agents.orchestrator_sdk.orchestrator_mcp_tool_names",
            return_value=[
                "mcp__sandbox__execute_code",
                "mcp__database__execute_sql_query",
                "mcp__sandbox__execute_r_code",
            ],
        ),
    ):
        yield


@pytest.fixture
def _patch_compose_prompt():
    """The shared compose_orchestrator_system_prompt reads from disk + the
    database context; stub it to a deterministic string so tests don't
    depend on the prompt file layout or active database profile."""
    with patch(
        "src.agents.orchestrator_sdk.compose_orchestrator_system_prompt",
        return_value="ORCH_PROMPT_STUB",
    ):
        yield


# ---------------------------------------------------------------------------
# Happy path + span emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_success(
    in_memory_span_exporter,
    _patch_mcp_builders,
    _patch_compose_prompt,
    tmp_path,
    monkeypatch,
):
    """Happy path: query yields AssistantMessage + ResultMessage → final text returned."""
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-sdk-test")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_api_key", "fake-key")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock")

    usage = {"input_tokens": 500, "output_tokens": 120}
    messages = [
        AssistantMessage([_TextBlock("plan narration")]),
        ResultMessage(result="synthesized final answer", usage=usage, total_cost_usd=0.0042),
    ]

    with patch("claude_agent_sdk.query", new=_make_mock_query(messages)):
        response = await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": [HumanMessage(content="research question")]},
            thread_id="u1:c1",
        )

    assert response == "synthesized final answer"

    # gen_ai.chat span emitted with all five contract attributes
    spans = in_memory_span_exporter.get_finished_spans()
    chat_spans = [s for s in spans if s.name == "gen_ai.chat"]
    assert len(chat_spans) == 1
    attrs = dict(chat_spans[0].attributes)
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == orchestrator_sdk.settings.orchestrator_sdk_model
    assert attrs["gen_ai.usage.input_tokens"] == 500
    assert attrs["gen_ai.usage.output_tokens"] == 120
    assert attrs["gen_ai.usage.cost_usd"] == 0.0042


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_falls_back_to_last_assistant_text(
    _patch_mcp_builders, _patch_compose_prompt, tmp_path, monkeypatch
):
    """When ResultMessage.result is empty, concatenate TextBlocks from the last AssistantMessage."""
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-fallback-test")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock")

    messages = [
        AssistantMessage([_TextBlock("early draft — superseded")]),
        AssistantMessage([_TextBlock("final synthesis text")]),
        ResultMessage(result="", usage={"input_tokens": 1, "output_tokens": 2}),
    ]

    with patch("claude_agent_sdk.query", new=_make_mock_query(messages)):
        response = await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == "final synthesis text"


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_cleanup_runs_on_success(
    _patch_mcp_builders, _patch_compose_prompt, tmp_path, monkeypatch
):
    """Transcript anchor dir should be cleaned up after a successful call."""
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-cleanup-test")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock")

    messages = [ResultMessage(result="ok", usage={"input_tokens": 1, "output_tokens": 1})]

    with patch("claude_agent_sdk.query", new=_make_mock_query(messages)):
        await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )

    anchor_root = tmp_path / "orch-cleanup-test"
    if anchor_root.exists():
        for thread_dir in anchor_root.iterdir():
            assert list(thread_dir.iterdir()) == [], f"request dirs leaked under {thread_dir}"


# ---------------------------------------------------------------------------
# Error handling — all SDK exceptions must map to "" (never propagate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_cli_not_found_returns_empty(
    _patch_mcp_builders, _patch_compose_prompt, tmp_path, monkeypatch, caplog
):
    from claude_agent_sdk import CLINotFoundError
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-cli-notfound")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock")

    async def explode(prompt, options):
        raise CLINotFoundError("claude CLI missing")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=explode):
        response = await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == ""
    assert any("CLI not found" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_process_error_returns_empty(
    _patch_mcp_builders, _patch_compose_prompt, tmp_path, monkeypatch
):
    from claude_agent_sdk import ProcessError
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-process-err")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock")

    async def explode(prompt, options):
        raise ProcessError("subprocess blew up")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=explode):
        response = await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == ""


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_unexpected_exception_returns_empty(
    _patch_mcp_builders, _patch_compose_prompt, tmp_path, monkeypatch
):
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-unexpected-err")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock")

    async def explode(prompt, options):
        raise RuntimeError("something random")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=explode):
        response = await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == ""


@pytest.mark.asyncio
async def test_invoke_orchestrator_sdk_empty_messages_returns_empty(
    _patch_mcp_builders, _patch_compose_prompt, tmp_path, monkeypatch
):
    """Empty message history → skip query() entirely; return "" without calling SDK."""
    from src.agents import orchestrator_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "orch-empty-msgs")

    async def should_not_be_called(prompt, options):
        raise AssertionError("query() should not run with empty messages")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=should_not_be_called):
        response = await orchestrator_sdk.invoke_orchestrator_sdk(
            state={"messages": []},
            thread_id="u:c",
        )
    assert response == ""


# ---------------------------------------------------------------------------
# Governance guards — same invariants pinned for coder_sdk
# ---------------------------------------------------------------------------


def test_orchestrator_anthropic_api_key_blank_guard():
    """_build_options must enforce ANTHROPIC_API_KEY='' regardless of other settings.

    Prevents a future env-var refactor from re-enabling the x-api-key header
    (Portkey rejects it with HTTP 401). Matches
    ``test_coder_sdk.test_anthropic_api_key_blank_guard``.
    """
    from pathlib import Path

    from src.agents import orchestrator_sdk

    with (
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "looks-real"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
        patch(
            "src.agents.orchestrator_sdk.orchestrator_mcp_tool_names",
            return_value=[],
        ),
    ):
        options = orchestrator_sdk._build_options("sys-prompt", Path("/tmp/cwd"))

    env = options.env
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["ANTHROPIC_AUTH_TOKEN"] == "looks-real"
    assert "x-portkey-slug: bedrock" in env["ANTHROPIC_CUSTOM_HEADERS"]


def test_orchestrator_anthropic_base_url_has_no_trailing_v1():
    """_build_options must strip /v1 from ANTHROPIC_BASE_URL.

    Same /v1/v1/messages regression the Phase 1 coder path pinned —
    reintroducing the suffix here would have the SDK CLI produce
    .../v1/v1/messages and Portkey would return a Coral
    UnknownOperationException. The orchestrator prototype MUST use
    ``settings.portkey_anthropic_base_url``.
    """
    from pathlib import Path

    from src.agents import orchestrator_sdk

    with (
        patch.object(
            orchestrator_sdk.settings,
            "portkey_base_url",
            "https://gateway.example.com/v1",
        ),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
        patch(
            "src.agents.orchestrator_sdk.orchestrator_mcp_tool_names",
            return_value=[],
        ),
    ):
        options = orchestrator_sdk._build_options("sys-prompt", Path("/tmp/cwd"))

    base = options.env["ANTHROPIC_BASE_URL"]
    assert base == "https://gateway.example.com", (
        f"expected stripped root; got {base!r} — would produce /v1/v1/messages"
    )
    assert not base.endswith("/v1")


# ---------------------------------------------------------------------------
# Tool surface — allowed_tools includes the orchestrator-specific servers
# ---------------------------------------------------------------------------


def test_build_options_flat_mode_exposes_all_orchestrator_tools():
    """``ORCHESTRATOR_SDK_TOOL_MODE=flat`` → orchestrator sees the full
    14-tool surface directly (plus sub-agents).
    """
    from pathlib import Path

    from src.agents import orchestrator_sdk
    from src.service.mcp import ORCHESTRATOR_MCP_TOOL_NAMES

    with (
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch.object(orchestrator_sdk.settings, "orchestrator_sdk_tool_mode", "flat"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
    ):
        # Real tuple intentionally used so this test fails if
        # ORCHESTRATOR_MCP_TOOL_NAMES drifts from what flat mode exposes.
        options = orchestrator_sdk._build_options("sys", Path("/tmp/cwd"))

    assert set(options.allowed_tools) == set(ORCHESTRATOR_MCP_TOOL_NAMES)


def test_build_options_delegated_mode_exposes_no_direct_tools():
    """``ORCHESTRATOR_SDK_TOOL_MODE=delegated`` (default) → orchestrator's
    ``allowed_tools`` is empty so it can ONLY invoke TodoWrite + sub-agents.

    This pins the architectural contract: in delegated mode the
    orchestrator is a planner/router, not a tool-caller. All MCP tool
    calls happen inside a sub-agent's isolated conversation.
    """
    from pathlib import Path

    from src.agents import orchestrator_sdk

    with (
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch.object(orchestrator_sdk.settings, "orchestrator_sdk_tool_mode", "delegated"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
    ):
        options = orchestrator_sdk._build_options("sys", Path("/tmp/cwd"))

    # Empty allowed_tools → orchestrator cannot call any MCP tool directly;
    # sub-agents still work because they carry their own scoped tool lists
    # at the AgentDefinition level.
    assert options.allowed_tools == []
    # TodoWrite must still be in the builtin tools list regardless of mode.
    assert "TodoWrite" in options.tools
    # mcp_servers stays registered (sub-agents need them).
    # (build_all_orchestrator_servers is mocked above so we can only check presence)
    assert options.mcp_servers is not None


def test_build_options_invalid_mode_falls_back_to_delegated(caplog):
    """Unknown tool_mode → delegated with a warning. Pins the
    defensive-fallback behavior so a typo in .env doesn't hard-fail the
    request path.
    """
    import logging
    from pathlib import Path

    from src.agents import orchestrator_sdk

    with (
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch.object(orchestrator_sdk.settings, "orchestrator_sdk_tool_mode", "BOGUS"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
    ):
        with caplog.at_level(logging.WARNING, logger="src.agents.orchestrator_sdk"):
            options = orchestrator_sdk._build_options("sys", Path("/tmp/cwd"))

    assert options.allowed_tools == []  # delegated fallback
    assert any("BOGUS" in rec.message for rec in caplog.records)


def test_build_options_registers_agent_definitions():
    """The SDK orchestrator uses AgentDefinition for worker personas.

    Pin that _build_options ships a non-empty agents dict covering the
    two worker names the LangChain orchestrator routes to (coder /
    sql_agent). If this ever diverges, the prototype can't
    delegate work internally and the evaluation will show degraded
    plan-completion rate — flag it here before it hits the harness.
    """
    from pathlib import Path

    from src.agents import orchestrator_sdk

    with (
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
        patch(
            "src.agents.orchestrator_sdk.orchestrator_mcp_tool_names",
            return_value=[],
        ),
    ):
        options = orchestrator_sdk._build_options("sys", Path("/tmp/cwd"))

    assert set(options.agents.keys()) == {"coder", "sql_agent"}


def test_build_options_uses_todowrite_not_manage_plan():
    """Pin that the orchestrator SDK uses the SDK-native TodoWrite rather
    than the custom manage_plan tool.

    The explicit point of the prototype is that ``TodoWrite`` is
    sufficient and the ``~130 lines of defensive override`` code can go.
    If a future refactor silently re-adds manage_plan to ``tools=[...]``,
    the evaluation comparison stops being meaningful.
    """
    from pathlib import Path

    from src.agents import orchestrator_sdk

    with (
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(orchestrator_sdk.settings, "portkey_bedrock_slug", "bedrock"),
        patch(
            "src.agents.orchestrator_sdk.build_all_orchestrator_servers",
            return_value={},
        ),
        patch(
            "src.agents.orchestrator_sdk.orchestrator_mcp_tool_names",
            return_value=[],
        ),
    ):
        options = orchestrator_sdk._build_options("sys", Path("/tmp/cwd"))

    assert "TodoWrite" in options.tools
    assert "manage_plan" not in options.tools


# ---------------------------------------------------------------------------
# Prompt parity — the two orchestrator paths share compose_orchestrator_system_prompt
# ---------------------------------------------------------------------------


def test_compose_orchestrator_system_prompt_is_shared_between_backends():
    """compose_orchestrator_system_prompt MUST be the single source of truth.

    The SDK prototype imports it directly from src.agents.orchestrator —
    if any future refactor hand-rolls a separate prompt string inside
    orchestrator_sdk.py, the evaluation comparison is tainted.
    """
    from src.agents.orchestrator import compose_orchestrator_system_prompt as from_langchain
    from src.agents.orchestrator_sdk import compose_orchestrator_system_prompt as from_sdk

    assert from_langchain is from_sdk, (
        "Both orchestrator backends must share compose_orchestrator_system_prompt. "
        "A divergent helper breaks the prompt-parity invariant Workstream B's "
        "ADR relies on."
    )


# ---------------------------------------------------------------------------
# Serialization parity with coder_sdk
# ---------------------------------------------------------------------------


def test_serialize_messages_preserves_order_and_roles_orchestrator():
    from src.agents.orchestrator_sdk import _serialize_messages_for_sdk

    msgs = [
        HumanMessage(content="user Q"),
        AIMessage(content="coder summary", name="coder"),
        HumanMessage(content="[Orchestrator] next step", name="orchestrator_task"),
    ]
    out = _serialize_messages_for_sdk(msgs)
    assert "<<<human>>>" in out
    assert "<<<ai:coder>>>" in out
    assert "<<<human:orchestrator_task>>>" in out
    # Order preserved
    assert out.find("user Q") < out.find("coder summary") < out.find("next step")


def test_serialize_messages_empty_input_returns_empty_string_orchestrator():
    from src.agents.orchestrator_sdk import _serialize_messages_for_sdk

    assert _serialize_messages_for_sdk([]) == ""
