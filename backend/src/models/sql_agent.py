"""Structured output models for SQL agent workflow."""

from typing import Literal, Optional, List

from pydantic import BaseModel, Field


class SQLProposal(BaseModel):
    """Structured output for SQL generation.

    Determines whether the agent wants to generate SQL, provide schema, or handle other cases.
    """

    kind: Literal["sql", "schema", "other"] = Field(
        description="The type of response: 'sql' for SQL query generation, 'schema' when user asks about database schema/structure (use this for 'what is the schema?' queries), 'other' for explanations or clarifications that don't require SQL"
    )
    sql: Optional[str] = Field(
        None, description="The generated SQL query (required if kind is 'sql')"
    )
    reason: Optional[str] = Field(
        None, description="Explanation or schema text (required if kind is 'schema' or 'other')"
    )


class SQLValidationResult(BaseModel):
    """Structured output for SQL validation."""

    status: Literal["valid", "invalid", "error"] = Field(
        description="The validation status of the SQL query"
    )
    feedback: str = Field(
        description="Detailed feedback on the validation, including reasons for invalidity or confirmation of validity"
    )
    severity: Optional[Literal["ok", "warn", "fail"]] = Field(
        None,
        description="Severity level for nuanced handling (ok=proceed, warn=proceed with caution, fail=reject)",
    )


class SQLQueryExecution(BaseModel):
    """Represents a single SQL query execution with its results."""

    sql: str = Field(..., description="The SQL query that was executed")
    execution_status: Literal["success", "validation_failed", "execution_error"] = Field(
        ..., description="Status of the execution"
    )
    execution_result: Optional[str] = Field(
        None, description="Raw results from SQL execution (if successful)"
    )
    error_message: Optional[str] = Field(None, description="Error details if execution failed")
    row_count: Optional[int] = Field(None, description="Number of rows returned")


class SQLAgenticResponse(BaseModel):
    """Structured output for agentic SQL agent with natural language response.

    Used in the simplified agentic SQL system where the agent handles
    SQL generation, execution, and formatting internally. The agent
    returns this structured response containing both the natural language
    response (for display) and structured metadata (for extraction/observability).
    """

    # Primary response - natural language formatted response shown to user
    response: str = Field(
        ...,
        description=(
            "Natural language formatted response to show to the user. "
            "This should be a complete, well-formatted response that includes: "
            "- Analysis and insights from the query results "
            "- Key findings and patterns "
            "- Summary of what was found "
            "- **CRITICAL: ALWAYS include ALL SQL queries executed in a 'SQL Queries Used' section** "
            "For schema requests, include the schema information in a readable format. "
            "For errors, explain what went wrong and suggest solutions."
        ),
    )

    # Response type classification
    kind: Literal["sql", "schema", "other", "error"] = Field(
        ...,
        description=(
            "Response type: "
            "'sql' = SQL query was generated and executed successfully, "
            "'schema' = Database schema information was provided, "
            "'other' = Explanation/clarification without SQL execution, "
            "'error' = An error occurred during processing"
        ),
    )

    # PRIMARY SOURCE OF TRUTH: List of all SQL queries executed (optional)
    # Only populated when kind='sql' and queries were actually executed
    # Empty when kind='schema', 'other', or 'error' (no queries executed)
    sql_queries: List[SQLQueryExecution] = Field(
        default_factory=list,
        description=(
            "List of ALL SQL queries executed during this agent run. "
            "REQUIRED when kind='sql' and queries were executed. "
            "OPTIONAL/EMPTY when kind='schema', 'other', or 'error' (no queries executed). "
            "CRITICAL: Include ALL queries you executed, not just the last one. "
            "This provides complete traceability of all database operations performed. "
            "Each entry should contain the SQL query, execution status, execution result, "
            "error_message (if failed), and row_count. "
            "This is the PRIMARY and ONLY source of truth for SQL execution details."
        ),
    )

    # Schema information (when kind='schema')
    schema_text: Optional[str] = Field(
        None,
        description=(
            "Database schema information (required if kind='schema'). "
            "This should contain the complete schema description that was "
            "retrieved and formatted for the user."
        ),
    )

    file_path: Optional[str] = Field(
        None,
        description=(
            "Path to saved CSV file if results were saved to file "
            "(for large datasets or visualization requests)"
        ),
    )

    # Additional context (when kind='other' or 'error')
    reason: Optional[str] = Field(
        None,
        description=(
            "Additional explanation or context (for kind='other' or 'error'). "
            "May contain clarifications, explanations, or detailed error context."
        ),
    )
