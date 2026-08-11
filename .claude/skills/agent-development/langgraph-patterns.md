# LangGraph Workflow Patterns

Detailed patterns for building LangGraph workflows. For core concepts, see [SKILL.md](SKILL.md).

## Contents
- [State Management](#state-management)
- [Node Implementation](#node-implementation)
- [Conditional Routing](#conditional-routing)
- [Complete Workflow Example](#complete-workflow-example)

## State Management

```python
from typing import TypedDict, Annotated, Sequence, Optional
from langgraph.graph import StateGraph
from langchain_core.messages import BaseMessage

class ResearchState(TypedDict):
    """State for research workflow."""
    messages: Annotated[Sequence[BaseMessage], "Chat history"]
    query: str
    context: dict
    results: list[dict]
    next_action: str
    error: Optional[str]

# Create workflow graph
workflow = StateGraph(ResearchState)
```

**Best Practice**: Always use TypedDict for explicit type safety.

## Node Implementation

```python
from langchain_core.messages import HumanMessage, AIMessage

async def research_node(state: ResearchState) -> ResearchState:
    """
    Execute research using biomedical researcher agent.

    Args:
        state: Current workflow state with query and context

    Returns:
        Updated state with research results

    Raises:
        ValueError: If query is empty
        APIError: If external API calls fail
    """
    query = state["query"]
    context = state["context"]

    # Reason: Validate input before calling expensive LLM
    if not query:
        return {**state, "error": "Empty query provided"}

    try:
        # Call biomedical researcher agent
        results = await biomedical_researcher.run(query, context)

        return {
            **state,
            "results": results,
            "next_action": "analyze",
            "error": None
        }
    except Exception as e:
        logger.exception(f"Research node failed: {e}")
        return {
            **state,
            "error": str(e),
            "next_action": "retry"
        }

# Add node to workflow
workflow.add_node("research", research_node)
```

## Conditional Routing

```python
def route_next_step(state: ResearchState) -> str:
    """
    Determine next step in workflow based on state.

    Args:
        state: Current workflow state

    Returns:
        Name of next node to execute
    """
    # Reason: Check for errors first to handle failures early
    if state.get("error"):
        return "error_handler"

    next_action = state.get("next_action")

    if next_action == "analyze":
        return "analyze"
    elif next_action == "report":
        return "report"
    elif next_action == "retry":
        return "research"
    else:
        return "end"

# Add conditional routing
workflow.add_conditional_edges(
    "research",
    route_next_step,
    {
        "analyze": "analyze",
        "report": "report",
        "research": "research",
        "error_handler": "error_handler",
        "end": END
    }
)
```

## Complete Workflow Example

```python
from langgraph.graph import StateGraph, END

# Create workflow
workflow = StateGraph(ResearchState)

# Add nodes
workflow.add_node("plan", planning_node)
workflow.add_node("research", research_node)
workflow.add_node("analyze", analysis_node)
workflow.add_node("report", reporting_node)
workflow.add_node("error_handler", error_handler_node)

# Set entry point
workflow.set_entry_point("plan")

# Add edges
workflow.add_edge("plan", "research")
workflow.add_conditional_edges(
    "research",
    route_next_step,
    {
        "analyze": "analyze",
        "report": "report",
        "research": "research",
        "error_handler": "error_handler",
        "end": END
    }
)
workflow.add_edge("analyze", "report")
workflow.add_edge("report", END)
workflow.add_edge("error_handler", END)

# Compile workflow
app = workflow.compile()

# Execute workflow
result = await app.ainvoke({
    "query": "Research query",
    "messages": [],
    "context": {},
    "results": [],
    "next_action": "",
    "error": None
})
```

## State Best Practices

Always use typed state for clarity:

```python
# ✅ Good: Typed state
class WorkflowState(TypedDict):
    """Workflow state with explicit types."""
    query: str
    results: list[dict]
    error: Optional[str]

# ❌ Bad: Untyped state
state = {}  # What fields are available?
```

## Error Handling in Nodes

Implement robust error handling at agent level:

```python
async def agent_node(state: State) -> State:
    """Agent node with comprehensive error handling."""
    try:
        result = await agent.run(state["query"])
        return {**state, "result": result, "error": None}
    except APIError as e:
        logger.error(f"API error in agent: {e}")
        return {**state, "error": f"API error: {e}", "next_action": "retry"}
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        return {**state, "error": f"Invalid input: {e}", "next_action": "end"}
    except Exception as e:
        logger.exception(f"Unexpected error in agent: {e}")
        return {**state, "error": f"Unexpected error: {e}", "next_action": "error_handler"}
```

## Observability

Implement logging and monitoring for agent actions:

```python
import structlog
import time

logger = structlog.get_logger()

async def agent_node(state: State) -> State:
    """Agent node with observability."""
    logger.info(
        "agent_node_start",
        agent="biomedical_researcher",
        query=state["query"]
    )

    start_time = time.time()

    try:
        result = await agent.run(state["query"])

        duration = time.time() - start_time
        logger.info(
            "agent_node_complete",
            agent="biomedical_researcher",
            duration_seconds=duration,
            result_count=len(result)
        )

        return {**state, "result": result}
    except Exception as e:
        logger.exception("agent_node_failed", agent="biomedical_researcher", error=str(e))
        raise
```
