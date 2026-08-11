"""Regression test — orchestrator_node must not shadow module-level imports.

Pins the fix for an UnboundLocalError: a
``from langchain_core.messages import AIMessage`` inside a conditional
branch made ``AIMessage`` a local variable in the entire function, so
every code path that didn't run that branch first raised
``UnboundLocalError: cannot access local variable 'AIMessage'``.

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
        "src.graph.nodes must import AIMessage at module level so every "
        "branch of orchestrator_node can use it."
    )
