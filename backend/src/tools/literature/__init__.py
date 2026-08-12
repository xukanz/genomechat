"""Literature search tools backed by the Europe PMC public REST API.

No API key and no registration required. Four tools:

    search_literature     - find papers by free text plus structured filters
    search_by_doi         - read one paper, including open-access full text
    get_paper_citations   - walk the citation graph forwards or backwards
    get_literature_stats  - corpus orientation, or a hit count for a query

Both the LangChain researcher agent and the SDK path's MCP server
(``src/service/mcp/literature_server.py``) consume these same tool objects.
"""

from src.tools.literature.tools import (
    get_literature_stats,
    get_paper_citations,
    search_by_doi,
    search_literature,
)

__all__ = [
    "get_literature_stats",
    "get_paper_citations",
    "search_by_doi",
    "search_literature",
]
