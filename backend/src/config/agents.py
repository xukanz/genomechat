"""Agent LLM configuration mapping.

Defines which LLM provider and model each agent should use.
LLM instantiation logic has been moved to src.service.llm for clean architecture.
"""

from typing import Tuple

from src.config.llm import ProviderType

# Define agent-LLM mapping: (provider, model)
AGENT_LLM_MAP: dict[str, Tuple[str, str]] = {
    "coordinator": (ProviderType.PORTKEY_BEDROCK, "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "orchestrator": (ProviderType.PORTKEY_BEDROCK, "us.anthropic.claude-opus-4-6-v1"),
    "coder": (ProviderType.PORTKEY_BEDROCK, "us.anthropic.claude-sonnet-4-6"),
    "sql_agent": (ProviderType.PORTKEY_BEDROCK, "us.anthropic.claude-sonnet-4-6"),
    "summarizer": (ProviderType.PORTKEY_BEDROCK, "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
}
# AGENT_LLM_MAP: dict[str, Tuple[str, str]] = {
#     "coordinator": (ProviderType.PORTKEY_AZURE, "gpt-5-mini"),
#     "orchestrator": (ProviderType.PORTKEY_AZURE, "gpt-5-mini"),
#     "coder": (ProviderType.PORTKEY_AZURE, "gpt-5-mini"),
#     "sql_agent": (ProviderType.PORTKEY_AZURE, "gpt-5-mini"),
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
