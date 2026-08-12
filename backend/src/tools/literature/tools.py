"""Literature search tools backed by Europe PMC.

Four tools with non-overlapping jobs: find papers, read one paper, walk the
citation graph, and size a topic before committing to a search.

Two shapes here follow from the API rather than from preference. Europe PMC has
no relevance score, so there is no ``score_threshold`` — ``sort`` is the only
ranking lever. And ``/search`` ignores ``page`` entirely, so pagination is
cursor-based: callers pass back the cursor the previous call printed.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from langchain_core.tools import tool

from src.service.observability import trace_tool
from src.tools.literature._client import LiteratureAPIError, get_json, get_text
from src.tools.literature._format import (
    format_citation_list,
    format_paper_detail,
    format_search_page,
    format_stats,
)
from src.tools.literature._fulltext import jats_to_text
from src.tools.literature._query import (
    VALID_FILTER_KEYS,
    LiteratureQueryError,
    build_query,
)

logger = logging.getLogger(__name__)

# ``resultType=core`` includes full abstracts; 50 records is already a large
# tool result, and the old ceiling of 100 was ~200 KB in one message.
MAX_SEARCH_LIMIT = 50
# Hub papers have thousands of citations — keep a single hop affordable.
MAX_CITATION_LIMIT = 100

# ``relevance`` omits the parameter, which is Europe PMC's own default.
_SORT_TOKENS: dict[str, Optional[str]] = {
    "relevance": None,
    "cited": "CITED desc",
    "date": "P_PDATE_D desc",
}
_SOURCES = ("MED", "PMC", "PPR")
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_DIRECTIONS = ("citations", "references")


def _clamp(value: Any, low: int, high: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return low


def _resolve_sort(sort: str) -> Optional[str]:
    key = (sort or "relevance").strip().lower()
    if key not in _SORT_TOKENS:
        raise LiteratureQueryError(
            f"Invalid sort '{sort}'. Use one of: {', '.join(_SORT_TOKENS)}."
        )
    return _SORT_TOKENS[key]


def _normalise_paper_id(paper_id: str, source: str) -> tuple[str, str]:
    """Resolve a PMID/PMCID plus its Europe PMC source partition.

    ``source`` is interpolated into a URL path, so the whitelist is a security
    control rather than a convenience.
    """
    pid = (paper_id or "").strip()
    if not pid:
        raise LiteratureQueryError("get_paper_citations requires a 'paper_id'.")
    if "/" in pid:
        raise LiteratureQueryError(
            f"'{pid}' looks like a DOI, but this tool needs a PMID or PMCID. "
            f'Call search_by_doi("{pid}") first and use the PMID from its output.'
        )
    if pid.upper().startswith("PMC"):
        return pid.upper(), "PMC"
    if not pid.isdigit():
        raise LiteratureQueryError(
            f"Unrecognised paper_id '{pid}'. Expected a PMID (digits) or a PMCID (PMC...)."
        )
    src = (source or "MED").strip().upper()
    if src not in _SOURCES:
        raise LiteratureQueryError(
            f"Invalid source '{source}'. Valid sources: {', '.join(_SOURCES)}."
        )
    return pid, src


@trace_tool
@tool
async def search_literature(
    query: str,
    limit: int = 10,
    cursor: str = "*",
    sort: str = "relevance",
    filters: Optional[dict] = None,
) -> str:
    """Search scientific literature in Europe PMC. Returns citations and abstracts.

    Europe PMC matches WORDS, not meaning — there is no semantic search. Supply
    your own synonyms and gene aliases, and try two or three phrasings before
    concluding a topic is unstudied.

    This tool never returns full text. To read a paper, take its DOI from these
    results and call search_by_doi.

    Args:
        query: Free-text terms, e.g. "polygenic risk score breast cancer". Wrap a
            multi-word phrase in double quotes to keep it together. Bare AND, OR
            and NOT work. Do NOT write field syntax here — use filters instead.
        limit: Records to return, 1-50 (default 10).
        cursor: Pagination token. Omit for the first page; afterwards pass the
            cursor printed at the end of the previous result. There are no page
            numbers, so you cannot jump ahead.
        sort: "relevance" (default), "cited" (most-cited first), or "date"
            (newest first — note some records carry bad future dates, so pair it
            with a publication_date_range filter).
        filters: Optional constraints:
            - journal: list of journal names
            - authors: list of author names, e.g. ["Smith J"]
            - title / abstract: list of phrases that must appear in that field
            - publication_date_range: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
            - dois: list of DOIs
            - pmids: list of PubMed IDs — use this to enrich IDs from
              get_paper_citations, or PUBMEDID values from the GWAS catalogue
            - sources: any of ["MED", "PMC", "PPR"]
            - open_access_only: bool
            - exclude_preprints: bool

    Returns:
        Formatted citations with identifiers, citation counts and abstracts.

    Example:
        search_literature("BRCA1 variant classification", limit=5,
                          filters={"publication_date_range":
                                   {"start": "2020-01-01", "end": "2024-12-31"}})
    """
    logger.info(
        "search_literature: query=%r limit=%s sort=%s filters=%s", query, limit, sort, filters
    )
    try:
        epmc_query = build_query(query, filters)
        sent_cursor = (cursor or "*").strip() or "*"
        params: dict[str, Any] = {
            "query": epmc_query,
            "format": "json",
            "resultType": "core",
            "pageSize": _clamp(limit, 1, MAX_SEARCH_LIMIT),
            "cursorMark": sent_cursor,
        }
        sort_token = _resolve_sort(sort)
        if sort_token:
            params["sort"] = sort_token

        data = await get_json("/search", params)
        return format_search_page(data, sent_cursor, epmc_query)
    except (LiteratureQueryError, LiteratureAPIError) as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001
        logger.error("search_literature failed unexpectedly", exc_info=True)
        return f"Error: Unexpected failure in search_literature: {e}"


@trace_tool
@tool
async def get_paper_citations(
    paper_id: str,
    source: str = "MED",
    direction: str = "citations",
    limit: int = 25,
    page: int = 1,
) -> str:
    """Walk the citation graph around a paper. Needs a PMID or PMCID, not a DOI.

    Use direction="citations" to find work that CITED this paper (newer:
    replications, extensions, contradictions), or direction="references" to read
    its bibliography (older: the foundations it built on).

    Results carry IDs, titles, authors and years but NO DOI and NO abstract. To
    read them, collect the PMIDs and enrich them in ONE batched call:
    search_literature(query="", filters={"pmids": ["111", "222"]}).

    Args:
        paper_id: PubMed ID (digits) or PMC ID ("PMC1234567"). A PUBMEDID from
            the GWAS catalogue can be passed directly.
        source: "MED" (PubMed), "PMC", or "PPR" (preprints). Ignored for a PMCID.
        direction: "citations" or "references".
        limit: Records per page, 1-100 (default 25).
        page: 1-based page number. Unlike search, this endpoint does paginate
            by page number.

    Returns:
        Formatted list of related papers, with the total count so you can tell a
        hub paper from a dead end.

    Example:
        get_paper_citations("35039532", direction="references", limit=20)
    """
    logger.info(
        "get_paper_citations: id=%r source=%s direction=%s page=%s",
        paper_id,
        source,
        direction,
        page,
    )
    try:
        pid, src = _normalise_paper_id(paper_id, source)
        mode = (direction or "citations").strip().lower()
        if mode not in _DIRECTIONS:
            raise LiteratureQueryError(
                f"Invalid direction '{direction}'. Use 'citations' or 'references'."
            )
        page_number = max(1, _clamp(page, 1, 10_000))
        params = {
            "format": "json",
            "pageSize": _clamp(limit, 1, MAX_CITATION_LIMIT),
            "page": page_number,
        }
        data = await get_json(f"/{src}/{pid}/{mode}", params)
        return format_citation_list(data, pid, src, mode, page_number)
    except (LiteratureQueryError, LiteratureAPIError) as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001
        logger.error("get_paper_citations failed unexpectedly", exc_info=True)
        return f"Error: Unexpected failure in get_paper_citations: {e}"


@trace_tool
@tool
async def search_by_doi(doi: str, include_full_text: bool = True) -> str:
    """Look up one paper by DOI. The only tool that returns full text.

    Full text exists only for the open-access subset. When a paper is not open
    access you get the citation, identifiers and abstract instead — that is a
    normal outcome, not a failure, and retrying will not change it.

    Args:
        doi: Digital Object Identifier, e.g. "10.1038/s41523-021-00361-2".
        include_full_text: Fetch open-access full text when available
            (default True). Set False for a fast metadata-only lookup.

    Returns:
        Citation, identifiers, abstract, and full text where available.

    Example:
        search_by_doi("10.1038/s41523-021-00361-2")
    """
    logger.info("search_by_doi: doi=%r include_full_text=%s", doi, include_full_text)
    try:
        clean_doi = (doi or "").strip()
        if not _DOI_RE.match(clean_doi):
            return (
                f"Error: Invalid DOI format: '{doi}'. "
                'A DOI looks like "10.1038/s41523-021-00361-2".'
            )

        data = await get_json(
            "/search",
            {
                "query": build_query("", {"dois": [clean_doi]}),
                "format": "json",
                "resultType": "core",
                "pageSize": 1,
            },
        )
        results = (data.get("resultList") or {}).get("result") or []
        if not results:
            return f"Error: No paper found for DOI {clean_doi} in Europe PMC."

        record = results[0]
        full_text, note = None, None
        if include_full_text:
            full_text, note = await _fetch_full_text(record)
        return format_paper_detail(record, full_text, note)
    except (LiteratureQueryError, LiteratureAPIError) as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001
        logger.error("search_by_doi failed unexpectedly", exc_info=True)
        return f"Error: Unexpected failure in search_by_doi: {e}"


async def _fetch_full_text(record: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Fetch and parse open-access full text, or explain why there is none.

    Returns ``(text, note)`` and never raises. The abstract has already been
    fetched successfully by this point, so no full-text problem — 404, 406,
    timeout — may be allowed to turn the whole lookup into an error and throw
    that abstract away.
    """
    pmcid = record.get("pmcid")
    if record.get("isOpenAccess") != "Y" or not pmcid or record.get("inEPMC") != "Y":
        return None, (
            "[Not open access - citation, identifiers and abstract only. "
            "This is expected for subscription content; do not retry.]"
        )

    try:
        xml = await get_text(f"/{pmcid}/fullTextXML", allow_404=True)
    except LiteratureAPIError as e:
        logger.warning("Full-text fetch failed for %s: %s", pmcid, e)
        return None, f"[Full text unavailable for {pmcid} ({e}); abstract shown above.]"
    if xml is None:
        return None, f"[Full text not retrievable for {pmcid}; abstract shown above.]"

    text = jats_to_text(xml)
    if not text:
        return None, f"[Full text for {pmcid} could not be parsed; abstract shown above.]"
    return text, None


@trace_tool
@tool
async def get_literature_stats(
    query: Optional[str] = None,
    filters: Optional[dict] = None,
) -> str:
    """Describe the Europe PMC corpus, or count hits for a query without fetching them.

    Call with no arguments to see corpus size, coverage and the filter vocabulary.
    Call with a query or filters to get just a hit count — a cheap way to check
    whether a search is worth running before spending context on results.

    Args:
        query: Optional free-text query to count, same syntax as search_literature.
        filters: Optional filters to count, same keys as search_literature.

    Returns:
        Corpus description, or the number of matching records.

    Example:
        get_literature_stats(query="polygenic risk score",
                             filters={"open_access_only": True})
    """
    logger.info("get_literature_stats: query=%r filters=%s", query, filters)
    try:
        probing = bool(query) or bool(filters)
        epmc_query = build_query(query or "", filters) if probing else "*"
        data = await get_json(
            "/search", {"query": epmc_query, "format": "json", "pageSize": 1}
        )
        return format_stats(
            data.get("hitCount", 0),
            epmc_query if probing else None,
            sorted(VALID_FILTER_KEYS),
        )
    except (LiteratureQueryError, LiteratureAPIError) as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001
        logger.error("get_literature_stats failed unexpectedly", exc_info=True)
        return f"Error: Unexpected failure in get_literature_stats: {e}"
