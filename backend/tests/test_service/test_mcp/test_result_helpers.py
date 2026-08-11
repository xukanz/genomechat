"""Tests for looks_like_tool_error prefix matcher."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "text",
    [
        "Error: bucket not in allowed list",
        "Error: Invalid file_type 'foo'. Valid types: ...",
        "Error reading from S3: NoSuchKey",
        "Error listing S3 files: AccessDenied",
        "Error writing to S3: ...",
    ],
)
def test_known_error_prefixes_match(text):
    from src.service.mcp._result_helpers import looks_like_tool_error

    assert looks_like_tool_error(text) is True


@pytest.mark.parametrize(
    "text",
    [
        # Legitimate file content that starts with the bare word "Error"
        "Error occurred at line 42 of the script",
        "Error-handling notes for the operator",
        "Error_2024 archive summary",
        # Content starts with something else entirely
        "[INFO] normal log line",
        "",
        "Normal text",
        # Colon present but different word — must not match
        "Warning: something",
        "Info: ok",
    ],
)
def test_non_tool_error_strings_do_not_match(text):
    from src.service.mcp._result_helpers import looks_like_tool_error

    assert looks_like_tool_error(text) is False
