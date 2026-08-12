"""JATS XML -> plain text, using only the standard library.

Europe PMC serves open-access full text as JATS XML (~150 KB for a typical
paper). Only the narrative matters for literature review, so tables, figures,
formulae and cross-reference markers are dropped.

:func:`jats_to_text` never raises — any parse failure returns ``""`` and the
caller degrades to abstract-only. ``xml.etree`` is not hardened against hostile
input, so the size gate below is what keeps a malformed document from becoming a
memory problem; Europe PMC is a fixed, trusted origin.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Refuse to parse anything larger than this. The biggest real papers are a few
# hundred KB; 5 MB means something is wrong.
MAX_XML_BYTES = 5_000_000
# Hard cap on extracted narrative. Display truncation happens on top of this.
MAX_FULLTEXT_CHARS = 200_000

_MATHML_NS = "http://www.w3.org/1998/Math/MathML"
_INLINE_WS_RE = re.compile(r"\s+")

# Subtrees removed wholesale. Their content is either non-narrative (figures,
# tables, formulae) or pure markup noise (``xref`` renders as a bare "12").
_DROP_TAGS = frozenset(
    {
        "table-wrap",
        "table",
        "fig",
        "graphic",
        "inline-graphic",
        "media",
        "supplementary-material",
        "disp-formula",
        "inline-formula",
        "tex-math",
        "label",
        "xref",
        "ext-link",
        "ref-list",
        "back",
    }
)

# Emit paragraph breaks around these.
_BLOCK_TAGS = frozenset({"p", "sec", "abstract", "list-item", "disp-quote"})
_HEADING_TAGS = frozenset({"title"})


def _localname(tag: Union[str, object]) -> str:
    """Strip a ``{namespace}`` prefix; non-element nodes yield ``""``."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[1] if tag.startswith("{") else tag


def _find_by_localname(root: ET.Element, name: str) -> Optional[ET.Element]:
    """Find the first element with this local name, ignoring any namespace.

    ``root.find(".//body")`` misses ``{ns}body`` when the document declares a
    default namespace, which would silently yield no full text at all.
    """
    if _localname(root.tag) == name:
        return root
    for element in root.iter():
        if _localname(element.tag) == name:
            return element
    return None


def _inline(text: str) -> str:
    """Collapse insignificant whitespace inside a text node.

    Newlines within a ``<p>`` are source formatting, not structure — only the
    explicit block markers emitted by :func:`_emit` carry paragraph breaks.
    """
    return _INLINE_WS_RE.sub(" ", text)


def _is_dropped(el: ET.Element) -> bool:
    tag = el.tag
    if isinstance(tag, str) and tag.startswith(f"{{{_MATHML_NS}}}"):
        return True
    return _localname(tag) in _DROP_TAGS


def _emit(el: ET.Element, out: list[str]) -> None:
    """Recursively collect narrative text from ``el`` into ``out``.

    Deliberately not ``itertext()``: that cannot skip subtrees, so figure and
    table content would be inlined into the prose.
    """
    tag = _localname(el.tag)

    if tag in _HEADING_TAGS:
        heading = " ".join("".join(el.itertext()).split())
        if heading:
            out.append(f"\n\n## {heading}\n\n")
        return

    if tag in _BLOCK_TAGS:
        out.append("\n\n")
    if el.text:
        out.append(_inline(el.text))

    for child in el:
        if not _is_dropped(child):
            _emit(child, out)
        # ``tail`` is text belonging to the PARENT's flow, not the child's, so it
        # must be emitted even when the child itself was dropped. Skipping it
        # swallows the rest of the sentence after every <xref>.
        if child.tail:
            out.append(_inline(child.tail))

    if tag in _BLOCK_TAGS:
        out.append("\n\n")


def _normalise(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def jats_to_text(xml_text: str) -> str:
    """Extract readable narrative from a JATS full-text document.

    Args:
        xml_text: Raw JATS XML as returned by ``/{PMCID}/fullTextXML``.

    Returns:
        Plain text with ``## `` section headings, or ``""`` if the document is
        empty, oversized, or unparseable.
    """
    if not xml_text or not xml_text.strip():
        return ""
    if len(xml_text) > MAX_XML_BYTES:
        logger.warning("Refusing to parse %d-byte JATS document", len(xml_text))
        return ""

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("Could not parse JATS XML: %s", e)
        return ""

    # Prefer the article body; fall back to the abstract for records that carry
    # metadata-only XML.
    # Explicit None checks: an empty <body/> is falsy as an Element, so `or`
    # would silently fall through to the abstract.
    node = _find_by_localname(root, "body")
    if node is None:
        node = _find_by_localname(root, "abstract")
    if node is None:
        return ""

    out: list[str] = []
    try:
        _emit(node, out)
    except RecursionError:
        logger.warning("JATS document nested too deeply; returning partial text")

    return _normalise("".join(out))[:MAX_FULLTEXT_CHARS]
