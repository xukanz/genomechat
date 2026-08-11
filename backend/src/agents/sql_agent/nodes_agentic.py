"""Agentic SQL agent workflow nodes.

Implements nodes for processing agentic SQL agent results with SQLAgenticResponse.
"""

import logging
import re
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.graph.state import SQLAgenticState
from src.models.sql_agent import SQLAgenticResponse, SQLQueryExecution

logger = logging.getLogger(__name__)


def prepare_sql_query_node_agentic(state: SQLAgenticState) -> Dict[str, Any]:
    """Extracts and combines user query, coordinator reasoning, and orchestrator context.

    Adapted version of prepare_sql_query_node for SQLAgenticState.
    Handles both direct user requests and iterative orchestrator calls.

    Args:
        state: Current SQL agentic state

    Returns:
        Updated state with combined natural language query
    """
    logger.info("SQL AGENTIC: Preparing query extraction and context combination...")

    messages = state.get("messages", [])
    if not messages:
        error_msg = "No messages found in state."
        logger.error(f"SQL AGENTIC: {error_msg}")
        return {"error_message": error_msg}

    # Extract components from message history
    user_queries = []
    orchestrator_contexts = []

    # Traverse messages in reverse to find the most recent relevant messages
    for msg in reversed(messages):
        # Extract user query (HumanMessage that's not a routing message)
        if isinstance(msg, HumanMessage):
            if hasattr(msg, "name") and msg.name in [
                "orchestrator",
                "coordinator",
                "sql_agent",
                "coder",
            ]:
                continue
            user_queries.append(msg.content)

        # Skip coordinator reasoning - coordinator only routes, doesn't set tasks
        # Coordinator reasoning is for observability only (CLI display), not for agent processing

        # Extract orchestrator context (AIMessage with name="orchestrator")
        if isinstance(msg, AIMessage):
            if hasattr(msg, "name") and msg.name == "orchestrator":
                orchestrator_contexts.append(msg.content)

    # Prioritize the most recent messages
    user_query = user_queries[0] if user_queries else None
    orchestrator_context = orchestrator_contexts[0] if orchestrator_contexts else None

    # Check if this is an iterative call
    is_iterative_call = orchestrator_context is not None and len(orchestrator_contexts) > 1

    if is_iterative_call:
        logger.info(
            "SQL AGENTIC: Detected iterative orchestrator call - prioritizing most recent orchestrator instructions"
        )

    # Validate we have at least a user query OR orchestrator context
    if user_query is None and orchestrator_context is None:
        error_msg = "No valid user query or orchestrator instructions found in message history."
        logger.error(f"SQL AGENTIC: {error_msg}")
        return {"error_message": error_msg}

    # Build comprehensive context package
    context_sections = []

    if is_iterative_call and orchestrator_context:
        context_sections.append(f"## Current Task (Iterative Call)\n{orchestrator_context}")
        if user_query:
            context_sections.append(f"\n## Original User Request\n{user_query}")
    else:
        if user_query:
            context_sections.append(f"## User Request\n{user_query}")
        if orchestrator_context:
            context_sections.append(f"\n## Task Context\n{orchestrator_context}")

    # Coordinator reasoning is NOT included - coordinator only routes, doesn't set tasks
    # The orchestrator is responsible for task planning and coordination

    # Combine into natural language query
    combined_query = "\n".join(context_sections)

    logger.info(
        f"SQL AGENTIC: Extracted user query: '{user_query[:100] if user_query else 'N/A'}...'"
    )

    # Replace the full main-graph message history with a single clean HumanMessage.
    # The original messages contain orchestrator AIMessages with tool_calls for tools
    # (manage_plan, OrchestratorResponse) that don't exist in the SQL agent's tool set.
    # Claude 4.6 on Bedrock rejects these as invalid assistant prefill.
    clean_messages = [HumanMessage(content=combined_query)]

    return {
        "natural_language_query": combined_query,
        "messages": clean_messages,
    }


def _extract_sql_queries_from_messages(messages: List) -> List[SQLQueryExecution]:
    """Extract all SQL queries executed from agent message history.

    Parses AIMessage tool_calls and matches with ToolMessage results
    to reconstruct all SQL query executions.

    Args:
        messages: List of messages from agent execution

    Returns:
        List of SQLQueryExecution objects representing all queries executed
    """
    sql_executions = []
    tool_results_by_id = {}

    # First pass: Collect all ToolMessage results
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_results_by_id[msg.tool_call_id] = msg.content

    # Second pass: Extract SQL queries from AIMessage tool_calls
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if tool_call.get("name") == "execute_sql_pipeline":
                    # Extract SQL query from tool call arguments
                    args = tool_call.get("args", {})
                    sql_query = args.get("sql_query", "")

                    if not sql_query:
                        continue

                    # Get tool result
                    tool_call_id = tool_call.get("id", "")
                    tool_result = tool_results_by_id.get(tool_call_id, "")

                    # Parse execution status and result from tool output
                    execution_status = "success"
                    execution_result = None
                    error_message = None
                    row_count = None

                    if isinstance(tool_result, str):
                        if tool_result.startswith("SUCCESS:"):
                            execution_status = "success"
                            execution_result = tool_result.replace("SUCCESS:", "").strip()
                            # Try to extract row count from result
                            if "rows" in execution_result.lower():
                                row_match = re.search(
                                    r"(\d+)\s+rows?", execution_result, re.IGNORECASE
                                )
                                if row_match:
                                    row_count = int(row_match.group(1))
                        elif tool_result.startswith("VALIDATION_FAILED:"):
                            execution_status = "validation_failed"
                            error_message = tool_result.replace("VALIDATION_FAILED:", "").strip()
                        elif tool_result.startswith("EXECUTION_ERROR:"):
                            execution_status = "execution_error"
                            error_message = tool_result.replace("EXECUTION_ERROR:", "").strip()

                    sql_execution = SQLQueryExecution(
                        sql=sql_query,
                        execution_status=execution_status,
                        execution_result=execution_result,
                        error_message=error_message,
                        row_count=row_count,
                    )
                    sql_executions.append(sql_execution)
                    logger.debug(
                        f"SQL AGENTIC: Extracted SQL query #{len(sql_executions)}: {sql_query[:100]}..."
                    )

    return sql_executions


def process_agentic_result_node(state: SQLAgenticState) -> Dict[str, Any]:
    """Processes the agentic agent's result which includes SQLAgenticResponse.

    Extracts the SQLAgenticResponse from structured_response and formats
    the final message for the user.

    Args:
        state: Current SQL agentic state (contains agent's result with structured_response)

    Returns:
        Updated state with formatted response message and metadata
    """
    logger.info("SQL AGENTIC: Processing agent result with structured output...")

    if state.get("error_message"):
        return {}

    # Extract structured_response from state (added by agent with response_format)
    structured_response = state.get("structured_response")

    if not structured_response:
        error_msg = "No structured_response found in agent result. Agent may not have returned structured output."
        logger.error(f"SQL AGENTIC: {error_msg}")
        return {"error_message": error_msg}

    try:
        # structured_response is already a SQLAgenticResponse instance
        result: SQLAgenticResponse = structured_response
        logger.info(f"SQL AGENTIC: Processed response - kind: {result.kind}")

        # OPTION 1: Deterministically extract all SQL queries from message history
        messages = state.get("messages", [])
        extracted_sql_queries = _extract_sql_queries_from_messages(messages)

        logger.info(
            f"SQL AGENTIC: Extracted {len(extracted_sql_queries)} SQL query(ies) from message history"
        )

        # OPTION 2: Compare with agent's reported queries (for validation)
        agent_reported_queries = result.sql_queries if result.sql_queries else []

        # Compare only successful queries (failed queries are for observability, not comparison)
        extracted_successful = [q for q in extracted_sql_queries if q.execution_status == "success"]
        agent_reported_successful = [
            q for q in agent_reported_queries if q.execution_status == "success"
        ]

        # Log comparison for observability (only warn if successful queries don't match)
        if len(extracted_successful) != len(agent_reported_successful):
            logger.warning(
                f"SQL AGENTIC: Successful query count mismatch - "
                f"Extracted successful: {len(extracted_successful)}, Agent reported successful: {len(agent_reported_successful)}"
            )
        elif len(extracted_sql_queries) != len(agent_reported_queries):
            # Log info if total counts differ but successful counts match (failed queries present)
            logger.info(
                f"SQL AGENTIC: Total query counts differ but successful queries match - "
                f"Extracted total: {len(extracted_sql_queries)} (successful: {len(extracted_successful)}), "
                f"Agent reported total: {len(agent_reported_queries)} (successful: {len(agent_reported_successful)})"
            )

        # Use extracted queries as source of truth (deterministic)
        # This includes all queries (successful and failed) for complete traceability
        final_sql_queries = (
            extracted_sql_queries if extracted_sql_queries else agent_reported_queries
        )

        # Build response content - ensure all SQL queries are included
        response_content = result.response

        # Check if SQL queries are already in response
        sql_markers = ["SQL Query Used", "SQL Queries Used", "```sql"]
        has_sql_in_response = any(
            marker.lower() in response_content.lower() for marker in sql_markers
        )

        # Append SQL queries section if we have queries and they're not already included
        if result.kind == "sql" and final_sql_queries:
            if not has_sql_in_response:
                logger.info(
                    "SQL AGENTIC: SQL queries not found in response, appending from extracted queries"
                )
                sql_section = "\n\n## SQL Queries Used\n\n"

                for idx, sql_exec in enumerate(final_sql_queries, 1):
                    sql_section += f"### Query {idx}\n\n"
                    sql_section += f"```sql\n{sql_exec.sql}\n```\n\n"
                    if sql_exec.execution_status != "success":
                        sql_section += f"**Status**: {sql_exec.execution_status}\n"
                        if sql_exec.error_message:
                            sql_section += f"**Error**: {sql_exec.error_message}\n"
                    sql_section += "\n"

                response_content = result.response + sql_section
            else:
                logger.debug("SQL AGENTIC: SQL queries already present in response")

        # Create final message with the response content
        final_message = AIMessage(content=response_content, name="sql_agent")

        # Build state update
        state_update = {
            "messages": [final_message],
            "natural_language_query": state.get("natural_language_query"),
            "structured_response": structured_response,  # Preserve for observability
        }

        # Log based on response kind for observability
        if result.kind == "sql":
            # Calculate query execution metrics
            total_queries = len(final_sql_queries)
            successful_queries = sum(
                1 for q in final_sql_queries if q.execution_status == "success"
            )
            failed_queries = total_queries - successful_queries
            validation_failed = sum(
                1 for q in final_sql_queries if q.execution_status == "validation_failed"
            )
            execution_errors = sum(
                1 for q in final_sql_queries if q.execution_status == "execution_error"
            )

            # Log summary metrics
            logger.info(
                f"SQL AGENTIC: Query execution summary - "
                f"Total: {total_queries}, "
                f"Successful: {successful_queries}, "
                f"Failed: {failed_queries} "
                f"(validation_failed: {validation_failed}, execution_error: {execution_errors})"
            )

            # Log individual queries at debug level
            for idx, sql_exec in enumerate(final_sql_queries, 1):
                logger.debug(
                    f"SQL AGENTIC: Query {idx}: {sql_exec.sql[:100]}... [{sql_exec.execution_status}]"
                )
        elif result.kind == "schema":
            logger.info("SQL AGENTIC: Schema information provided")
        elif result.kind == "error":
            # Derive error message from sql_queries if available
            last_query = final_sql_queries[-1] if final_sql_queries else None
            error_msg = (
                last_query.error_message
                if last_query and last_query.error_message
                else (result.reason or "Unknown error")
            )
            logger.warning(f"SQL AGENTIC: Error response - {error_msg}")
        elif result.kind == "other":
            logger.info(
                f"SQL AGENTIC: Other response - {result.reason[:100] if result.reason else 'N/A'}"
            )

        return state_update

    except Exception as e:
        error_msg = f"Error processing agentic result: {str(e)}"
        logger.error(f"SQL AGENTIC: {error_msg}")
        return {"error_message": error_msg}
