"""Type definitions for the agent system graph.

Defines routing types and patterns for orchestrator delegation and coordinator decisions.
"""

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class CoordinatorResponse(BaseModel):
    """Coordinator response with structured output for type safety.

    The coordinator uses structured output to determine whether to respond directly
    or hand off to the orchestrator for complex queries.

    Attributes:
        action: Whether to respond directly or hand off to orchestrator
        response: The response content if action is "respond" (required for direct responses)
        reasoning: Optional explanation of the decision for observability
    """

    action: Literal["respond", "handoff_to_orchestrator"] = Field(
        ...,
        description="'respond' for greetings/small talk, 'handoff_to_orchestrator' for complex queries",
    )
    response: Optional[str] = Field(
        None,
        description="Response content when action is 'respond'. Required for direct responses.",
    )
    reasoning: Optional[str] = Field(
        None,
        description="Optional explanation of the decision",
    )


class OrchestratorResponse(BaseModel):
    """Orchestrator response with routing decision, todos update, and final synthesis.

    The orchestrator uses structured output to determine which worker agent
    should handle the next task, or if the workflow is complete. When routing
    to __end__, it should provide a synthesized final response.

    Routing rules:
    - "coder": For Python code execution, S3 operations (list/read/write files),
               mathematical calculations, data analysis, visualizations
    - "sql_agent": For SQL queries, database operations, structured data queries
    - "__end__": When the task is complete, a final comprehensive response has been provided,
                 or no worker agent is needed (simple greeting/clarification).

    Attributes:
        next: The agent to route to, or "__end__" to complete the workflow
        reasoning: Optional explanation of the routing decision for observability
        final_response: Optional final synthesized response when routing to __end__.
                       Should synthesize findings from worker agents into a clear,
                       comprehensive response for the user. REQUIRED when next='__end__'
                       and worker agents have completed their tasks.
        todos_update: Updated todos list with current status. REQUIRED when worker agent completes.
                     Include ALL todos with updated status values (completed/in_progress/pending).
    """

    next: Union[Literal["coder"], Literal["sql_agent"], Literal["__end__"]] = Field(
        ...,
        description=(
            "The agent to route to, or '__end__' to complete the workflow. "
            "Use 'coder' for Python code execution, S3 operations, mathematical calculations, data analysis, or visualizations. "
            "Use 'sql_agent' for SQL queries, database operations, or structured data queries. "
            "Use '__end__' when the task is complete, a final comprehensive response has been provided, or no worker agent is needed."
        ),
    )
    reasoning: Optional[str] = Field(
        None,
        description="Optional explanation of the routing decision for observability and debugging",
    )
    final_response: Optional[str] = Field(
        None,
        description=(
            "Final synthesized response REQUIRED when next='__end__'. "
            "Synthesize findings from worker agents into a clear, comprehensive response. "
            "Should directly address the user's original request, be well-structured, "
            "and cite sources where applicable. Do NOT just say 'Task complete' - provide "
            "the actual synthesized answer/report. Leave empty/null when routing to workers."
        ),
    )
