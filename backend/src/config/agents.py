"""Agent LLM configuration mapping.

Defines which model each agent should use. Every agent runs on the same
OpenAI-compatible gateway route, so the model name is the only thing that
varies per agent. LLM instantiation lives in src.service.llm.
"""

# Define agent-model mapping
AGENT_LLM_MAP: dict[str, str] = {
    "coordinator": "us.anthropic.claude-sonnet-4-6",
    "orchestrator": "us.anthropic.claude-opus-5",
    "coder": "us.anthropic.claude-sonnet-5",
    "sql_agent": "us.anthropic.claude-sonnet-5",
    "researcher": "us.anthropic.claude-sonnet-5",
    "summarizer": "us.anthropic.claude-sonnet-4-6",
}


def resolve_agent_model(agent_name: str) -> str:
    """Resolve an agent to the model it runs on.

    Args:
        agent_name: The name of the agent

    Returns:
        Model identifier

    Raises:
        ValueError: If agent_name is not found
    """
    if agent_name not in AGENT_LLM_MAP:
        raise ValueError(f"Agent '{agent_name}' not found in AGENT_LLM_MAP")

    return AGENT_LLM_MAP[agent_name]
