"""Agent LLM configuration mapping.

Every agent runs against the same OpenAI-compatible gateway, so the model name
is the only thing that varies per agent — and each one is a setting, so models
can be changed per environment without a deploy. LLM instantiation lives in
src.service.llm.
"""

from src.config.settings import settings

# Agent name -> the Settings field holding its model. Membership here is what
# makes an agent known; add a route by adding a settings field and an entry.
AGENT_MODEL_SETTINGS: dict[str, str] = {
    "coordinator": "openai_model_coordinator",
    "orchestrator": "openai_model_orchestrator",
    "coder": "openai_model_coder",
    "sql_agent": "openai_model_sql_agent",
    "researcher": "openai_model_researcher",
    "summarizer": "openai_model_summarizer",
}


def resolve_agent_model(agent_name: str) -> str:
    """Resolve an agent to the model it runs on.

    Read through `settings` on every call rather than snapshotting at import,
    so overriding a model in tests or at runtime takes effect.

    Args:
        agent_name: The name of the agent

    Returns:
        Model identifier

    Raises:
        ValueError: If agent_name is not found
    """
    if agent_name not in AGENT_MODEL_SETTINGS:
        raise ValueError(f"Agent '{agent_name}' not found in AGENT_MODEL_SETTINGS")

    model: str = getattr(settings, AGENT_MODEL_SETTINGS[agent_name])
    return model
