"""Rendering Europe PMC responses into text for the researcher agent.

Two things here are load-bearing rather than cosmetic:

* **Every success string starts with our own text**, never paper-derived
  content. That is what lets the MCP layer classify results by an ``"Error: "``
  prefix without a paper abstract ever being mistaken for a failure.
* **Pagination advertises a cursor only when one genuinely exists.** Europe PMC
  echoes the cursor you sent once you walk off the end, and omits the key
  entirely when the result set fits in one page. Advertising unconditionally
  would loop the agent until it burned its turn budget.
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional

# Europe PMC embeds presentation markup in titles and abstracts
# (``<i>BRCA1</i>``, ``<h4>Background</h4>``). It carries no meaning for the
# agent and wastes context, so strip it.
_TAG_RE = re.compile(r"<[^>]{1,80}>")
_WS_RE = re.compile(r"\s+")

# ``resultType=core`` carries the full abstract, often 2000+ characters. Ten of
# those is already a large tool result, so cap each one.
ABSTRACT_MAX_CHARS = 1500
# Whole paper if it fits, otherwise a generous preview — a DOI lookup is an
# explicit request for one specific paper, so it earns a bigger budget.
FULL_TEXT_INLINE_LIMIT = 15_000
FULL_TEXT_PREVIEW_CHARS = 10_000


def clean(text: Any) -> str:
    """Strip embedded HTML markup and normalise whitespace."""
    if not text:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", str(text)))).strip()


def _journal_name(record: dict[str, Any]) -> str:
    info = record.get("journalInfo") or {}
    journal = info.get("journal") or {}
    # Preprints carry no journalInfo; the server name lives under
    # bookOrReportDetails.publisher (e.g. "bioRxiv").
    report = record.get("bookOrReportDetails") or {}
    return clean(
        journal.get("title")
        or journal.get("medlineAbbreviation")
        or record.get("journalAbbreviation")
        or report.get("publisher")
        or "Unknown journal"
    )


def format_citation(record: dict[str, Any]) -> str:
    """One-line citation: ``Authors (Year). Title. Journal. DOI: x. Available at: url``."""
    authors = clean(record.get("authorString")) or "Unknown authors"
    year = record.get("pubYear") or "n.d."
    title = clean(record.get("title")).rstrip(".") or "Untitled"
    journal = _journal_name(record)

    citation = f"{authors} ({year}). {title}. {journal}."
    doi = record.get("doi")
    if doi:
        return f"{citation} DOI: {doi}. Available at: https://doi.org/{doi}"
    pmid = record.get("pmid") or record.get("id")
    return f"{citation} PMID: {pmid}" if pmid else citation


def _identifier_line(record: dict[str, Any]) -> str:
    bits = []
    if record.get("pmid"):
        bits.append(f"PMID: {record['pmid']}")
    if record.get("pmcid"):
        bits.append(f"PMCID: {record['pmcid']}")
    if record.get("source"):
        bits.append(f"Source: {record['source']}")
    if record.get("citedByCount") is not None:
        bits.append(f"Cited by: {record['citedByCount']}")
    bits.append("Open access: yes" if record.get("isOpenAccess") == "Y" else "Open access: no")
    if record.get("source") == "PPR":
        bits.append("PREPRINT - not peer reviewed")
    return " | ".join(bits)


def _abstract_block(record: dict[str, Any], limit: int = ABSTRACT_MAX_CHARS) -> str:
    """Render the abstract, stating absence explicitly.

    Silently omitting the field invites the agent to infer findings from the
    title, which is exactly the failure mode worth preventing.
    """
    abstract = clean(record.get("abstractText"))
    if not abstract:
        return "   [No abstract available]"
    if len(abstract) > limit:
        return f"   Abstract: {abstract[:limit]}... [abstract truncated]"
    return f"   Abstract: {abstract}"


def format_record(record: dict[str, Any], index: int) -> str:
    return "\n".join(
        [
            f"{index}. {format_citation(record)}",
            f"   {_identifier_line(record)}",
            _abstract_block(record),
        ]
    )


def _pagination_footer(data: dict[str, Any], sent_cursor: str, count: int) -> str:
    """Advertise the next cursor only when the API actually offers one.

    Termination has two shapes, both verified live: the key is absent when
    everything fitted in one page, and it echoes the cursor you sent (alongside
    zero results) once you walk past the end.
    """
    next_cursor = data.get("nextCursorMark")
    if not next_cursor or next_cursor == sent_cursor or count == 0:
        return "\n[End of results]"
    return (
        f"\nMore results available. To continue, call again with "
        f'cursor="{next_cursor}" (all other arguments unchanged).'
    )


def format_search_page(data: dict[str, Any], sent_cursor: str, query: str) -> str:
    """Render a ``/search`` response: header, records, pagination footer."""
    results = (data.get("resultList") or {}).get("result") or []
    hit_count = data.get("hitCount", 0)

    if not results:
        return (
            f"No results found for query '{query}'. "
            "Europe PMC matches words, not meaning — try broader terms, "
            "alternative gene or disease names, or fewer filters."
        )

    parts = [f"Found {len(results)} of {hit_count:,} matching records:\n"]
    parts.extend(format_record(r, i) for i, r in enumerate(results, 1))
    parts.append(_pagination_footer(data, sent_cursor, len(results)))
    return "\n".join(parts)


def format_citation_list(
    data: dict[str, Any],
    paper_id: str,
    source: str,
    direction: str,
    page: int,
) -> str:
    """Render a ``/citations`` or ``/references`` response.

    These records carry no DOI and no abstract, so the footer tells the agent
    how to enrich them in one batched call rather than one lookup per hit.
    """
    key = "citationList" if direction == "citations" else "referenceList"
    item_key = "citation" if direction == "citations" else "reference"
    items = (data.get(key) or {}).get(item_key) or []
    hit_count = data.get("hitCount", 0)

    relation = "citing" if direction == "citations" else "referenced by"
    if not items:
        return (
            f"No {direction} found for {source}/{paper_id}"
            f"{f' on page {page}' if page > 1 else ''}."
        )

    parts = [
        f"Found {len(items)} of {hit_count:,} papers {relation} "
        f"{source}/{paper_id} (page {page}):\n"
    ]
    for i, item in enumerate(items, 1):
        authors = clean(item.get("authorString")) or "Unknown authors"
        year = item.get("pubYear") or "n.d."
        title = clean(item.get("title")).rstrip(".") or "Untitled"
        journal = clean(item.get("journalAbbreviation")) or "Unknown journal"
        parts.append(f"{i}. {authors} ({year}). {title}. {journal}.")
        detail = f"   ID: {item.get('id')} | Source: {item.get('source')}"
        if item.get("citedByCount") is not None:
            detail += f" | Cited by: {item['citedByCount']}"
        parts.append(detail)

    pmids = [str(i["id"]) for i in items if i.get("source") == "MED" and i.get("id")]
    if pmids:
        sample = ", ".join(f'"{p}"' for p in pmids[:5])
        suffix = ", ..." if len(pmids) > 5 else ""
        parts.append(
            "\nThese records have no DOI or abstract. To read them, enrich the "
            "IDs in ONE batched call rather than one lookup each:\n"
            f'   search_literature(query="", filters={{"pmids": [{sample}{suffix}]}})'
        )
    return "\n".join(parts)


def format_paper_detail(
    record: dict[str, Any],
    full_text: Optional[str],
    full_text_note: Optional[str] = None,
) -> str:
    """Render a single paper for ``search_by_doi``: citation, abstract, full text."""
    parts = [
        "Paper found:",
        format_citation(record),
        _identifier_line(record),
        "",
        _abstract_block(record, limit=ABSTRACT_MAX_CHARS * 2).lstrip(),
    ]

    if full_text_note:
        parts.append(f"\n{full_text_note}")

    if full_text:
        length = len(full_text)
        parts.append(f"\nFull text: {length:,} characters")
        if length <= FULL_TEXT_INLINE_LIMIT:
            parts.append(full_text)
        else:
            parts.append(f"Preview (first {FULL_TEXT_PREVIEW_CHARS:,} characters):")
            parts.append(full_text[:FULL_TEXT_PREVIEW_CHARS] + "...")
            parts.append(f"[Content truncated - full text is {length:,} characters total]")
    return "\n".join(parts)


def format_stats(hit_count: int, query: Optional[str], valid_filter_keys: list[str]) -> str:
    """Render corpus orientation, or a hit-count probe for a specific query."""
    if query is not None:
        return (
            f"{hit_count:,} records match that query.\n"
            "Use this to scope before searching: 0 means loosen the terms or "
            "drop a filter; tens of thousands means add filters."
        )
    return "\n".join(
        [
            f"Europe PMC: {hit_count:,} records.",
            "",
            "Coverage:",
            "  MED - MEDLINE/PubMed abstracts and metadata",
            "  PMC - PubMed Central, includes open-access full text",
            "  PPR - preprint servers (bioRxiv, medRxiv); NOT peer reviewed",
            "",
            "Full text is available only for the open-access subset, and only "
            "through search_by_doi.",
            "",
            f"Filter keys accepted by search_literature: {', '.join(valid_filter_keys)}",
        ]
    )
