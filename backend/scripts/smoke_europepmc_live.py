"""Europe PMC live smoke — exercises all four literature tools for real.

The unit tests mock httpx, so they prove the wiring but not that Europe PMC
still behaves the way the implementation assumes. This script checks the
assumptions that would silently produce wrong results if the API changed:

- keyword search returns records and a usable pagination cursor
- cursor chaining advances, and terminates instead of looping forever
- SRC must be unquoted while multi-word JOURNAL must be quoted
- a PMID resolves through EXT_ID (the GWAS PUBMEDID bridge)
- open-access full text parses out of JATS; non-OA degrades to abstract
- citation traversal works in both directions and paginates by page number

Usage:
    cd backend && uv run python scripts/smoke_europepmc_live.py

Needs outbound HTTPS to www.ebi.ac.uk. No API key. Exits 0 on pass, 1 on the
first failure. Costs nothing — Europe PMC is free.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
sys.path.insert(0, str(_BACKEND))

from src.tools.literature import (  # noqa: E402
    get_literature_stats,
    get_paper_citations,
    search_by_doi,
    search_literature,
)
from src.tools.literature._query import build_query  # noqa: E402

# A stable, well-cited open-access paper with a bibliography and citations.
OA_DOI = "10.1038/s41523-021-00361-2"
OA_PMID = "35039532"
# Hallmarks of Cancer: heavily cited and firmly behind a paywall.
CLOSED_DOI = "10.1016/j.cell.2011.02.013"

_failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    if not condition:
        _failures.append(name)


async def smoke_search() -> None:
    print("\nsearch_literature")
    result = await search_literature.ainvoke({"query": "BRCA1 variant classification", "limit": 3})
    check("returns records", result.startswith("Found "), result[:60])
    check("reports the total hit count", " of " in result.split("\n")[0])
    check(
        "includes an abstract or states its absence",
        "Abstract:" in result or "[No abstract" in result,
    )
    check("offers a pagination cursor", 'cursor="' in result)

    empty = await search_literature.ainvoke(
        {"query": "zzzq nonexistent gibberish term xyzzy", "limit": 3}
    )
    check("zero hits is not an error", not empty.startswith("Error"), empty[:60])


async def smoke_pagination() -> None:
    print("\npagination (cursor chaining and termination)")
    first = await search_literature.ainvoke({"query": "BRCA1", "limit": 2})
    marker = 'cursor="'
    check("page 1 advertises a cursor", marker in first)
    if marker not in first:
        return
    cursor = first.split(marker, 1)[1].split('"', 1)[0]
    second = await search_literature.ainvoke({"query": "BRCA1", "limit": 2, "cursor": cursor})
    check("page 2 returns different records", second.startswith("Found "))
    check(
        "page 2 content differs from page 1",
        second.split("\n")[2:4] != first.split("\n")[2:4],
    )

    # A query with very few hits must terminate rather than advertise forever.
    narrow = await search_literature.ainvoke(
        {"query": "", "filters": {"pmids": [OA_PMID]}, "limit": 10}
    )
    check("exhausted result set terminates", "[End of results]" in narrow)


async def smoke_query_syntax() -> None:
    print("\nquery syntax (the two rules a uniform quoting scheme gets wrong)")
    # SRC must be bare: SRC:"MED" returns zero hits.
    src_query = build_query("", {"sources": ["MED"]})
    check("SRC is emitted unquoted", src_query == "SRC:MED", src_query)
    result = await search_literature.ainvoke(
        {"query": "BRCA1", "filters": {"sources": ["MED"]}, "limit": 1}
    )
    check("SRC filter returns hits", result.startswith("Found "), result[:60])

    # Multi-word JOURNAL must be quoted or the tail becomes a free-text term.
    journal_query = build_query("", {"journal": ["Nature Genetics"]})
    check("JOURNAL is emitted quoted", journal_query == 'JOURNAL:"Nature Genetics"', journal_query)
    result = await search_literature.ainvoke(
        {"query": "variant", "filters": {"journal": ["Nature Genetics"]}, "limit": 1}
    )
    check("JOURNAL filter returns hits", result.startswith("Found "), result[:60])


async def smoke_pmid_bridge() -> None:
    print("\nPMID bridge (GWAS PUBMEDID -> literature)")
    result = await search_literature.ainvoke({"query": "", "filters": {"pmids": [OA_PMID]}})
    check(
        "a bare PMID resolves to exactly one record", result.startswith("Found 1 of 1"), result[:60]
    )
    check("the resolved record is the expected paper", "heterozygosity" in result.lower())

    batch = await search_literature.ainvoke(
        {"query": "", "filters": {"pmids": [OA_PMID, "22505045"]}}
    )
    check("PMIDs batch into one call", batch.startswith("Found 2 of 2"), batch[:60])


async def smoke_doi_and_fulltext() -> None:
    print("\nsearch_by_doi")
    oa = await search_by_doi.ainvoke({"doi": OA_DOI})
    check("open-access lookup succeeds", oa.startswith("Paper found:"), oa[:60])
    check("full text was retrieved", "Full text:" in oa)
    check("JATS parsed into readable prose", "## " in oa)
    check("no raw XML leaked through", "<article" not in oa and "<sec>" not in oa)

    closed = await search_by_doi.ainvoke({"doi": CLOSED_DOI})
    check("non-OA lookup is not an error", not closed.startswith("Error"), closed[:60])
    check("non-OA still returns an abstract", "Abstract:" in closed)
    check("non-OA explains why there is no full text", "[Not open access" in closed)

    missing = await search_by_doi.ainvoke({"doi": "10.9999/does.not.exist"})
    check("unknown DOI reports not found", missing.startswith("Error: No paper found"))


async def smoke_citations() -> None:
    print("\nget_paper_citations")
    refs = await get_paper_citations.ainvoke(
        {"paper_id": OA_PMID, "direction": "references", "limit": 3}
    )
    check("references traversal works", refs.startswith("Found "), refs[:60])
    check("teaches the batched enrichment call", "pmids" in refs)

    cites = await get_paper_citations.ainvoke(
        {"paper_id": OA_PMID, "direction": "citations", "limit": 3}
    )
    check("citations traversal works", cites.startswith("Found "), cites[:60])

    page2 = await get_paper_citations.ainvoke(
        {"paper_id": OA_PMID, "direction": "references", "limit": 3, "page": 2}
    )
    check("this endpoint paginates by page number", page2.startswith("Found "))
    check("page 2 differs from page 1", page2.split("\n")[2:4] != refs.split("\n")[2:4])

    rejected = await get_paper_citations.ainvoke({"paper_id": OA_DOI})
    check("a DOI is rejected with a recovery hint", "search_by_doi" in rejected)


async def smoke_stats() -> None:
    print("\nget_literature_stats")
    orientation = await get_literature_stats.ainvoke({})
    check("reports corpus size", "Europe PMC:" in orientation, orientation.split("\n")[0])
    check("lists the filter vocabulary", "pmids" in orientation)

    probe = await get_literature_stats.ainvoke({"query": "polygenic risk score"})
    check("probe mode returns a count", "records match" in probe, probe.split("\n")[0])
    check("probe mode returns no result bodies", "Abstract:" not in probe)


async def main() -> int:
    print("Europe PMC live smoke — no API key required")
    for stage in (
        smoke_search,
        smoke_pagination,
        smoke_query_syntax,
        smoke_pmid_bridge,
        smoke_doi_and_fulltext,
        smoke_citations,
        smoke_stats,
    ):
        try:
            await stage()
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {stage.__name__} raised: {e}")
            _failures.append(stage.__name__)

    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): {', '.join(_failures)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
