"""SQL execution pipeline tool that wraps validation, execution, and error handling.

Provides a single tool interface for SQL validation → execution → error handling
for use in the agentic SQL agent system.
"""

import logging
import re
from typing import Optional

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from src.config.database_registry import get_active_profile_from_context
from src.config.settings import settings
from src.models.sql_agent import SQLValidationResult
from src.prompts.template import get_processed_prompt
from src.service.llm import LLMService
from src.service.observability import trace_tool
from src.tools.database import execute_sql_query, execute_sql_query_and_save, get_database_manager

logger = logging.getLogger(__name__)


@trace_tool
@tool
def execute_sql_pipeline(
    sql_query: str,
    user_query: str,
    database_schema: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Execute SQL query with automatic validation and error handling.

    This tool performs a complete SQL execution pipeline:
    1. Validates SQL syntax and logic using LLM
    2. Executes SQL if valid (with safety guards)
    3. Handles errors and provides feedback for retries

    Args:
        sql_query: The SQL query to execute
        user_query: Original user query for context
        database_schema: Database schema (optional, will fetch if not provided)
        description: Optional comprehensive description of what the query does and its purpose.
                    This description will be saved in file metadata for traceability and
                    used by downstream agents (e.g., coder agent) for context.
                    Examples:
                    - "Clinical significance distribution showing frequency and percentage of each category"
                    - "Variant count grouped by gene symbol with total occurrences"
                    - "Chromosomal variant density with statistical breakdown"

    Returns:
        Structured result string with status, feedback, and results.
        Format:
        - SUCCESS: <execution_result> on success
        - VALIDATION_FAILED: <feedback> on validation failure
        - EXECUTION_ERROR: <error> on execution error
    """
    logger.info(f"SQL PIPELINE: Executing pipeline for query: {sql_query[:100]}...")

    # Step 1: Validate SQL
    validation_result = _validate_sql(sql_query, user_query, database_schema)

    if validation_result.status != "valid":
        error_msg = f"VALIDATION_FAILED: {validation_result.feedback}\n\nSQL: {sql_query}"
        logger.warning(f"SQL PIPELINE: Validation failed - {validation_result.feedback}")
        return error_msg

    # Step 2: Execute SQL (with guards)
    try:
        execution_result = _execute_sql_with_guards(sql_query, user_query, description)
        logger.info("SQL PIPELINE: Execution successful")
        return f"SUCCESS: {execution_result}"
    except Exception as e:
        error_msg = f"EXECUTION_ERROR: {str(e)}\n\nSQL: {sql_query}"
        logger.error(f"SQL PIPELINE: Execution failed - {e}")
        return error_msg


def _validate_sql(
    sql_query: str, user_query: str, database_schema: Optional[str]
) -> SQLValidationResult:
    """Validate SQL using LLM with structured output."""
    llm_client = LLMService.get_llm_by_agent("sql_agent", temperature=0.0, streaming=False)

    # Fetch schema if not provided
    if not database_schema:
        try:
            db_manager = get_database_manager()
            database_schema = db_manager.load_schema_description()
        except Exception as e:
            logger.warning(f"SQL PIPELINE: Could not fetch schema: {e}")
            database_schema = "Schema not available for validation."

    # Get SQL dialect from active database profile (uses request context)
    try:
        profile = get_active_profile_from_context()
        sql_dialect = profile.sql_dialect.upper()  # "SQLITE" or "POSTGRESQL"
        database_name = profile.display_name
    except Exception:
        sql_dialect = "SQL"
        database_name = "the database"

    template_vars = {
        "DATABASE_SCHEMA": database_schema,
        "USER_QUERY": user_query,
        "GENERATED_SQL": sql_query,
        "SQL_DIALECT": sql_dialect,
        "DATABASE_NAME": database_name,
    }

    prompt_str = get_processed_prompt("sql_agent/sql_validator", template_vars)
    method = LLMService.structured_output_method()
    structured_llm = llm_client.with_structured_output(SQLValidationResult, method=method)

    try:
        validation_result = structured_llm.invoke([HumanMessage(content=prompt_str)])
        logger.info(f"SQL PIPELINE: Validation result: {validation_result.status}")
        return validation_result
    except Exception as e:
        logger.error(f"SQL PIPELINE: Validation error: {e}")
        return SQLValidationResult(status="error", feedback=f"Failed during validation: {str(e)}")


def _execute_sql_with_guards(
    sql_query: str, user_query: str, description: Optional[str] = None
) -> str:
    """Execute SQL with safety guards (DDL checks, adaptive LIMIT, etc.).

    Args:
        sql_query: The SQL query to execute
        user_query: Original user query for context
        description: Optional comprehensive description of what the query does
    """
    query_lower = sql_query.lower().strip()

    # DDL guard: reject CREATE/DROP/ALTER/TRUNCATE without approval
    ddl_patterns = [r"\bCREATE\b", r"\bDROP\b", r"\bALTER\b", r"\bTRUNCATE\b"]
    if any(re.search(pattern, query_lower, re.IGNORECASE) for pattern in ddl_patterns):
        raise ValueError("DDL detected (CREATE/DROP/ALTER/TRUNCATE); requires human approval.")

    # Use provided description or fallback to user_query (with truncation if needed)
    query_description = description or user_query
    if not description and len(user_query) > 100:
        query_description = user_query[:100] + "..."

    # Check if force-save is enabled via environment variable
    force_save_all = getattr(settings, "sql_always_save_to_s3", False)

    if force_save_all:
        logger.info("SQL PIPELINE: Force-save enabled - saving all queries to S3")
        return execute_sql_query_and_save.invoke(
            {"query": sql_query, "description": query_description}
        )

    # Check for visualization/plotting indicators - coder agent needs CSV files
    user_query_lower = user_query.lower()
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
                "SQL PIPELINE: Using file-based execution for visualization/plotting "
                "(coder agent needs CSV files)"
            )
        else:
            logger.info(
                "SQL PIPELINE: Using file-based execution for potentially large/complex results"
            )

        return execute_sql_query_and_save.invoke(
            {"query": sql_query, "description": query_description}
        )
    else:
        # Apply adaptive LIMIT if not present
        if not re.search(r"\blimit\b", query_lower, re.IGNORECASE):
            sql_query = f"{sql_query.rstrip(';')} LIMIT 1000"
            logger.info("SQL PIPELINE: Applied adaptive LIMIT 1000 for first pass")

        logger.info("SQL PIPELINE: Using standard execution for smaller expected results")
        return execute_sql_query.invoke({"query": sql_query})
