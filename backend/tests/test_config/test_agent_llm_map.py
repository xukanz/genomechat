"""Tests for AGENT_LLM_MAP coverage.

Regression guard: ``create_researcher_agent()`` shipped calling
``get_llm_by_agent("researcher")`` while ``AGENT_LLM_MAP`` had no such key, so
``researcher_node`` raised ``ValueError`` the first time the orchestrator routed
to it. A missing entry is invisible until that agent is actually exercised, so
pin the whole set rather than the one key.
"""

import pytest

from src.config.agents import AGENT_LLM_MAP, resolve_agent_model
from src.config.settings import settings

# Every literal passed to ``LLMService.get_llm_by_agent`` across src/, plus the
# configurable one. Keep in sync when a new agent is added:
#   rg -n "get_llm_by_agent\(" src/
REQUIRED_AGENTS = frozenset(
    {
        "coordinator",  # graph/nodes.py
        "orchestrator",  # agents/orchestrator.py
        "coder",  # agents/coder.py
        "sql_agent",  # agents/sql_agent/graph.py, tools/sql_pipeline.py
        "researcher",  # agents/researcher.py
        "summarizer",  # agents/orchestrator.py
    }
)


def test_every_agent_used_in_src_is_mapped():
    missing = REQUIRED_AGENTS - AGENT_LLM_MAP.keys()
    assert not missing, f"AGENT_LLM_MAP is missing entries for: {sorted(missing)}"


@pytest.mark.parametrize("agent_name", sorted(REQUIRED_AGENTS))
def test_each_agent_resolves_to_a_model(agent_name):
    assert resolve_agent_model(agent_name), f"{agent_name} resolved to an empty model"


def test_memory_extraction_agent_setting_is_mapped():
    """``memory_extraction_agent`` is config-driven, so a typo here fails late."""
    assert settings.memory_extraction_agent in AGENT_LLM_MAP


def test_unknown_agent_raises():
    with pytest.raises(ValueError, match="not found in AGENT_LLM_MAP"):
        resolve_agent_model("no_such_agent")
