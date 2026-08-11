"""PHI / secret redaction for memory ingestion.

Runs before any Haiku call and before any write to `research_memories`. Errs
on the side of over-redaction — a false positive costs a prompt token, a false
negative is a potential compliance incident. Patterns are tuned for the
biomedical research domain (MRN-like strings, email addresses) plus standard
secret shapes (AWS keys, JWTs, private keys).

Callers receive `(redacted_text, hits)`. The `hits` list is written to
`memory_redaction_log` so an auditor can confirm the extractor never saw the
raw text. We NEVER silently drop content — if a pattern matches, the audit
row carries the `pattern_name` and offset so a reviewer can reconstruct what
was caught without ever storing the raw match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionHit:
    pattern_name: str
    span: tuple[int, int]


_PATTERNS: dict[str, re.Pattern[str]] = {
    # —— Secrets ——
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    "private_key": re.compile(
        r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----"
    ),
    # —— PII / PHI ——
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "us_phone": re.compile(r"\b(?:\+?1[ -.]?)?\(?\d{3}\)?[ -.]?\d{3}[ -.]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # —— Clinical identifiers (biomedical domain) ——
    "mrn_like": re.compile(r"\bMRN[:#\s]*\d{6,12}\b", re.IGNORECASE),
    "patient_id_like": re.compile(r"\bPATIENT[_\- ]?ID[:#\s]*\d{6,}\b", re.IGNORECASE),
}


def redact(text: str) -> tuple[str, list[RedactionHit]]:
    """Return (redacted_text, hits).

    All matches are replaced with `[REDACTED:<pattern_name>]`. The `hits` list
    records each match's span in the ORIGINAL text (before replacement), which
    is the audit-trail invariant: `text[span[0]:span[1]]` is recoverable only
    by re-running the pattern on the caller's input (which was live only during
    the extraction turn and is never persisted).
    """
    if not text:
        return text, []

    hits: list[RedactionHit] = []
    for name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            hits.append(RedactionHit(pattern_name=name, span=match.span()))

    if not hits:
        return text, hits

    redacted = text
    for name, pattern in _PATTERNS.items():
        redacted = pattern.sub(f"[REDACTED:{name}]", redacted)

    return redacted, hits
