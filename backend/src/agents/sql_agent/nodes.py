"""SQL agent workflow nodes for LangGraph subgraph.

Implements nodes for SQL generation, validation, execution, and response formatting.
Uses structured output instead of regex parsing for reliability.
"""

import logging
import re
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.config.settings import settings
from src.graph.state import SQLAgentState
from src.models.sql_agent import SQLValidationResult
from src.prompts.template import get_processed_prompt
from src.service.llm import LLMService
from src.tools.database import execute_sql_query, execute_sql_query_and_save

logger = logging.getLogger(__name__)

# Constants
MAX_SQL_RETRIES = 2


def prepare_sql_query_node(state: SQLAgentState) -> Dict[str, Any]:
    """Extracts and combines user query, coordinator reasoning, and orchestrator context.

    Handles both direct user requests and iterative orchestrator calls. In iterative
    scenarios, the orchestrator may call SQL agent multiple times with new instructions
    based on previous results. This function prioritizes the most recent orchestrator
    instructions while preserving the original user intent.

    Note: Previous SQL results are NOT included here as the orchestrator already
    provides relevant context in its iterative instructions, avoiding context overload.

    Creates a comprehensive context package without fetching schema (SQL agent has the tool).

    Args:
        state: Current SQL agent state

    Returns:
        Updated state with combined natural language query and reset fields
    """
    logger.info("SQL AGENT: Preparing query extraction and context combination...")

    messages = state.get("messages", [])
    if not messages:
        error_msg = "No messages found in state."
        logger.error(f"SQL AGENT: {error_msg}")
        return {"error_message": error_msg}

    # Extract components from message history
    # Use lists to collect ALL relevant messages, then take the most recent
    user_queries = []
    orchestrator_contexts = []

    # Traverse messages in reverse to find the most recent relevant messages
    # We collect all instances, then prioritize the most recent ones
    for msg in reversed(messages):
        # Extract user query (HumanMessage that's not a routing message)
        if isinstance(msg, HumanMessage):
            # Skip routing messages from internal agents
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
        # IMPORTANT: Collect ALL orchestrator messages, we'll use the most recent
        if isinstance(msg, AIMessage):
            if hasattr(msg, "name") and msg.name == "orchestrator":
                orchestrator_contexts.append(msg.content)

    # Prioritize the most recent messages (first in reversed list)
    user_query = user_queries[0] if user_queries else None
    orchestrator_context = orchestrator_contexts[0] if orchestrator_contexts else None

    # Check if this is an iterative call (orchestrator providing new instructions)
    is_iterative_call = orchestrator_context is not None and len(orchestrator_contexts) > 1

    # In iterative scenarios, orchestrator's most recent instruction is the primary query
    # But we still preserve original user intent for context
    if is_iterative_call:
        logger.info(
            "SQL AGENT: Detected iterative orchestrator call - prioritizing most recent orchestrator instructions"
        )

    # Validate we have at least a user query OR orchestrator context
    # In iterative calls, orchestrator might be providing the query directly
    if user_query is None and orchestrator_context is None:
        error_msg = "No valid user query or orchestrator instructions found in message history."
        logger.error(f"SQL AGENT: {error_msg}")
        return {"error_message": error_msg}

    # Build comprehensive context package
    context_sections = []

    # In iterative calls, orchestrator's instruction is primary
    # Otherwise, user query is primary
    if is_iterative_call and orchestrator_context:
        context_sections.append(f"## Current Task (Iterative Call)\n{orchestrator_context}")
        if user_query:
            context_sections.append(f"\n## Original User Request\n{user_query}")
    else:
        # Direct user request
        if user_query:
            context_sections.append(f"## User Request\n{user_query}")
        if orchestrator_context:
            context_sections.append(f"\n## Task Context\n{orchestrator_context}")

    # Coordinator reasoning is NOT included - coordinator only routes, doesn't set tasks
    # The orchestrator is responsible for task planning and coordination

    # Note: Previous SQL results are NOT included here to avoid context overload.
    # The orchestrator already includes relevant context in its iterative instructions.

    # Combine into natural language query
    combined_query = "\n".join(context_sections)

    logger.info(
        f"SQL AGENT: Extracted user query: '{user_query[:100] if user_query else 'N/A'}...'"
    )
    if orchestrator_context:
        logger.debug(f"SQL AGENT: Found orchestrator context (iterative: {is_iterative_call})")

    return {
        "natural_language_query": combined_query,
        # Reset SQL generation state (unless retrying)
        "generated_sql": None
        if not state.get("sql_generation_retries")
        else state.get("generated_sql"),
        "provided_schema_text": None,
        "error_message": None,
    }


def process_agent_result_node(state: SQLAgentState) -> Dict[str, Any]:
    """Processes the agent's result which includes structured_response.

    The agent uses response_format=SQLProposal (automatic strategy selection), so the result
    contains structured_response with the SQLProposal extracted from tool call.

    Args:
        state: Current SQL agent state (contains agent's result with structured_response)

    Returns:
        Updated state with generated SQL or schema text
    """
    logger.info("SQL AGENT: Processing agent result with structured output...")

    if state.get("error_message"):
        return {}

    # Get messages to extract user query and tool results
    messages = state.get("messages", [])
    if not messages:
        return {"error_message": "No messages found from agent"}

    # Extract original user query if not already stored (for retry purposes)
    natural_language_query = state.get("natural_language_query")
    if not natural_language_query:
        for msg in messages:
            if isinstance(msg, HumanMessage):
                natural_language_query = msg.content
                break

    # Extract structured_response from state (added by agent with response_format)
    # When agent is invoked as a node, structured_response is added to state
    structured_response = state.get("structured_response")

    if not structured_response:
        # Fallback: try to extract from the last AIMessage if structured_response not in state
        # This might happen if the agent didn't return structured output properly
        error_msg = "No structured_response found in agent result. Agent may not have returned structured output."
        logger.error(f"SQL AGENT: {error_msg}")
        return {"error_message": error_msg}

    try:
        # structured_response is already a SQLProposal instance
        result = structured_response
        logger.info(f"SQL AGENT: Processed proposal - kind: {result.kind}")

        if result.kind == "schema":
            logger.info("SQL AGENT: Agent provided schema information")
            # If agent called get_database_schema tool, the schema should be in the ToolMessage
            schema_text = result.reason or ""

            # Look for ToolMessage with schema content (from get_database_schema tool)
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage):
                    content = msg.content if isinstance(msg.content, str) else str(msg.content)
                    # Check if this looks like schema content
                    if (
                        "Table:" in content
                        or "complexes" in content.lower()
                        or "chains" in content.lower()
                    ):
                        schema_text = content
                        logger.info("SQL AGENT: Found schema in tool result")
                        break

            return {
                "provided_schema_text": schema_text or "Schema requested by agent.",
                "generated_sql": None,
                "natural_language_query": natural_language_query,  # Store for retries
            }
        elif result.kind == "sql" and result.sql:
            logger.info(f"SQL AGENT: Extracted SQL: {result.sql[:100]}...")
            return {
                "generated_sql": result.sql,
                "provided_schema_text": None,
                "natural_language_query": natural_language_query,  # Store for retries
            }
        elif result.kind == "other" and result.reason:
            # Handle "other" kind - might contain schema info or explanations
            reason_lower = result.reason.lower()
            schema_indicators = ["table", "column", "schema", "complex_id", "chain_id"]
            if any(indicator in reason_lower for indicator in schema_indicators):
                logger.info("SQL AGENT: Detected schema information in 'other' response")
                return {
                    "provided_schema_text": result.reason,
                    "generated_sql": None,
                    "natural_language_query": natural_language_query,
                }
            else:
                error_msg = f"Agent returned 'other' kind without clear action. Reason: {result.reason[:100]}"
                logger.warning(f"SQL AGENT: {error_msg}")
                return {"error_message": error_msg}
        else:
            error_msg = f"No SQL or schema request produced. Kind: {result.kind}, SQL: {bool(result.sql)}, Reason: {bool(result.reason)}"
            logger.error(f"SQL AGENT: {error_msg}")
            return {"error_message": error_msg}

    except Exception as e:
        error_msg = f"Error processing agent result: {str(e)}"
        logger.error(f"SQL AGENT: {error_msg}")
        return {"error_message": error_msg}


def sql_validator_node(
    state: SQLAgentState, llm_client: Any, agent_name: str = "sql_agent"
) -> Dict[str, Any]:
    """Validates the generated SQL using an LLM with structured output.

    Args:
        state: Current SQL agent state
        llm_client: LLM client for structured output
        agent_name: Name of the agent (default: "sql_agent")

    Returns:
        Updated state with validation status and feedback
    """
    logger.info("SQL AGENT: Validating SQL...")

    if (
        state.get("error_message")
        or not state.get("generated_sql")
        or state.get("provided_schema_text")
    ):
        logger.warning(
            "SQL AGENT: Skipping SQL validation due to prior error, missing SQL, or schema was provided directly."
        )
        return {}

    schema = state.get("schema", "Schema not available for validation.")

    # Prepare template variables for SQL validation
    template_vars = {
        "DATABASE_SCHEMA": schema,
        "USER_QUERY": state.get("natural_language_query", ""),
        "GENERATED_SQL": state.get("generated_sql", ""),
    }

    # Generate the validation prompt using the workflow template
    prompt_str = get_processed_prompt("sql_agent/sql_validator", template_vars)

    try:
        method = LLMService.get_structured_output_method_for_agent(agent_name)
        structured_llm = llm_client.with_structured_output(SQLValidationResult, method=method)
        logger.info("SQL AGENT: Attempting SQL validation...")
        validation_result = structured_llm.invoke([HumanMessage(content=prompt_str)])
        logger.info(f"SQL AGENT: Validation result: {validation_result.status}")
        return {
            "validation_status": validation_result.status,
            "validation_feedback": validation_result.feedback,
        }
    except Exception as e:
        logger.error(f"SQL AGENT: Error validating SQL: {e}")
        return {
            "validation_status": "error",
            "validation_feedback": f"Failed during validation: {str(e)}",
        }


def sql_executor_node(state: SQLAgentState) -> Dict[str, Any]:
    """Executes the validated SQL query with EXPLAIN guard and adaptive LIMIT.

    Args:
        state: Current SQL agent state

    Returns:
        Updated state with execution result
    """
    logger.info("SQL AGENT: Executing SQL...")

    if (
        state.get("error_message")
        or not state.get("generated_sql")
        or state.get("validation_status") != "valid"
        or state.get("provided_schema_text")
    ):
        if state.get("validation_status") != "valid" and not state.get("provided_schema_text"):
            logger.warning(
                f"SQL AGENT: Skipping execution because SQL validation status is "
                f"'{state.get('validation_status')}'."
            )
        return {}

    try:
        sql_query = state.get("generated_sql", "")
        query_lower = sql_query.lower().strip()

        # DDL guard: reject CREATE/DROP/ALTER/TRUNCATE without approval
        ddl_patterns = [r"\bCREATE\b", r"\bDROP\b", r"\bALTER\b", r"\bTRUNCATE\b"]
        if any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in ddl_patterns):
            error_msg = "DDL detected (CREATE/DROP/ALTER/TRUNCATE); requires human approval."
            logger.warning(f"SQL AGENT: {error_msg}")
            return {"error_message": error_msg}

        # Check if force-save is enabled via environment variable
        force_save_all = getattr(settings, "sql_always_save_to_s3", False)

        if force_save_all:
            logger.info("SQL AGENT: Force-save enabled - saving all queries to S3")
            query_description = state.get("natural_language_query", "data_analysis")
            if len(query_description) > 100:
                query_description = query_description[:100] + "..."

            execution_result = execute_sql_query_and_save.invoke(
                {"query": sql_query, "description": query_description}
            )
        else:
            # Check for visualization/plotting indicators - coder agent needs CSV files
            user_query_lower = state.get("natural_language_query", "").lower()
            visualization_indicators = [
                "plot" in user_query_lower,
                "graph" in user_query_lower,
                "chart" in user_query_lower,
                "visualiz" in user_query_lower,
                "distribution" in user_query_lower
                and any(word in user_query_lower for word in ["plot", "chart", "graph", "show"]),
                '"agent_name": "coder"' in user_query_lower,
                "coder" in user_query_lower and "visualization" in user_query_lower,
            ]

            # Check for patterns that typically return large datasets
            large_dataset_indicators = [
                "join" in query_lower and "group by" in query_lower,
                "cross join" in query_lower,
                "window" in query_lower or "over(" in query_lower,
                sql_query.count("join") > 2,
                "statistical" in user_query_lower,
                "significance" in user_query_lower,
                "diversity" in user_query_lower,
            ]

            # Use file-based approach for large results or visualizations
            use_file_approach = any(large_dataset_indicators) or any(visualization_indicators)

            if use_file_approach:
                if any(visualization_indicators):
                    logger.info(
                        "SQL AGENT: Using file-based execution for visualization/plotting "
                        "(coder agent needs CSV files)"
                    )
                else:
                    logger.info(
                        "SQL AGENT: Using file-based execution for potentially large/complex results"
                    )

                # Generate a meaningful description for the saved file
                query_description = state.get("natural_language_query", "data_analysis")
                if len(query_description) > 100:
                    query_description = query_description[:100] + "..."

                execution_result = execute_sql_query_and_save.invoke(
                    {"query": sql_query, "description": query_description}
                )
            else:
                # Apply adaptive LIMIT if not present
                if not re.search(r"\blimit\b", query_lower, re.IGNORECASE):
                    # Add LIMIT to the query
                    sql_query = f"{sql_query.rstrip(';')} LIMIT 1000"
                    logger.info("SQL AGENT: Applied adaptive LIMIT 1000 for first pass")

                logger.info("SQL AGENT: Using standard execution for smaller expected results")
                execution_result = execute_sql_query.invoke({"query": sql_query})

        logger.info("SQL AGENT: Execution result obtained.")
        return {"execution_result": execution_result}

    except Exception as e:
        error_msg = f"Failed during SQL execution: {str(e)}"
        logger.error(f"SQL AGENT: {error_msg}")
        return {"error_message": error_msg}


def format_response_node(state: SQLAgentState, llm_client: Any) -> Dict[str, Any]:
    """Formats the final response message using LLM-powered formatting.

    Includes both analysis and raw results.

    Args:
        state: Current SQL agent state
        llm_client: LLM client for response formatting

    Returns:
        Updated state with formatted response message
    """
    logger.info("SQL AGENT: Formatting final response with LLM...")

    error_message = state.get("error_message")
    execution_result = state.get("execution_result")
    provided_schema_text = state.get("provided_schema_text")
    query = state.get("natural_language_query", "your query")
    generated_sql = state.get("generated_sql", "")

    # Determine query type for the formatter
    if provided_schema_text:
        query_type = "schema_request"
        raw_results = provided_schema_text
    elif error_message:
        query_type = "error"
        raw_results = ""
    elif execution_result:
        query_type = "data_query"
        raw_results = execution_result
    else:
        query_type = "validation_failure"
        raw_results = f"Validation feedback: {state.get('validation_feedback', 'No specific feedback available.')}"

    # Prepare template variables for response formatting
    template_vars = {
        "USER_QUERY": query,
        "QUERY_TYPE": query_type,
        "RAW_RESULTS": raw_results,
        "GENERATED_SQL": generated_sql,
        "ERROR_MESSAGE": error_message or "",
    }

    # Generate the formatting prompt using the workflow template
    llm_formatted_content = ""
    try:
        formatting_prompt = get_processed_prompt("sql_agent/response_formatter", template_vars)

        # Use LLM to format the response
        formatted_response = llm_client.invoke([HumanMessage(content=formatting_prompt)])
        llm_formatted_content = formatted_response.content
        logger.info("SQL AGENT: Response formatted successfully using LLM")

    except Exception as e:
        # Fallback to simple formatting if LLM formatting fails
        logger.warning(f"SQL AGENT: LLM formatting failed, using fallback: {e}")
        if provided_schema_text:
            llm_formatted_content = (
                "## Analysis\n\nHere is the database schema you requested for analysis."
            )
        elif error_message:
            llm_formatted_content = f"## Error Analysis\n\nI encountered an error while processing your request: {error_message}"
        elif execution_result:
            llm_formatted_content = (
                "## Analysis\n\nI've successfully executed your query and retrieved the results."
            )
        else:
            llm_formatted_content = (
                f"## Analysis\n\nI processed your request but couldn't validate or execute the SQL query. "
                f"Validation feedback: {state.get('validation_feedback', 'No specific feedback available.')}"
            )

    # Combine LLM-formatted content with raw results
    final_message_content = llm_formatted_content

    # Add raw results section for non-error cases
    if not error_message and raw_results:
        final_message_content += "\n\n---\n\n"

        if provided_schema_text:
            final_message_content += "## Complete Database Schema\n\n"
            final_message_content += f"```\n{provided_schema_text}\n```"
        elif execution_result:
            final_message_content += "## Complete Query Results\n\n"
            # Check if results look like they might be from a file-based operation
            if "saved to" in execution_result.lower() or "file:" in execution_result.lower():
                # For file-based results, show both the file info AND extract/show sample data
                final_message_content += f"{execution_result}\n\n"

                # Try to extract data from the file result to show in conversation
                # Look for data patterns in the execution result
                if "|" in execution_result or "┃" in execution_result:
                    # Table data is present in the result, extract it
                    lines = execution_result.split("\n")
                    data_section = []
                    in_data_section = False
                    for line in lines:
                        # Look for table-like formatting
                        if ("|" in line or "┃" in line) and not line.strip().startswith("File"):
                            in_data_section = True
                            data_section.append(line)
                        elif in_data_section and line.strip() == "":
                            break

                    if data_section:
                        final_message_content += "**DATA FOR DOWNSTREAM PROCESSING:**\n```\n"
                        final_message_content += "\n".join(data_section[:20])  # Show first 20 rows
                        if len(data_section) > 20:
                            final_message_content += f"\n... ({len(data_section) - 20} more rows)\n"
                        final_message_content += "\n```"
            else:
                final_message_content += f"```\n{execution_result}\n```"
        else:
            final_message_content += "## Raw Results\n\n"
            final_message_content += f"```\n{raw_results}\n```"

    # Add SQL query section if available
    if generated_sql and not error_message:
        final_message_content += "\n\n---\n\n"
        final_message_content += "## SQL Query Used\n\n"
        final_message_content += f"```sql\n{generated_sql}\n```"

    final_message = AIMessage(content=final_message_content, name="sql_agent")

    # Clear all previous messages and set only the final formatted message
    # This prevents intermediate agent messages from appearing in the output
    # We use a list with just the final message to replace all previous messages
    return {
        "messages": [
            final_message
        ],  # This will replace all previous messages due to how LangGraph handles message updates
        "natural_language_query": state.get("natural_language_query"),
        "schema": state.get("schema"),
        "generated_sql": state.get("generated_sql"),
        "validation_status": state.get("validation_status"),
        "validation_feedback": state.get("validation_feedback"),
        "execution_result": state.get("execution_result"),
        "error_message": state.get("error_message"),
        "sql_generation_retries": state.get("sql_generation_retries"),
        "provided_schema_text": state.get("provided_schema_text"),
    }


def handle_error_node(state: SQLAgentState) -> Dict[str, Any]:
    """Handles errors encountered during the process.

    Args:
        state: Current SQL agent state

    Returns:
        Updated state with error message preserved
    """
    error_msg = state.get("error_message", "An unspecified error occurred.")
    logger.warning(f"SQL AGENT: Handling error: {error_msg}")
    return {"error_message": error_msg}


def increment_retry_node(state: SQLAgentState) -> Dict[str, Any]:
    """Increments retry counter and prepares state for retry with error feedback.

    Handles both validation failures and execution errors by feeding error feedback
    back to the agent for self-healing. Preserves the original combined query context
    (user + coordinator + orchestrator) while adding error details.

    Args:
        state: Current SQL agent state

    Returns:
        Updated state with incremented retry count, reset fields, and error feedback
    """
    retries = state.get("sql_generation_retries", 0)
    retry_count = retries + 1

    # Determine error type and feedback
    validation_feedback = state.get("validation_feedback", "")
    execution_error = state.get("error_message", "")

    # Build error feedback message
    error_feedback_parts = []

    if validation_feedback:
        error_feedback_parts.append(f"SQL Validation Failed: {validation_feedback}")

    if execution_error:
        error_feedback_parts.append(f"SQL Execution Failed: {execution_error}")

    # Get the original combined query (preserves coordinator/orchestrator context)
    original_query = state.get("natural_language_query", "")

    # Build messages for retry: original context + error feedback
    messages = []

    if original_query:
        messages.append(HumanMessage(content=original_query))

    if error_feedback_parts:
        error_feedback = "\n\n".join(error_feedback_parts)
        retry_message = (
            f"The previous SQL query failed. Here are the details:\n\n{error_feedback}\n\n"
            f"Please analyze the error(s) above and generate a corrected SQL query. "
            f"Consider:\n"
            f"- Reviewing the database schema using the get_database_schema tool if needed\n"
            f"- Checking table and column names match the schema exactly\n"
            f"- Ensuring proper SQLite syntax\n"
            f"- Handling NULL values and data types correctly"
        )
        messages.append(HumanMessage(content=retry_message))
        logger.info(f"SQL AGENT: Preparing retry (Attempt {retry_count}) with error feedback")
    else:
        logger.warning(
            f"SQL AGENT: Preparing retry (Attempt {retry_count}) but no error feedback available"
        )

    return {
        "sql_generation_retries": retry_count,
        "messages": messages,
        "generated_sql": None,  # Reset for retry
        "provided_schema_text": None,  # Reset for retry
        "validation_status": None,
        "validation_feedback": None,
        "execution_result": None,
        "error_message": None,  # Clear error message for retry
    }


# Conditional edge functions
def check_extraction_result(state: SQLAgentState) -> str:
    """Checks if schema or SQL was successfully extracted.

    Args:
        state: Current SQL agent state

    Returns:
        Next node name to route to
    """
    if state.get("error_message"):
        return "handle_error"
    elif state.get("provided_schema_text"):
        return "format_response"
    elif state.get("generated_sql"):
        return "validate_sql"
    else:
        return "handle_error"


def decide_after_validation(state: SQLAgentState) -> str:
    """Decides the next step after SQL validation.

    Args:
        state: Current SQL agent state

    Returns:
        Next node name to route to
    """
    if state.get("error_message"):
        return "handle_error"

    validation_status = state.get("validation_status")
    retries = state.get("sql_generation_retries", 0)

    if validation_status == "valid":
        return "execute_sql"
    elif retries < MAX_SQL_RETRIES:
        logger.warning(f"SQL AGENT: SQL Invalid. Retrying generation (Attempt {retries + 1})")
        return "increment_retry"
    else:
        logger.error(f"SQL AGENT: SQL Invalid after {MAX_SQL_RETRIES} retries.")
        return "handle_error"


def check_for_errors_after_execution(state: SQLAgentState) -> str:
    """Check for errors after SQL execution and route to retry if possible.

    Enables self-healing by routing execution errors back through the retry mechanism
    if retries are still available.

    Args:
        state: Current SQL agent state

    Returns:
        Next node name to route to
    """
    error_message = state.get("error_message")
    retries = state.get("sql_generation_retries", 0)

    if error_message:
        # Check if we can retry
        if retries < MAX_SQL_RETRIES:
            logger.warning(
                f"SQL AGENT: Execution failed. Retrying generation (Attempt {retries + 1})"
            )
            return "increment_retry"
        else:
            logger.error(
                f"SQL AGENT: Execution failed after {MAX_SQL_RETRIES} retries. "
                f"Error: {error_message}"
            )
        return "handle_error"

    return "continue_to_format"
