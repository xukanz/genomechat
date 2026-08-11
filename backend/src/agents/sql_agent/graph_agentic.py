"""Agentic SQL agent graph builder.

Creates a simplified LangGraph subgraph for agentic SQL database interaction workflow.
Uses a single agent with tools instead of multiple graph nodes.
"""

import logging
from typing import Any

from langchain import agents
from langgraph.graph import END, StateGraph

from src.agents.sql_agent.nodes_agentic import (
    prepare_sql_query_node_agentic,
    process_agentic_result_node,
)
from src.graph.state import SQLAgenticState
from src.models.sql_agent import SQLAgenticResponse
from src.prompts.template import get_processed_prompt_with_database_context
from src.service.llm import LLMService
from src.tools.database import get_database_schema, get_random_subsamples
from src.tools.sql_pipeline import execute_sql_pipeline

logger = logging.getLogger(__name__)


def create_sql_agent_agentic_graph() -> Any:
    """Creates and compiles the LangGraph StateGraph for the agentic SQL agent.

    The agentic system uses a simplified graph:
    - Entry node: prepare_query (extracts context)
    - Agent node: sql_agent (with tools, handles everything internally)
    - Process node: process_agentic_result (extracts structured response)

    Returns:
        Compiled LangGraph agent for agentic SQL database interaction
    """
    # Get the LLM client for the SQL agent
    # Disable streaming since SQL agent uses tools and Bedrock requires toolConfig when tools are used
    llm_client = LLMService.get_llm_by_agent("sql_agent", temperature=0.0, streaming=False)

    # Build the workflow graph
    workflow = StateGraph(SQLAgenticState)

    # Create the SQL agent with tools and structured output
    # Tools: get_database_schema, get_random_subsamples, execute_sql_pipeline
    # The agent uses structured output (SQLAgenticResponse) via response_format
    # Automatic strategy selection: ProviderStrategy for OpenAI/Gemini (native structured output),
    # ToolStrategy fallback for other providers
    system_prompt = get_processed_prompt_with_database_context(
        "sql_agent/system_prompt_agentic", {}
    )
    sql_agent = agents.create_agent(
        model=llm_client,
        tools=[get_database_schema, get_random_subsamples, execute_sql_pipeline],
        system_prompt=system_prompt,
        response_format=SQLAgenticResponse,  # Automatic strategy selection: ProviderStrategy for OpenAI/Gemini, ToolStrategy fallback
    )

    # Add nodes
    workflow.add_node("prepare_query", prepare_sql_query_node_agentic)
    workflow.add_node("sql_agent", sql_agent)
    workflow.add_node("process_agentic_result", process_agentic_result_node)

    # Set entry point to prepare_query (extracts and combines context)
    workflow.set_entry_point("prepare_query")

    # Add edges - simple linear flow
    workflow.add_edge("prepare_query", "sql_agent")
    workflow.add_edge("sql_agent", "process_agentic_result")
    workflow.add_edge("process_agentic_result", END)

    # Compile the graph
    sql_agent_app = workflow.compile()
    sql_agent_app.name = "sql_agent_agentic"
    logger.info("SQL AGENTIC: Compiled agentic SQL agent graph.")
    return sql_agent_app
