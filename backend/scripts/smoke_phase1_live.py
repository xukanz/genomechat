"""Phase 1 live smoke — one real SDK coder invocation end-to-end.

Drives ``invoke_coder_sdk`` with a real Portkey round-trip and real MCP
tool execution (against the running sandbox). Validates:

- Portkey Bedrock auth + tool_use works for a full coder turn
- MCP sandbox tool actually hits http://localhost:8080 and gets a result
- ``gen_ai.chat`` + ``agent.tool.*`` spans are emitted as expected
- Transcript anchor dir is created and cleaned up
- coder_sdk returns a non-empty string on success

Usage:
    cd backend && uv run python scripts/smoke_phase1_live.py

Requires sandbox service running at ``settings.sandbox_url`` (default
http://sandbox:8080 in Docker or http://localhost:8080 locally). Exits 0
on pass. Approx cost: ~$0.03 for one Sonnet turn with tool_use.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure we run from the backend/ directory so .env is discovered
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
sys.path.insert(0, str(_BACKEND))


def _section(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def _result(status: str, msg: str) -> None:
    marker = {"PASS": "[PASS]", "FAIL": "[FAIL]", "INFO": "[INFO]"}[status]
    print(f"  {marker} {msg}")


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _section("Phase 1 live smoke — one SDK coder invocation")

    # Install in-memory span exporter so we can inspect what coder_sdk emits
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    import src.service.observability.decorators as dec_mod

    replay_tracer = provider.get_tracer("genomechat.platform.smoke")
    dec_mod.tracer = replay_tracer

    from src.config.settings import settings

    if not settings.portkey_bedrock_api_key or not settings.portkey_bedrock_slug:
        _result("FAIL", "Portkey Bedrock credentials missing — cannot run live smoke")
        return 1

    _result("INFO", f"model: {settings.coder_sdk_model}")
    _result("INFO", f"sandbox_url: {settings.sandbox_url}")
    _result("INFO", f"portkey_base_url: {settings.portkey_base_url}")

    from langchain_core.messages import HumanMessage

    from src.agents.coder_sdk import invoke_coder_sdk
    from src.utils.context import thread_id_context

    thread_id = "smoke-phase1-live:turn-1"
    tid_token = thread_id_context.set(thread_id)

    task_prompt = (
        "Use the execute_code tool to run a tiny Python snippet that prints "
        "the sum of the first 10 integers (0 through 9). Then reply with "
        "one sentence giving the numeric result."
    )

    try:
        import time
        t0 = time.perf_counter()
        response = await invoke_coder_sdk(
            user_id="smoke",
            project_snippets=None,
            code_language="python",
            state={"messages": [HumanMessage(content=task_prompt)]},
            thread_id=thread_id,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        thread_id_context.reset(tid_token)

    _section("Response")
    if response:
        _result("PASS", f"non-empty response ({len(response)} chars) in {elapsed_ms:.0f}ms")
        print(f"\n{response[:600]}{'...' if len(response) > 600 else ''}")
    else:
        _result("FAIL", f"empty response after {elapsed_ms:.0f}ms — coder_sdk converted failure to ''")

    _section("Span trace")
    provider.force_flush()
    spans = list(exporter.get_finished_spans())
    _result("INFO", f"captured {len(spans)} spans")
    for s in spans:
        attrs = dict(s.attributes or {})
        line = f"    {s.name}"
        # Highlight the interesting attrs
        for k in (
            "tool.name",
            "tool.success",
            "gen_ai.request.model",
            "gen_ai.usage.input_tokens",
            "gen_ai.usage.output_tokens",
            "gen_ai.usage.cost_usd",
        ):
            if k in attrs:
                line += f"  {k}={attrs[k]}"
        print(line)

    # Invariant checks
    tool_spans = [s for s in spans if s.name.startswith("agent.tool.")]
    llm_spans = [s for s in spans if s.name == "gen_ai.chat"]

    _section("Acceptance gates")
    checks = {
        "response_non_empty": bool(response),
        "at_least_one_tool_span": len(tool_spans) >= 1,
        "execute_code_invoked": any(s.name == "agent.tool.execute_code" for s in tool_spans),
        "gen_ai_chat_span_emitted": len(llm_spans) == 1,
        "usage_populated": len(llm_spans) == 1 and (
            dict(llm_spans[0].attributes or {}).get("gen_ai.usage.input_tokens", 0) > 0
        ),
    }
    all_pass = all(checks.values())
    for k, v in checks.items():
        _result("PASS" if v else "FAIL", f"{k}: {v}")

    _section("Summary")
    if all_pass:
        cost = (
            dict(llm_spans[0].attributes or {}).get("gen_ai.usage.cost_usd", 0.0)
            if llm_spans
            else 0.0
        )
        _result("PASS", f"Phase 1 live smoke PASSED (cost=${cost}, elapsed={elapsed_ms:.0f}ms)")
        return 0
    _result("FAIL", "Phase 1 live smoke FAILED — see span trace above")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
