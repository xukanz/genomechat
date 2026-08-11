"""State management for the agent system.

Defines the AgentState TypedDict and Plan models for observability.
"""

from typing import Any, Literal, Optional

from langgraph.graph import MessagesState

from src.config.code_language import CodeLanguageType
from src.config.research_mode import ResearchModeType
from src.models.plan import Plan


class AgentState(MessagesState):
    """State for the agent system, extends MessagesState with plan field.

    The plan field enables frontend observability of the agent's execution plan.
    This state is used by the LangGraph StateGraph to coordinate between nodes.
    """

    # Plan for task tracking and observability (updated by manage_plan tool)
    # Contains structured steps with agent assignments, descriptions, and status
    plan: Optional[Plan] = None

    # Current step index for tracking progress
    current_step_index: int = 0

    # Structured output from agent (when using response_format)
    structured_response: Optional[Any] = None  # OrchestratorResponse instance

    # Research mode for controlling research depth
    research_mode: ResearchModeType = "standard"

    # Code language for controlling coder agent runtime (python, r, auto)
    code_language: CodeLanguageType = "python"

    # Thread ID for conversation tracking (extracted from config)
    thread_id: Optional[str] = None

    # Project ID for loading project-specific resources (e.g., snippets)
    project_id: Optional[str] = None

    # Database ID for request-scoped database selection (e.g., "clinvar", "gwas")
    database_id: Optional[str] = None


class SQLAgentState(MessagesState):
    """State for SQL agent workflow, extends MessagesState with SQL-specific fields.

    Used by the SQL agent subgraph for managing SQL generation, validation, and execution workflow.
    """

    # User query
    natural_language_query: Optional[str] = None

    # Schema information
    schema: Optional[str] = None

    # SQL generation
    generated_sql: Optional[str] = None
    provided_schema_text: Optional[str] = None  # For schema-only requests

    # Structured output from agent (when using response_format)
    structured_response: Optional[Any] = None  # SQLProposal instance

    # Validation
    validation_status: Optional[Literal["valid", "invalid", "error"]] = None
    validation_feedback: Optional[str] = None

    # Execution
    execution_result: Optional[str] = None

    # Error handling
    error_message: Optional[str] = None
    sql_generation_retries: int = 0


class SQLAgenticState(MessagesState):
    """State for agentic SQL agent workflow, extends MessagesState with simplified fields.

    Used by the agentic SQL agent subgraph. Simpler than SQLAgentState since
    validation and execution are handled internally by the execute_sql_pipeline tool.

    Note: Schema is not stored in state as it's handled by tools and included
    in SQLAgenticResponse when needed.
    """

    # User query (combined from prepare_sql_query_node_agentic)
    natural_language_query: Optional[str] = None

    # Structured output from agent (when using response_format)
    # Contains SQLAgenticResponse with all execution details, schema info, and natural language response
    structured_response: Optional[Any] = None  # SQLAgenticResponse instance

    # Retry counter (safety guard)
    sql_generation_retries: int = 0
