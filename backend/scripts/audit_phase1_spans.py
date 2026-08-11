"""Phase 1 span-schema audit.

Runs the SDK coder path under in-memory OTel capture and asserts every
span emitted matches the minimum-commitment schema in
``docs/backend/phase0_phase1_contract.md``. Fails fast if Phase 1
introduced a drift.

Usage::

    cd backend && uv run python scripts/audit_phase1_spans.py

Exits 0 on PASS, 1 on any schema drift.

The check is intentionally strict on **required keys** and tolerant of
extras (e.g. ``active_skills``). Any new attribute on a locked-in span
type means the contract's ``schema_version`` must be bumped — a human
decision, not automation.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Minimum-commitment schema from docs/backend/phase0_phase1_contract.md §15–45
REQUIRED_NODE_ATTRS: frozenset[str] = frozenset({
    "agent.name",
    "agent.backend",
    "agent.thread_id",
    "agent.database_id",
    "agent.research_mode",
    "agent.code_language",
    "active_skills",
})

REQUIRED_TOOL_ATTRS: frozenset[str] = frozenset({
    "tool.name",
    "tool.args_hash",
    "tool.success",
})

REQUIRED_LLM_ATTRS: frozenset[str] = frozenset({
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.cost_usd",
})


def _pass(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


async def _capture_sdk_coder_spans() -> list[Any]:
    """Drive one SDK coder replay with canned messages and return the spans."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from types import SimpleNamespace
    from langchain_core.messages import HumanMessage

    from src.config.settings import settings
    from src.service import sdk_runtime
    from evaluation import harness as harness_mod

    # Canned SDK messages — match the shape _TextBlock/AssistantMessage/ResultMessage
    class _TextBlock:
        def __init__(self, text: str):
            self.text = text

    class AssistantMessage:  # noqa: N801
        def __init__(self, blocks):
            self.content = blocks

    class ResultMessage:  # noqa: N801
        def __init__(self, result, usage, total_cost_usd):
            self.result = result
            self.usage = usage
            self.total_cost_usd = total_cost_usd

    canned = [
        AssistantMessage([_TextBlock("audit-response")]),
        ResultMessage(
            result="audit-response",
            usage={"input_tokens": 7, "output_tokens": 3},
            total_cost_usd=0.0001,
        ),
    ]

    async def fake_query(prompt, options):
        for m in canned:
            yield m

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def fake_saver(conn_string: str):
        yield object()

    class _DirectAgent:
        async def ainvoke(self, state, config=None):
            from src.graph.nodes import coder_node

            state_payload = {
                "messages": [HumanMessage(content="audit")],
                "thread_id": "audit:r",
                "database_id": "clinvar",
                "project_id": "",
                "research_mode": "standard",
                "code_language": "python",
            }
            cmd = await coder_node(state_payload)
            coder_msg = cmd.update["messages"][0]
            return {"messages": [SimpleNamespace(type="ai", content=coder_msg.content)]}

    class _DirectBuilder:
        def compile(self, checkpointer=None):
            return _DirectAgent()

    # Install saver + builder patches
    from langgraph.checkpoint.sqlite import aio as saver_mod

    settings.coder_backend = "langchain"  # baseline — replay flips it
    if not settings.portkey_bedrock_api_key:
        settings.portkey_bedrock_api_key = "audit-fake-key"
    if not settings.portkey_bedrock_slug:
        settings.portkey_bedrock_slug = "bedrock"

    original_builder = harness_mod.build_graph
    original_saver = saver_mod.AsyncSqliteSaver.from_conn_string

    harness_mod.build_graph = lambda: _DirectBuilder()
    saver_mod.AsyncSqliteSaver.from_conn_string = staticmethod(fake_saver)  # type: ignore[assignment]

    try:
        with patch("claude_agent_sdk.query", new=fake_query), patch(
            "src.agents.coder_sdk.build_all_coder_servers",
            return_value={"sandbox": {}, "s3": {}, "file_ops": {}},
        ), patch(
            "src.agents.coder_sdk.mcp_tool_names",
            return_value=["mcp__sandbox__execute_code"],
        ):
            result = await harness_mod.replay(
                {"query": "audit", "thread_id": "audit:r"},
                backend="sdk",
            )
        return result.spans
    finally:
        harness_mod.build_graph = original_builder
        saver_mod.AsyncSqliteSaver.from_conn_string = staticmethod(original_saver)  # type: ignore[assignment]


def _audit_node_span(span: dict[str, Any]) -> bool:
    attrs = set(span["attributes"].keys())
    missing = REQUIRED_NODE_ATTRS - attrs
    if missing:
        _fail(f"node span {span['name']!r} missing attrs: {sorted(missing)}")
        return False
    # Extra attrs on node spans are a contract violation per §46 (schema_version bump)
    extras = attrs - REQUIRED_NODE_ATTRS
    if extras:
        _fail(
            f"node span {span['name']!r} has UNDECLARED attrs: {sorted(extras)} "
            f"— schema_version bump required per phase0_phase1_contract.md"
        )
        return False
    _pass(f"node span {span['name']!r} schema matches")
    return True


def _audit_tool_span(span: dict[str, Any]) -> bool:
    attrs = set(span["attributes"].keys())
    missing = REQUIRED_TOOL_ATTRS - attrs
    if missing:
        _fail(f"tool span {span['name']!r} missing attrs: {sorted(missing)}")
        return False
    _pass(f"tool span {span['name']!r} has required attrs")
    return True


def _audit_llm_span(span: dict[str, Any]) -> bool:
    attrs = set(span["attributes"].keys())
    missing = REQUIRED_LLM_ATTRS - attrs
    if missing:
        _fail(f"gen_ai.chat span missing attrs: {sorted(missing)}")
        return False
    _pass("gen_ai.chat span has required attrs")
    return True


def audit(spans: list[dict[str, Any]]) -> int:
    node_spans = [s for s in spans if s["name"].startswith("agent.node.")]
    tool_spans = [s for s in spans if s["name"].startswith("agent.tool.")]
    llm_spans = [s for s in spans if s["name"] == "gen_ai.chat"]

    if not node_spans:
        _fail("expected at least one agent.node.* span — got none")
        return 1
    if not llm_spans:
        _fail("expected at least one gen_ai.chat span — got none")
        return 1

    sdk_node_spans = [
        s for s in node_spans if s["attributes"].get("agent.backend") == "sdk"
    ]
    if not sdk_node_spans:
        _fail("no agent.node.* span carried agent.backend=sdk — dispatch may be broken")
        return 1

    ok = True
    for s in node_spans:
        ok &= _audit_node_span(s)
    for s in tool_spans:
        ok &= _audit_tool_span(s)
    for s in llm_spans:
        ok &= _audit_llm_span(s)

    return 0 if ok else 1


def main() -> int:
    print("\n" + "=" * 70)
    print("  Phase 1 span-schema audit")
    print("=" * 70)
    print("  (runs coder_sdk under canned responses, asserts span shapes)")

    spans = asyncio.run(_capture_sdk_coder_spans())
    print(f"  captured {len(spans)} spans")

    rc = audit(spans)

    print("\n" + "=" * 70)
    print(f"  audit: {'PASS' if rc == 0 else 'FAIL'}")
    print("=" * 70)

    # Print span tree for quick visual inspection on FAIL
    if rc != 0:
        print("\n  Span tree snapshot:")
        for s in spans:
            print(f"    - {s['name']}: {sorted(s['attributes'].keys())}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
