"""SQL agent graph builder.

Creates a LangGraph subgraph for SQL database interaction workflow.
Uses modern LangChain patterns with structured output and create_agent.
"""

import logging
from functools import partial
from typing import Any

from langchain import agents
from langgraph.graph import END, StateGraph

from src.agents.sql_agent.nodes import (
    check_extraction_result,
    check_for_errors_after_execution,
    decide_after_validation,
    format_response_node,
    handle_error_node,
    increment_retry_node,
    prepare_sql_query_node,
    process_agent_result_node,
    sql_executor_node,
    sql_validator_node,
)
from src.graph.state import SQLAgentState
from src.models.sql_agent import SQLProposal
from src.prompts.template import get_processed_prompt
from src.service.llm import LLMService
from src.tools.database import get_database_schema, get_random_subsamples

logger = logging.getLogger(__name__)


def create_sql_agent_graph() -> Any:
    """Creates and compiles the LangGraph StateGraph for the SQL agent.

    Returns:
        Compiled LangGraph agent for SQL database interaction
    """
    # Get the LLM client for the SQL agent
    # Disable streaming since SQL agent uses tools and Bedrock requires toolConfig when tools are used
    llm_client = LLMService.get_llm_by_agent("sql_agent", temperature=0.0, streaming=False)

    # Build the workflow graph
    workflow = StateGraph(SQLAgentState)

    # Create the SQL agent with tools and structured output
    # Tools: get_database_schema (for schema requests), get_random_subsamples (for sample data)
    # The agent uses structured output (SQLProposal) via response_format to communicate its decision
    # Automatic strategy selection: ProviderStrategy for OpenAI/Gemini (native structured output),
    # ToolStrategy fallback for other providers
    system_prompt = get_processed_prompt("sql_agent/system_prompt", {})
    sql_agent = agents.create_agent(
        model=llm_client,
        tools=[get_database_schema, get_random_subsamples],
        system_prompt=system_prompt,
        response_format=SQLProposal,  # Automatic strategy selection: ProviderStrategy for OpenAI/Gemini, ToolStrategy fallback
    )

    # Bind the llm_client and agent_name to the nodes that need it
    validate_sql_with_llm = partial(
        sql_validator_node, llm_client=llm_client, agent_name="sql_agent"
    )
    format_response_with_llm = partial(format_response_node, llm_client=llm_client)

    # Add nodes
    workflow.add_node("prepare_query", prepare_sql_query_node)
    workflow.add_node("sql_agent", sql_agent)
    workflow.add_node("process_agent_result", process_agent_result_node)
    workflow.add_node("validate_sql", validate_sql_with_llm)
    workflow.add_node("execute_sql", sql_executor_node)
    workflow.add_node("handle_error", handle_error_node)
    workflow.add_node("format_response", format_response_with_llm)
    workflow.add_node("increment_retry", increment_retry_node)

    # Set entry point to prepare_query (extracts and combines context)
    workflow.set_entry_point("prepare_query")

    # Add edges
    workflow.add_edge("prepare_query", "sql_agent")
    workflow.add_edge("sql_agent", "process_agent_result")

    workflow.add_conditional_edges(
        "process_agent_result",
        check_extraction_result,
        {
            "validate_sql": "validate_sql",
            "format_response": "format_response",
            "handle_error": "handle_error",
        },
    )

    workflow.add_conditional_edges(
        "validate_sql",
        decide_after_validation,
        {
            "execute_sql": "execute_sql",
            "increment_retry": "increment_retry",
            "handle_error": "handle_error",
        },
    )

    # Retries go back to prepare_query to rebuild context with error feedback
    workflow.add_edge("increment_retry", "prepare_query")

    workflow.add_conditional_edges(
        "execute_sql",
        check_for_errors_after_execution,
        {
            "increment_retry": "increment_retry",  # Retry on execution error
            "handle_error": "handle_error",
            "continue_to_format": "format_response",
        },
    )

    workflow.add_edge("handle_error", "format_response")
    workflow.add_edge("format_response", END)

    # Compile the graph
    sql_agent_app = workflow.compile()
    sql_agent_app.name = "sql_agent"
    logger.info("SQL AGENT: Compiled SQL agent graph.")
    return sql_agent_app
