"""Orchestrator agent implementation with custom plan management.

The orchestrator replaces the legacy planner+supervisor combination.
It uses a custom manage_plan tool for planning and structured output for routing decisions.
"""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ClearToolUsesEdit,
    ContextEditingMiddleware,
    SummarizationMiddleware,
)

from src.config.research_mode import ResearchModeType
from src.config.settings import settings
from src.graph.types import OrchestratorResponse
from src.prompts.template import get_processed_prompt_with_database_context
from src.service.llm import LLMService
from src.tools.todos import manage_plan


def compose_orchestrator_system_prompt(research_mode: ResearchModeType = "standard") -> str:
    """Return the orchestrator's system prompt.

    Kept as a standalone helper so the prompt can be composed (and asserted
    on in tests) without constructing the agent.

    Args:
        research_mode: ``"standard"`` | ``"deep_research"``. Controls which
            research-mode section the prompt template inlines.
    """
    return get_processed_prompt_with_database_context("orchestrator", research_mode=research_mode)


def create_orchestrator_agent(research_mode: ResearchModeType = "standard"):
    """Create the orchestrator agent with custom manage_plan tool and structured routing.

    The orchestrator uses a custom manage_plan tool for planning and task management.
    Routing decisions and final synthesis are returned via structured output
    (OrchestratorResponse) in a single LLM call, eliminating the need for a separate routing call.

    Args:
        research_mode: Research mode for controlling research depth ("standard" or "deep_research")

    Returns:
        LangChain agent with manage_plan tool for planning and automatic structured output strategy
    """
    # Disable streaming for orchestrator agent since it uses tools (manage_plan)
    # Bedrock requires toolConfig when tools are used, which conflicts with streaming
    model = LLMService.get_llm_by_agent(
        "orchestrator", temperature=settings.llm_temperature, streaming=False
    )

    # Prompt is composed via the shared helper so the SDK prototype path
    # and this LangChain path see the identical prompt text (Phase 2 parity).
    system_prompt = compose_orchestrator_system_prompt(research_mode=research_mode)

    # Get summary LLM for context window management middleware
    summary_llm = LLMService.get_llm_by_agent("summarizer", streaming=False)

    # Compute trigger threshold: 200K * 0.70 = 140K tokens
    summary_trigger_tokens = int(
        settings.context_model_max_tokens * settings.context_summary_trigger_fraction
    )

    # Create agent with custom manage_plan tool and automatic structured output strategy
    # - manage_plan provides planning capability (custom implementation)
    # - response_format=OrchestratorResponse automatically uses ProviderStrategy for OpenAI/Gemini
    #   (native structured output) or falls back to ToolStrategy for other providers
    # - Both work together: agent calls tools during execution, returns structured output at end
    # - No file system tools (more secure for production)
    orchestrator = create_agent(
        model=model,
        tools=[manage_plan],  # Custom plan management tool
        middleware=[
            SummarizationMiddleware(
                model=summary_llm,
                trigger=("tokens", summary_trigger_tokens),
                keep=("messages", settings.context_summary_keep_messages),
            ),
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=settings.context_tool_clear_trigger,
                        keep=settings.context_tool_clear_keep,
                        clear_tool_inputs=False,
                        placeholder="[cleared — see conversation summary]",
                    ),
                ],
            ),
        ],
        system_prompt=system_prompt,
        response_format=OrchestratorResponse,  # Automatic strategy selection: ProviderStrategy for OpenAI/Gemini, ToolStrategy fallback
    )

    return orchestrator


# Global orchestrator agent instances cached by research_mode (used by orchestrator_node)
# Created lazily to avoid circular imports and expensive re-creation
_orchestrator_agents: dict[ResearchModeType, Any] = {}


def get_orchestrator_agent(research_mode: ResearchModeType = "standard"):
    """Get or create the orchestrator agent instance for the specified research mode.

    Args:
        research_mode: Research mode for controlling research depth ("standard" or "deep_research")

    Returns:
        Cached orchestrator agent instance for the specified mode
    """
    global _orchestrator_agents
    if research_mode not in _orchestrator_agents:
        _orchestrator_agents[research_mode] = create_orchestrator_agent(research_mode=research_mode)
    return _orchestrator_agents[research_mode]
