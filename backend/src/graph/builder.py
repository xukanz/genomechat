"""LangGraph builder for the agent system.

Builds the StateGraph with coordinator, orchestrator (middleware-based), and worker nodes.
Uses modular checkpointer system (MongoDB by default, SQLite for testing) for persistent,
multi-user safe state management.

Note:
    The graph builder returns an uncompiled graph. The checkpointer is created
    per-request in the API routes using the checkpointer factory (see checkpointer.py).
"""

from pathlib import Path
from langgraph.graph import StateGraph, START

from src.config.settings import settings
from src.graph.state import AgentState
from src.graph.nodes import (
    coordinator_node,
    orchestrator_node,
    coder_node,
    sql_agent_node,
)


def build_graph():
    """Build the agent workflow graph.

    Architecture:
    - START -> coordinator (initial routing)
    - coordinator -> orchestrator (complex queries) or __end__ (simple responses)
    - orchestrator -> workers (coder, sql_agent) or __end__ (complete)
    - workers -> orchestrator (loop back for coordination)

    The orchestrator uses middleware for planning and structured output for routing.
    Workers are invoked directly in graph nodes, not as subagents.

    Returns:
        Uncompiled StateGraph builder
    """
    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("coder", coder_node)
    builder.add_node("sql_agent", sql_agent_node)

    # Add edges
    builder.add_edge(START, "coordinator")
    # Coordinator routes to orchestrator or __end__ (via Command objects)
    # Orchestrator routes to workers or __end__ (via structured output)
    # Workers route back to orchestrator (via Command objects)

    return builder


def get_checkpointer_db_path() -> str:
    """Get the checkpointer database path from settings.

    Returns:
        Path to SQLite database for checkpointer
    """
    checkpoints_db = settings.checkpointer_db_path

    # Ensure parent directory exists
    db_path = Path(checkpoints_db)
    if not db_path.is_absolute():
        db_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    return str(checkpoints_db)


def create_agent():
    """Create the uncompiled agent graph builder.

    Returns:
        Uncompiled StateGraph builder

    Note:
        The graph is compiled per-request in API routes with a fresh checkpointer
        (via create_checkpointer factory) to avoid event loop binding issues.
        Supports MongoDB (default) and SQLite (testing).
    """
    return build_graph()
