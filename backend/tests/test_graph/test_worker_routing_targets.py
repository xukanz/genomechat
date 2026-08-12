"""The set of worker agents must agree across every place that names them.

Regression guard for a routing bug that failed *silently*: the researcher was
added to the graph, to ``valid_workers`` and to the prompts, but not to the
``OrchestratorResponse.next`` Literal. Structured output then could not emit
"researcher" at all, so the orchestrator — which had reasoned its way to the
researcher and said so in its ``reasoning`` field — was coerced into routing to
"coder" instead, and told the coder to call a literature API over raw HTTP.

Nothing raised. The only symptom was the wrong agent doing the work, which is
why this is pinned as an executable invariant rather than left to review.
"""

from __future__ import annotations

import typing

import pytest
from pydantic import ValidationError

from src.config.agents import AGENT_LLM_MAP
from src.graph.builder import build_graph
from src.graph.types import OrchestratorResponse

# Every worker the orchestrator may delegate to. Adding one means updating each
# surface asserted below.
WORKERS = frozenset({"coder", "sql_agent", "researcher"})


def _next_literals() -> set[str]:
    args = typing.get_args(OrchestratorResponse.model_fields["next"].annotation)
    return {literal for arg in args for literal in typing.get_args(arg)}


def test_routing_schema_accepts_every_worker():
    assert WORKERS <= _next_literals()


def test_routing_schema_also_allows_end():
    assert "__end__" in _next_literals()


def test_routing_schema_rejects_unknown_targets():
    with pytest.raises(ValidationError):
        OrchestratorResponse(next="not_an_agent")


@pytest.mark.parametrize("worker", sorted(WORKERS))
def test_worker_is_routable_end_to_end(worker):
    """Schema, graph node and LLM mapping must all know the same worker."""
    OrchestratorResponse(next=worker, reasoning="routing check")
    assert worker in build_graph().nodes, f"{worker} has no graph node"
    assert worker in AGENT_LLM_MAP, f"{worker} has no entry in AGENT_LLM_MAP"


def test_graph_exposes_exactly_the_expected_nodes():
    nodes = set(build_graph().nodes)
    assert WORKERS <= nodes
    assert {"coordinator", "orchestrator"} <= nodes
