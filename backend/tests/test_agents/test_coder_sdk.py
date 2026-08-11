"""Tests for agents.coder_sdk.invoke_coder_sdk."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


# ---------------------------------------------------------------------------
# Fake SDK message classes — shaped like the real ones enough for our asserts
# ---------------------------------------------------------------------------


class _TextBlock:
    def __init__(self, text: str):
        self.text = text


# The SDK's real classes are named AssistantMessage / ResultMessage —
# invoke_coder_sdk dispatches on type(msg).__name__, so our fakes must
# use the same names (no leading underscore).
class AssistantMessage:  # noqa: N801 — intentional mirror of SDK name
    def __init__(self, blocks):
        self.content = blocks


class ResultMessage:  # noqa: N801
    def __init__(self, result: str, usage: dict | None = None, total_cost_usd: float | None = None):
        self.result = result
        self.usage = usage
        self.total_cost_usd = total_cost_usd


def _make_mock_query(messages: list[Any]):
    """Return a mock ``query()`` that yields the given messages in order."""

    async def fake_query(prompt: str, options: Any):
        for m in messages:
            yield m

    return fake_query


@pytest.fixture
def _patch_mcp_builders():
    """Avoid building the real MCP servers during tests (they work, but slow)."""
    with (
        patch(
            "src.agents.coder_sdk.build_all_coder_servers",
            return_value={"sandbox": {"type": "sdk"}, "s3": {}, "file_ops": {}},
        ),
        patch(
            "src.agents.coder_sdk.mcp_tool_names",
            return_value=["mcp__sandbox__execute_code"],
        ),
    ):
        yield


@pytest.mark.asyncio
async def test_invoke_coder_sdk_success(
    in_memory_span_exporter, _patch_mcp_builders, tmp_path, monkeypatch
):
    """Happy path: query yields AssistantMessage + ResultMessage — final text returned."""
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "coder-sdk-test")
    # Make sure a portkey key is considered present so ANTHROPIC_AUTH_TOKEN isn't blank
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_api_key", "fake-key")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_slug", "bedrock")

    usage = {"input_tokens": 100, "output_tokens": 25}
    messages = [
        AssistantMessage([_TextBlock("done")]),
        ResultMessage(result="done", usage=usage, total_cost_usd=0.001),
    ]

    with patch("claude_agent_sdk.query", new=_make_mock_query(messages)):
        response = await coder_sdk.invoke_coder_sdk(
            user_id="u1",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u1:c1",
        )

    assert response == "done"

    # gen_ai.chat span emitted with all 5 required attributes
    spans = in_memory_span_exporter.get_finished_spans()
    chat_spans = [s for s in spans if s.name == "gen_ai.chat"]
    assert len(chat_spans) == 1
    attrs = dict(chat_spans[0].attributes)
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == coder_sdk.settings.coder_sdk_model
    assert attrs["gen_ai.usage.input_tokens"] == 100
    assert attrs["gen_ai.usage.output_tokens"] == 25
    assert attrs["gen_ai.usage.cost_usd"] == 0.001


@pytest.mark.asyncio
async def test_invoke_coder_sdk_falls_back_to_last_assistant_text(
    in_memory_span_exporter, _patch_mcp_builders, tmp_path, monkeypatch
):
    """When ResultMessage.result is empty, concatenate TextBlocks from last AssistantMessage."""
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "fallback-test")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_slug", "bedrock")

    messages = [
        AssistantMessage([_TextBlock("earlier response — superseded")]),
        AssistantMessage([_TextBlock("final answer here")]),
        ResultMessage(result="", usage={"input_tokens": 1, "output_tokens": 2}),
    ]

    with patch("claude_agent_sdk.query", new=_make_mock_query(messages)):
        response = await coder_sdk.invoke_coder_sdk(
            user_id="u",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == "final answer here"


@pytest.mark.asyncio
async def test_invoke_coder_sdk_cleanup_runs_on_success(_patch_mcp_builders, tmp_path, monkeypatch):
    """Transcript anchor + projects dir must be gone after a successful call."""
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "cleanup-test-success")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_slug", "bedrock")

    messages = [ResultMessage(result="ok", usage={"input_tokens": 1, "output_tokens": 1})]

    with patch("claude_agent_sdk.query", new=_make_mock_query(messages)):
        await coder_sdk.invoke_coder_sdk(
            user_id="u",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )

    # No leftover anchor dirs under tmp_path/instance_id/
    anchor_root = tmp_path / "cleanup-test-success"
    if anchor_root.exists():
        # Any thread subdirs should be empty of request dirs
        for thread_dir in anchor_root.iterdir():
            assert list(thread_dir.iterdir()) == [], f"request dirs leaked under {thread_dir}"


@pytest.mark.asyncio
async def test_invoke_coder_sdk_cli_not_found_returns_empty(
    _patch_mcp_builders, tmp_path, monkeypatch, caplog
):
    """CLINotFoundError must be caught and return '' — matches LangChain-path empty-on-failure."""
    from claude_agent_sdk import CLINotFoundError
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "cli-notfound-test")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_slug", "bedrock")

    async def explode(prompt, options):
        raise CLINotFoundError("claude CLI missing")
        yield  # pragma: no cover — makes it a generator

    with patch("claude_agent_sdk.query", new=explode):
        response = await coder_sdk.invoke_coder_sdk(
            user_id="u",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == ""
    assert any("CLI not found" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_invoke_coder_sdk_process_error_returns_empty(
    _patch_mcp_builders, tmp_path, monkeypatch
):
    from claude_agent_sdk import ProcessError
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "process-err-test")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_slug", "bedrock")

    async def explode(prompt, options):
        raise ProcessError("subprocess blew up")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=explode):
        response = await coder_sdk.invoke_coder_sdk(
            user_id="u",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == ""


@pytest.mark.asyncio
async def test_invoke_coder_sdk_unexpected_exception_returns_empty(
    _patch_mcp_builders, tmp_path, monkeypatch
):
    """A completely unknown exception must still be caught (never raises)."""
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "unexpected-err-test")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_api_key", "k")
    monkeypatch.setattr(coder_sdk.settings, "portkey_bedrock_slug", "bedrock")

    async def explode(prompt, options):
        raise RuntimeError("something random")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=explode):
        response = await coder_sdk.invoke_coder_sdk(
            user_id="u",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content="hi")]},
            thread_id="u:c",
        )
    assert response == ""


@pytest.mark.asyncio
async def test_invoke_coder_sdk_empty_messages_returns_empty(
    _patch_mcp_builders, tmp_path, monkeypatch
):
    from src.agents import coder_sdk
    from src.service import sdk_runtime

    monkeypatch.setattr(sdk_runtime.settings, "sdk_transcript_root", str(tmp_path))
    monkeypatch.setattr(sdk_runtime, "_INSTANCE_ID", "empty-msgs-test")

    # query() must not be called because history is empty; patch it to fail loud if it is.
    async def should_not_be_called(prompt, options):
        raise AssertionError("query() should not be called when messages is empty")
        yield  # pragma: no cover

    with patch("claude_agent_sdk.query", new=should_not_be_called):
        response = await coder_sdk.invoke_coder_sdk(
            user_id="u",
            project_snippets=None,
            code_language="python",
            state={"messages": []},
            thread_id="u:c",
        )
    assert response == ""


# ---------------------------------------------------------------------------
# Task 19b — ANTHROPIC_API_KEY leakage guard
# ---------------------------------------------------------------------------


def test_anthropic_api_key_blank_guard():
    """_build_options must enforce ANTHROPIC_API_KEY='' regardless of other settings.

    Prevents a future env-var refactor from silently re-enabling the
    x-api-key header (Portkey rejects it with HTTP 401).
    """
    from pathlib import Path
    from src.agents import coder_sdk

    # Patch settings to something that looks like a real key — the guard
    # must still force ANTHROPIC_API_KEY="" in the env overlay.
    with (
        patch.object(coder_sdk.settings, "portkey_bedrock_api_key", "a-real-looking-key"),
        patch.object(coder_sdk.settings, "portkey_bedrock_slug", "bedrock"),
    ):
        options = coder_sdk._build_options("sys-prompt", Path("/tmp/cwd"), "python")
    env = options.env
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["ANTHROPIC_AUTH_TOKEN"] == "a-real-looking-key"
    assert "x-portkey-slug: bedrock" in env["ANTHROPIC_CUSTOM_HEADERS"]


def test_anthropic_base_url_has_no_trailing_v1():
    """_build_options must strip the /v1 suffix from ANTHROPIC_BASE_URL.

    Regression for the 2026-05-08 container diagnosis: a /v1-suffixed base URL
    causes the bundled CLI to request .../v1/v1/messages, which Portkey forwards
    to Bedrock as a Coral UnknownOperationException. Uses
    settings.portkey_anthropic_base_url to enforce the invariant.
    """
    from pathlib import Path
    from src.agents import coder_sdk

    # Patch the raw value to the canonical /v1-suffixed form
    with (
        patch.object(
            coder_sdk.settings,
            "portkey_base_url",
            "https://gateway.example.com/v1",
        ),
        patch.object(
            coder_sdk.settings,
            "portkey_bedrock_api_key",
            "k",
        ),
        patch.object(
            coder_sdk.settings,
            "portkey_bedrock_slug",
            "bedrock",
        ),
    ):
        options = coder_sdk._build_options("sys-prompt", Path("/tmp/cwd"), "python")

    base = options.env["ANTHROPIC_BASE_URL"]
    # Base must be the gateway root, not /v1-suffixed.
    assert base == "https://gateway.example.com", (
        f"expected stripped root; got {base!r} — will produce /v1/v1/messages "
        "when the CLI appends /v1/messages"
    )
    assert not base.endswith("/v1"), (
        f"ANTHROPIC_BASE_URL must NOT end in /v1 (got {base!r}); "
        "the Claude Agent SDK CLI appends /v1/messages itself"
    )


# ---------------------------------------------------------------------------
# Tool-surface parity with LangChain coder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code_language, expect_python_tool, expect_r_tool",
    [
        ("python", True, False),
        ("r", False, True),
        ("auto", True, True),
    ],
)
def test_build_options_allowed_tools_respects_code_language(
    code_language, expect_python_tool, expect_r_tool
):
    """_build_options must scope allowed_tools to match the LangChain tool
    filter for the same code_language — parity invariant flagged by the
    Codex adversarial review.
    """
    from pathlib import Path
    from src.agents import coder_sdk

    with (
        patch.object(coder_sdk.settings, "portkey_bedrock_api_key", "k"),
        patch.object(coder_sdk.settings, "portkey_bedrock_slug", "bedrock"),
    ):
        options = coder_sdk._build_options("sys", Path("/tmp/cwd"), code_language)

    allowed = set(options.allowed_tools)
    assert ("mcp__sandbox__execute_code" in allowed) is expect_python_tool
    assert ("mcp__sandbox__execute_r_code" in allowed) is expect_r_tool
    # Non-language-gated tools always present
    assert "mcp__s3__read_file_from_s3" in allowed
    assert "mcp__file_ops__list_files_by_thread" in allowed


# ---------------------------------------------------------------------------
# Serialization parity
# ---------------------------------------------------------------------------


def test_serialize_messages_preserves_order_and_roles():
    from src.agents.coder_sdk import _serialize_messages_for_sdk

    msgs = [
        HumanMessage(content="user Q"),
        AIMessage(content="orchestrator plan", name="orchestrator"),
        HumanMessage(content="[Orchestrator Task] do X", name="orchestrator_task"),
    ]
    out = _serialize_messages_for_sdk(msgs)
    # Order preserved
    user_idx = out.find("user Q")
    orch_idx = out.find("orchestrator plan")
    task_idx = out.find("do X")
    assert 0 <= user_idx < orch_idx < task_idx
    # Roles tagged
    assert "<<<human>>>" in out
    assert "<<<ai:orchestrator>>>" in out
    assert "<<<human:orchestrator_task>>>" in out


def test_serialize_messages_empty_input_returns_empty_string():
    from src.agents.coder_sdk import _serialize_messages_for_sdk

    assert _serialize_messages_for_sdk([]) == ""
