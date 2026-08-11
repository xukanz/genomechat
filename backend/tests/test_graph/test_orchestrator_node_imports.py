"""Regression test — orchestrator_node must not shadow module-level imports.

Pins the fix for an UnboundLocalError that shipped in Workstream B: a
``from langchain_core.messages import AIMessage`` inside the SDK branch
made ``AIMessage`` a local variable in the entire function, which made
the LangChain branch at line ~613 raise
``UnboundLocalError: cannot access local variable 'AIMessage'`` whenever
the SDK branch didn't run first (= every LangChain-orchestrator request).

The fix is to NOT re-import names that are already imported at module
level. This test walks the orchestrator_node function's AST to catch
any future re-import inside the function body before it reaches prod.
"""

from __future__ import annotations

import ast
import inspect

# Names that MUST stay module-level only — importing them inside the
# function body shadows the module import and causes UnboundLocalError
# in branches where the inner import didn't execute.
_PROTECTED_NAMES = {
    "AIMessage",
    "HumanMessage",
    "SystemMessage",
    "Command",
    "trim_messages",
}


def test_orchestrator_node_does_not_reimport_protected_names():
    from src.graph.nodes import orchestrator_node

    src = inspect.getsource(orchestrator_node)
    tree = ast.parse(src.strip())

    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                local_name = alias.asname or alias.name
                if local_name in _PROTECTED_NAMES:
                    offenders.append((node.lineno, local_name))

    assert not offenders, (
        f"orchestrator_node re-imports protected names inside the function: "
        f"{offenders!r}. These must come from the module-level imports at "
        f"the top of src/graph/nodes.py to avoid UnboundLocalError on "
        f"branches where the inner import doesn't execute. "
        f"See the 2026-05-13 orchestrator_node hotfix for the backstory."
    )


def test_orchestrator_node_uses_module_level_aimessage():
    """Sanity: AIMessage is bound at module level in src.graph.nodes."""
    import src.graph.nodes as nodes_mod

    assert hasattr(nodes_mod, "AIMessage"), (
        "src.graph.nodes must import AIMessage at module level so both "
        "the LangChain and SDK branches of orchestrator_node can use it."
    )


def test_orchestrator_sdk_branch_clears_plan_and_todos():
    """SDK branch must clear plan/todos in its Command.update.

    Otherwise the previous LangChain turn's plan persists in the checkpoint
    and renders visibly stale through the next SDK turn (the SSE pipeline at
    chat.py reads ``snapshot.plan`` first, then ``snapshot.todos``).
    The SDK orchestrator drives its own TodoWrite plan internally and does
    not surface it back into AgentState — Phase 3 prerequisite.
    """
    import asyncio
    from unittest.mock import patch

    from src.config.agent_backends import AgentBackend
    from src.graph.nodes import orchestrator_node
    from src.models.plan import Plan, PlanStep

    stale_plan = Plan(
        thought="prior LangChain turn plan",
        title="prior",
        steps=[PlanStep(agent_name="coder", title="t", description="d", status="completed")],
    )
    state = {
        "messages": [],
        "research_mode": "standard",
        "thread_id": "test:abc",
        "plan": stale_plan,
        "current_step_index": 2,
        "todos": [{"content": "old", "status": "completed"}],
    }

    async def _fake_invoke_sdk(state, thread_id, research_mode):
        return "synthesized SDK answer"

    with (
        patch("src.config.agent_backends.resolve_agent_backend", return_value=AgentBackend.SDK),
        patch("src.agents.orchestrator_sdk.invoke_orchestrator_sdk", _fake_invoke_sdk),
    ):
        cmd = asyncio.run(orchestrator_node(state))

    assert cmd.goto == "__end__"
    assert cmd.update["plan"] is None
    assert cmd.update["current_step_index"] == 0
    assert cmd.update["todos"] == []
    assert len(cmd.update["messages"]) == 1
    assert cmd.update["messages"][0].name == "orchestrator"
