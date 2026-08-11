"""Main agent entry point.

This module provides the uncompiled agent graph builder.
The graph is compiled per-request with AsyncSqliteSaver in API routes.
"""

from src.graph.builder import create_agent

# Global uncompiled graph builder instance
# Graph is compiled per-request with fresh AsyncSqliteSaver (like legacy system)
graph_builder = create_agent()
