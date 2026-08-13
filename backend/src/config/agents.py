"""Agent LLM configuration mapping.

Defines which LLM provider and model each agent should use.
LLM instantiation logic has been moved to src.service.llm for clean architecture.
"""

from typing import Tuple

from src.config.llm import ProviderType

# Define agent-LLM mapping: (provider, model)
AGENT_LLM_MAP: dict[str, Tuple[str, str]] = {
    "coordinator": (ProviderType.OPENAI_BEDROCK, "us.anthropic.claude-sonnet-4-6"),
    "orchestrator": (ProviderType.OPENAI_BEDROCK, "us.anthropic.claude-opus-5"),
    "coder": (ProviderType.OPENAI_BEDROCK, "us.anthropic.claude-sonnet-5"),
    "sql_agent": (ProviderType.OPENAI_BEDROCK, "us.anthropic.claude-sonnet-5"),
    "researcher": (ProviderType.OPENAI_BEDROCK, "us.anthropic.claude-sonnet-5"),
    "summarizer": (ProviderType.OPENAI_BEDROCK, "us.anthropic.claude-sonnet-4-6"),
}
# AGENT_LLM_MAP: dict[str, Tuple[str, str]] = {
#     "coordinator": (ProviderType.OPENAI_AZURE, "gpt-5-mini"),
#     "orchestrator": (ProviderType.OPENAI_AZURE, "gpt-5-mini"),
#     "coder": (ProviderType.OPENAI_AZURE, "gpt-5-mini"),
#     "sql_agent": (ProviderType.OPENAI_AZURE, "gpt-5-mini"),
# }


def resolve_agent_llm_config(agent_name: str) -> Tuple[str, str]:
    """Resolve agent LLM configuration to (provider, model) tuple.

    Args:
        agent_name: The name of the agent

    Returns:
        Tuple of (provider, model)

    Raises:
        ValueError: If agent_name is not found
    """
    if agent_name not in AGENT_LLM_MAP:
        raise ValueError(f"Agent '{agent_name}' not found in AGENT_LLM_MAP")

    return AGENT_LLM_MAP[agent_name]
