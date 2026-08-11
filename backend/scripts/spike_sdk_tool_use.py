"""Phase 1 pre-phase Spike 1 — tool_use content blocks through Portkey.

Extends ``spike_portkey_bedrock.py`` Test 3 with a single in-process MCP tool
wrapped via ``@tool`` + ``create_sdk_mcp_server``. Confirms that when the model
is told to call the tool, Portkey proxies both directions end-to-end:

- outbound: ``AssistantMessage.content`` includes a ``ToolUseBlock``
- inbound:  ``UserMessage.content`` carries back a ``ToolResultBlock``
- final:    ``ResultMessage`` has non-zero usage and a sensible ``result``

Phase 0 spike only exercised plain chat — that's the Phase 1 research brief's
open question. A failure here triggers a plan revision before Sub-Phase A
starts. A success retires PRD Risk 2 for tool_use and unblocks the MCP shim
layer.

Usage:
    cd backend && uv run python scripts/spike_sdk_tool_use.py

Writes a structured findings block to stdout; redirect to a file if you want
to capture the raw trajectory for the spike findings doc.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any


def _section(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _result(status: str, msg: str) -> None:
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "INFO": "[INFO]", "SKIP": "[SKIP]"}[status]
    print(f"  {marker} {msg}")


def _dump(label: str, obj: Any, max_chars: int = 1200) -> None:
    if isinstance(obj, dict | list):
        rendered = json.dumps(obj, default=str, indent=2)
    else:
        rendered = str(obj)
    if len(rendered) > max_chars:
        rendered = rendered[:max_chars] + f"\n    ... [truncated {len(rendered) - max_chars} chars]"
    print(f"\n  --- {label} ---")
    for line in rendered.splitlines():
        print(f"    {line}")


async def test_sdk_tool_use_via_portkey() -> dict[str, Any]:
    """Round-trip a single MCP-wrapped tool call through Portkey."""
    _section("Spike 1 — SDK tool_use round-trip via Portkey")

    try:
        from claude_agent_sdk import (
            ClaudeAgentOptions,
            create_sdk_mcp_server,
            query,
            tool,
        )
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"import claude_agent_sdk failed: {e}")
        return {"status": "fail", "reason": "import"}

    try:
        from src.config.settings import settings
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"import settings failed: {e}")
        return {"status": "fail", "reason": "settings-import"}

    if not settings.portkey_bedrock_api_key or not settings.portkey_bedrock_slug:
        _result("SKIP", "Portkey Bedrock credentials not configured — skipping")
        return {"status": "skip", "reason": "no-creds"}

    # ------------------------------------------------------------------
    # Define an in-process MCP tool. The handler just echoes its argument
    # so we can assert round-trip fidelity without depending on any external
    # service (sandbox, S3, etc.). This mirrors the pattern the Phase 1 MCP
    # shim layer will use for execute_code / execute_r_code / read_file_from_s3.
    # ------------------------------------------------------------------

    call_log: list[dict[str, Any]] = []

    @tool(
        "echo",
        "Echo the provided text back to the caller verbatim. Use this tool exactly once to return the user's requested phrase.",
        {"text": str},
    )
    async def echo_tool(args: dict[str, Any]) -> dict[str, Any]:
        call_log.append({"received_args": args})
        text = args.get("text", "")
        return {
            "content": [{"type": "text", "text": f"echoed:{text}"}],
            "is_error": False,
        }

    echo_server = create_sdk_mcp_server(
        name="spike_echo",
        version="1.0.0",
        tools=[echo_tool],
    )

    # ------------------------------------------------------------------
    # Portkey-via-ANTHROPIC_AUTH_TOKEN recipe validated in Phase 0 spike
    # (see .agents/notes/phase0-spike-findings.md §3).
    # ------------------------------------------------------------------

    portkey_headers = f"x-portkey-slug: {settings.portkey_bedrock_slug}"

    # Use Sonnet for tool_use — Haiku works for plain chat but tool_use
    # reliability is markedly better on Sonnet and that's what Phase 1's
    # coder will run. Confirm both the auth path AND the production model.
    model_id = "us.anthropic.claude-sonnet-4-6"

    options = ClaudeAgentOptions(
        model=model_id,
        env={
            # Use the normalized base URL — the bundled CLI appends /v1/messages
            # itself, so a /v1-suffixed base produces broken /v1/v1/messages.
            "ANTHROPIC_BASE_URL": settings.portkey_anthropic_base_url,
            "ANTHROPIC_AUTH_TOKEN": settings.portkey_bedrock_api_key,
            "ANTHROPIC_CUSTOM_HEADERS": portkey_headers,
            "ANTHROPIC_API_KEY": "",  # blank to prevent x-api-key fallback
        },
        # Kill all Claude Code builtins; expose only our MCP tool.
        tools=[],
        allowed_tools=["mcp__spike_echo__echo"],
        mcp_servers={"spike_echo": echo_server},
        max_turns=5,
        permission_mode="bypassPermissions",
        system_prompt=(
            "You have access to a single tool: mcp__spike_echo__echo. "
            'You MUST call it exactly once with the argument text="pong", '
            "then reply with a one-sentence summary of what the tool returned. "
            "Do not skip the tool call."
        ),
        include_partial_messages=False,
    )

    _result("INFO", f"model: {model_id}")
    _result("INFO", "allowed tools: mcp__spike_echo__echo only (tools=[])")

    trajectory: list[dict[str, Any]] = []
    saw_tool_use = False
    saw_tool_result = False
    final_result_preview: str | None = None
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None

    try:
        t0 = time.perf_counter()
        async for msg in query(prompt="Please say pong back to me.", options=options):
            msg_type = type(msg).__name__
            entry: dict[str, Any] = {"type": msg_type}

            # AssistantMessage.content is a list of content blocks; ToolUseBlock
            # here is the confirmation that Portkey proxied the tool_use shape.
            content = getattr(msg, "content", None)
            if content:
                block_summaries = []
                for block in content:
                    block_type = type(block).__name__
                    summary: dict[str, Any] = {"block_type": block_type}
                    if hasattr(block, "text"):
                        summary["text"] = getattr(block, "text", "")[:300]
                    if hasattr(block, "name"):
                        summary["name"] = getattr(block, "name", "")
                    if hasattr(block, "input"):
                        summary["input"] = getattr(block, "input", {})
                    if hasattr(block, "tool_use_id"):
                        summary["tool_use_id"] = getattr(block, "tool_use_id", "")
                    if hasattr(block, "content"):
                        # ToolResultBlock.content is a list of content blocks
                        summary["content"] = [
                            getattr(b, "text", str(b))[:300]
                            for b in (getattr(block, "content", None) or [])
                        ]
                    block_summaries.append(summary)
                    if block_type == "ToolUseBlock":
                        saw_tool_use = True
                    if block_type == "ToolResultBlock":
                        saw_tool_result = True
                entry["blocks"] = block_summaries

            if hasattr(msg, "result"):
                final_result_preview = str(getattr(msg, "result") or "")[:300]
                entry["result_preview"] = final_result_preview
            if hasattr(msg, "usage"):
                usage = getattr(msg, "usage", None) or {}
                entry["usage"] = usage
            if hasattr(msg, "total_cost_usd"):
                cost_usd = getattr(msg, "total_cost_usd", None)
                entry["total_cost_usd"] = cost_usd

            trajectory.append(entry)

        elapsed_ms = (time.perf_counter() - t0) * 1000
    except Exception as e:  # noqa: BLE001
        _result("FAIL", f"query() raised {type(e).__name__}: {e}")
        _dump("trajectory so far", trajectory)
        _dump("tool call log", call_log)
        return {
            "status": "fail",
            "reason": "query-exception",
            "error": f"{type(e).__name__}: {e}",
            "trajectory": trajectory,
            "call_log": call_log,
        }

    _dump("trajectory", trajectory)
    _dump("tool call log", call_log)

    # ------------------------------------------------------------------
    # Acceptance gates
    # ------------------------------------------------------------------

    checks = {
        "tool_use_block_observed": saw_tool_use,
        "tool_result_block_observed": saw_tool_result,
        "tool_handler_was_invoked": len(call_log) >= 1,
        "result_message_received": final_result_preview is not None,
        "usage_populated": bool(usage and (usage.get("input_tokens") or usage.get("inputTokens"))),
    }

    all_pass = all(checks.values())

    _section("Spike 1 — acceptance")
    for k, v in checks.items():
        _result("PASS" if v else "FAIL", f"{k}: {v}")
    _result("INFO", f"latency: {elapsed_ms:.0f}ms")
    _result("INFO", f"cost_usd (ResultMessage): {cost_usd}")

    return {
        "status": "pass" if all_pass else "fail",
        "checks": checks,
        "latency_ms": elapsed_ms,
        "model": model_id,
        "final_result_preview": final_result_preview,
        "usage": usage,
        "total_cost_usd": cost_usd,
        "trajectory": trajectory,
        "call_log": call_log,
    }


async def _main() -> int:
    # backend/ must be importable so `from src.config.settings import settings` works
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    summary = await test_sdk_tool_use_via_portkey()

    _section("Spike 1 — summary")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in {"trajectory", "call_log"}},
            default=str,
            indent=2,
        )
    )
    return 0 if summary.get("status") == "pass" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
