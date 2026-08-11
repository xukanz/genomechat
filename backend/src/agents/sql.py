"""SQL agent factory for database interaction workflows.

Creates a LangGraph subgraph for SQL database interaction with validation,
execution, and response formatting capabilities. Supports switching between
graph-based and agentic systems via configuration.
"""

from typing import Any

from src.agents.sql_agent.graph import create_sql_agent_graph
from src.agents.sql_agent.graph_agentic import create_sql_agent_agentic_graph
from src.config.sql_agent import sql_agent_config


def create_sql_agent_agentic() -> Any:
    """Create the agentic SQL agent graph for database interaction.

    The agentic SQL agent uses a simplified LangGraph structure with a single
    agent that handles SQL generation, execution, and formatting internally.
    It includes tools for schema access, sample data retrieval, and SQL execution
    pipeline (validation + execution).

    Returns:
        Compiled LangGraph agent for agentic SQL database interaction
    """
    return create_sql_agent_agentic_graph()


def create_sql_agent() -> Any:
    """Create the SQL agent graph for database interaction.

    The SQL agent uses LangGraph to orchestrate SQL generation, validation,
    execution, and response formatting. It includes tools for schema access
    and sample data retrieval.

    Supports two modes:
    - "graph": Multi-node graph with explicit validation/execution nodes
    - "agentic": Simplified single-agent system with pipeline tool

    Returns:
        Compiled LangGraph agent for SQL database interaction
    """
    if sql_agent_config.sql_agent_mode == "agentic":
        return create_sql_agent_agentic()
    else:
        return create_sql_agent_graph()


# Global SQL agent instance (used by sql_agent_node)
# Created lazily to avoid circular imports
_sql_agent = None


def get_sql_agent() -> Any:
    """Get or create the SQL agent instance.

    Returns the appropriate SQL agent based on configuration:
    - "graph": Graph-based system with multiple nodes
    - "agentic": Agentic system with single agent and tools
    """
    global _sql_agent
    if _sql_agent is None:
        _sql_agent = create_sql_agent()
    return _sql_agent
