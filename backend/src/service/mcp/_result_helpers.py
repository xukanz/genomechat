"""Shared result-shape helpers for MCP tool wrappers.

The wrapped LangChain tools return plain strings — on success the raw content,
on failure an ``"Error: ..."`` or ``"Error reading ..."`` style message. The
MCP layer needs to translate that into the structured ``{content, is_error}``
shape the SDK expects, WITHOUT misclassifying a legitimate file whose
content happens to start with the bare word ``"Error"``.

The underlying tools use a narrow set of error prefixes (see the grep in
``tools/s3_operations.py`` and ``tools/file_operations.py``). Match those
exactly — not the bare word — to keep legitimate file contents like
``"Error occurred at line 42 ..."`` flowing through as success.

Codex adversarial review (2026-05-07) flagged the bare-prefix match; this
module is the concrete fix.
"""

from __future__ import annotations


# Exact prefixes produced by the underlying LangChain tool error paths:
#   tools/s3_operations.py: "Error: ...", "Error reading ...", "Error listing ..."
#   tools/file_operations.py: "Error: Invalid file_type ...", "Error listing files: ..."
# Stays explicit so a future tool change that adds a new error grammar does
# NOT silently re-broaden the prefix match.
_TOOL_ERROR_PREFIXES: tuple[str, ...] = (
    "Error: ",
    "Error reading ",
    "Error listing ",
    "Error writing ",
)


def looks_like_tool_error(text: str) -> bool:
    """Return True iff ``text`` matches a known underlying-tool error string."""
    return any(text.startswith(p) for p in _TOOL_ERROR_PREFIXES)


__all__ = ["looks_like_tool_error"]
