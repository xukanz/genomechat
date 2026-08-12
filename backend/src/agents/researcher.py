"""Researcher agent factory using langchain.agents.create_agent."""

from typing import Any

from langchain import agents

from src.service.llm import LLMService
from src.prompts.template import get_processed_prompt
from src.tools.literature import (
    search_literature,
    get_paper_citations,
    search_by_doi,
    get_literature_stats,
)


def create_researcher_agent() -> Any:
    """Create a researcher agent with literature search capabilities.

    The researcher agent uses Europe PMC to search scientific literature,
    retrieve papers by DOI, walk the citation graph, and scope a topic before
    committing to a search.

    Returns:
        Compiled LangGraph agent for literature research tasks
    """
    llm = LLMService.get_llm_by_agent("researcher", temperature=0.7, streaming=False)

    # Researcher agent needs the Europe PMC literature tools
    agent_tools = [
        search_literature,
        get_paper_citations,
        search_by_doi,
        get_literature_stats,
    ]

    # Get system prompt from template
    system_prompt = get_processed_prompt("researcher")

    # Create agent using langchain.agents.create_agent
    agent = agents.create_agent(
        model=llm,
        tools=agent_tools,
        system_prompt=system_prompt,
    )

    return agent
