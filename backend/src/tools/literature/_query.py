"""Europe PMC query construction.

The ``query`` argument is always treated as **free text**, never as Europe PMC
syntax; every structured need goes through ``filters``. That split is what makes
injection impossible: a user string can only ever land inside a quoted term.

Quoting is field-dependent, and both directions were verified against the live
API — a uniform rule breaks one case or the other:

    SRC:MED                    -> 1 hit       SRC:"MED"                 -> 0 hits
    JOURNAL:"Nature Genetics"  -> 10182 hits  JOURNAL:Nature Genetics   -> 7639 hits

Quoting ``SRC`` silently returns nothing; *not* quoting a multi-word journal
silently reinterprets the tail as a free-text term. So enum-valued fields are
written bare (safe because they are whitelist-validated) and phrase-valued
fields are always quoted.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

# Free-text tokens: a double-quoted phrase, or a run of non-whitespace.
_TOKEN_RE = re.compile(r'"([^"]*)"|(\S+)')
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Lucene operators Europe PMC understands. Passed through bare; everything else
# is quoted, so a user cannot inject syntax by typing a field name.
_OPERATORS = frozenset({"AND", "OR", "NOT"})

_SOURCES = frozenset({"MED", "PMC", "PPR"})
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_PMID_RE = re.compile(r"^\d{1,9}$")

# Phrase-valued fields: always quoted.
_PHRASE_FIELDS: dict[str, str] = {
    "journal": "JOURNAL",
    "authors": "AUTH",
    "title": "TITLE",
    "abstract": "ABSTRACT",
}

VALID_FILTER_KEYS = frozenset(
    set(_PHRASE_FIELDS)
    | {
        "publication_date_range",
        "dois",
        "pmids",
        "open_access_only",
        "sources",
        "exclude_preprints",
    }
)


class LiteratureQueryError(ValueError):
    """A query or filter value could not be turned into valid Europe PMC syntax."""


def _escape_phrase(value: str) -> str:
    """Escape and quote one phrase so no metacharacter survives.

    Quoting neutralises ``: ( ) [ ] ~ ^ * ?`` and whitespace in one step, so only
    the quote character and its escape need explicit handling.
    """
    cleaned = _CONTROL_RE.sub("", str(value))
    cleaned = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{cleaned}"'


def _tokenize_free_text(query: str) -> list[str]:
    """Split free text into Europe PMC terms, honouring user-supplied quotes.

    Wrapping the whole query in quotes would turn every search into an exact
    phrase match and destroy recall, so tokens are quoted individually. A phrase
    the user quoted themselves stays one token.
    """
    tokens: list[str] = []
    for phrase, bare in _TOKEN_RE.findall(query):
        if phrase:
            tokens.append(_escape_phrase(phrase))
            continue
        if not bare:
            continue
        if bare in _OPERATORS:
            tokens.append(bare)
            continue
        # A stray unbalanced quote would otherwise become part of the search
        # term and match nothing.
        tokens.append(_escape_phrase(bare.strip('"')))
    return tokens


def _or_clause(field: str, values: Any, key: str, quoted: bool = True) -> str:
    """Build ``(FIELD:a OR FIELD:b)`` from a list of values."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)) or not values:
        raise LiteratureQueryError(f"Filter '{key}' must be a non-empty list of strings.")
    parts = [f"{field}:{_escape_phrase(v) if quoted else v}" for v in values]
    return f"({' OR '.join(parts)})" if len(parts) > 1 else parts[0]


def _date_range_clause(value: Any) -> str:
    if not isinstance(value, dict):
        raise LiteratureQueryError(
            "Filter 'publication_date_range' must be a dict with 'start' and 'end'."
        )
    bounds = []
    for edge in ("start", "end"):
        raw = value.get(edge)
        if not raw:
            raise LiteratureQueryError(
                f"Filter 'publication_date_range' is missing '{edge}'. Use YYYY-MM-DD."
            )
        try:
            datetime.strptime(str(raw), "%Y-%m-%d")
        except ValueError as e:
            raise LiteratureQueryError(
                f"Invalid date in publication_date_range: '{raw}'. Use YYYY-MM-DD."
            ) from e
        bounds.append(str(raw))
    # Brackets cannot be escaped, so nothing unvalidated may reach this string.
    return f"FIRST_PDATE:[{bounds[0]} TO {bounds[1]}]"


def _dois_clause(value: Any) -> str:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or not values:
        raise LiteratureQueryError("Filter 'dois' must be a non-empty list of DOIs.")
    for doi in values:
        if not _DOI_RE.match(str(doi).strip()):
            raise LiteratureQueryError(f"Invalid DOI in 'dois' filter: '{doi}'.")
    return _or_clause("DOI", [str(d).strip() for d in values], "dois")


def _pmids_clause(value: Any) -> str:
    """PMIDs resolve via ``EXT_ID`` scoped to ``SRC:MED``.

    Both written bare: PMIDs are digit-validated, and ``SRC:"MED"`` returns zero
    hits (verified). This is the bridge from the GWAS catalogue's PUBMEDID column.
    """
    values = [value] if isinstance(value, (str, int)) else value
    if not isinstance(values, (list, tuple)) or not values:
        raise LiteratureQueryError("Filter 'pmids' must be a non-empty list of PMIDs.")
    for pmid in values:
        if not _PMID_RE.match(str(pmid).strip()):
            raise LiteratureQueryError(f"Invalid PMID in 'pmids' filter: '{pmid}'.")
    ids = _or_clause("EXT_ID", [str(p).strip() for p in values], "pmids", quoted=False)
    return f"({ids} AND SRC:MED)"


def _sources_clause(value: Any) -> str:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or not values:
        raise LiteratureQueryError("Filter 'sources' must be a non-empty list.")
    normalised = [str(v).strip().upper() for v in values]
    for src in normalised:
        if src not in _SOURCES:
            raise LiteratureQueryError(
                f"Invalid source '{src}'. Valid sources: {', '.join(sorted(_SOURCES))}."
            )
    return _or_clause("SRC", normalised, "sources", quoted=False)


def _build_filter_clauses(filters: dict[str, Any]) -> list[str]:
    unknown = set(filters) - VALID_FILTER_KEYS
    if unknown:
        raise LiteratureQueryError(
            f"Unknown filter key(s): {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(VALID_FILTER_KEYS))}."
        )

    clauses: list[str] = []
    for key, field in _PHRASE_FIELDS.items():
        if filters.get(key):
            clauses.append(_or_clause(field, filters[key], key))
    if filters.get("publication_date_range"):
        clauses.append(_date_range_clause(filters["publication_date_range"]))
    if filters.get("dois"):
        clauses.append(_dois_clause(filters["dois"]))
    if filters.get("pmids"):
        clauses.append(_pmids_clause(filters["pmids"]))
    if filters.get("sources"):
        clauses.append(_sources_clause(filters["sources"]))
    if filters.get("open_access_only"):
        clauses.append("OPEN_ACCESS:Y")
    if filters.get("exclude_preprints"):
        clauses.append("NOT SRC:PPR")
    return clauses


def build_query(query: str, filters: Optional[dict[str, Any]] = None) -> str:
    """Compose a Europe PMC query string from free text plus structured filters.

    Args:
        query: Free-text search terms. Quoted phrases and bare AND/OR/NOT are
            honoured; everything else is escaped.
        filters: Optional structured constraints, keys per :data:`VALID_FILTER_KEYS`.

    Returns:
        A query string safe to pass as the ``query`` parameter.

    Raises:
        LiteratureQueryError: On an unknown filter key, a malformed value, or an
            empty query with no filters.
    """
    clauses: list[str] = []

    tokens = _tokenize_free_text(query or "")
    if tokens:
        joined = " ".join(tokens)
        # Parenthesised so a user's OR cannot bind across a filter boundary.
        clauses.append(f"({joined})" if len(tokens) > 1 else joined)

    if filters:
        clauses.extend(_build_filter_clauses(filters))

    if not clauses:
        raise LiteratureQueryError(
            "A non-empty 'query' or at least one filter is required."
        )
    return " AND ".join(clauses)
