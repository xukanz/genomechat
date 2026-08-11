"""In-process MCP servers wrapping existing coder tools for SDK consumption.

Public API:
    build_sandbox_server()         — Python + R sandbox execution
    build_s3_server()              — S3 read / list
    build_file_ops_server()        — conversation-scoped file tracking
    build_database_server()        — SQL query execution + schema (Phase 2, orchestrator)
    build_all_coder_servers()      — dict wired to ``ClaudeAgentOptions.mcp_servers`` for coder
    build_all_orchestrator_servers() — dict for the orchestrator SDK prototype (Phase 2)
    mcp_tool_names(code_language)  — ``allowed_tools`` list filtered by language (coder)
    orchestrator_mcp_tool_names()  — full orchestrator allowed_tools list (Phase 2)
    CODER_MCP_TOOL_NAMES           — frozen tuple of ALL coder MCP tool names
    ORCHESTRATOR_MCP_TOOL_NAMES    — frozen tuple of ALL orchestrator MCP tool names (Phase 2)
"""

from __future__ import annotations

from typing import Any

from src.config.code_language import CodeLanguageType
from src.service.mcp.database_server import build_database_server
from src.service.mcp.file_ops_server import build_file_ops_server
from src.service.mcp.s3_server import build_s3_server
from src.service.mcp.sandbox_server import build_sandbox_server


# Canonical superset of MCP tool names. Every entry must match a
# ``@tool("<name>", ...)`` registration in one of the three server modules.
# Tests enforce that ``mcp_tool_names("auto")`` equals this tuple.
CODER_MCP_TOOL_NAMES: tuple[str, ...] = (
    "mcp__sandbox__execute_code",
    "mcp__sandbox__execute_r_code",
    "mcp__s3__read_file_from_s3",
    "mcp__s3__list_s3_files",
    "mcp__file_ops__list_files_by_thread",
    "mcp__file_ops__list_files_by_type",
)

# Tools that are always exposed regardless of ``code_language`` — S3 read/list
# and file discovery. Both language-gated tools live on the sandbox server.
_ALWAYS_EXPOSED_TOOLS: tuple[str, ...] = (
    "mcp__s3__read_file_from_s3",
    "mcp__s3__list_s3_files",
    "mcp__file_ops__list_files_by_thread",
    "mcp__file_ops__list_files_by_type",
)


def mcp_tool_names(code_language: CodeLanguageType = "auto") -> list[str]:
    """Return the list of MCP tool names the coder SDK path exposes.

    Mirrors ``coder.create_coder_agent``'s tool-filter rule (``coder.py:76-79``):
    Python-only and R-only sessions see only the matching execute_* tool.
    ``auto`` exposes both. Non-execute tools (S3, file_ops) are always exposed.

    Pass the result directly to ``ClaudeAgentOptions(allowed_tools=...)``.

    Args:
        code_language: ``"python"`` | ``"r"`` | ``"auto"``. Defaults to
            ``"auto"`` for backward compatibility with callers that haven't
            been updated yet.
    """
    names = list(_ALWAYS_EXPOSED_TOOLS)
    if code_language in ("python", "auto"):
        names.append("mcp__sandbox__execute_code")
    if code_language in ("r", "auto"):
        names.append("mcp__sandbox__execute_r_code")
    return names


def build_all_coder_servers() -> dict[str, Any]:
    """Return the ``mcp_servers`` dict for ``ClaudeAgentOptions``.

    Always registers all three servers — exposure to the LLM is controlled
    entirely by ``allowed_tools`` (see ``mcp_tool_names``). The SDK's
    ``allowed_tools`` is authoritative: tools on a registered server that are
    not in the allowlist are invisible in the model's context.
    """
    return {
        "sandbox": build_sandbox_server(),
        "s3": build_s3_server(),
        "file_ops": build_file_ops_server(),
    }


# ---------------------------------------------------------------------------
# Phase 2 — orchestrator SDK prototype (Workstream B, branch-only)
# ---------------------------------------------------------------------------

# Canonical superset for the orchestrator path. Inherits every coder tool so
# the orchestrator can hand work off to the coder worker via AgentDefinition
# without a re-registration step, plus the orchestrator-only database
# tools. Tests enforce this tuple matches what
# ``build_all_orchestrator_servers()`` registers.
ORCHESTRATOR_MCP_TOOL_NAMES: tuple[str, ...] = (
    # coder-path tools (sandbox + s3 + file_ops)
    *CODER_MCP_TOOL_NAMES,
    # database (orchestrator-only)
    "mcp__database__execute_sql_query",
    "mcp__database__execute_sql_query_and_save",
    "mcp__database__get_database_schema",
    "mcp__database__get_random_subsamples",
)


def orchestrator_mcp_tool_names() -> list[str]:
    """Return the full ``allowed_tools`` list for the orchestrator SDK path.

    Unlike ``mcp_tool_names()`` there's no ``code_language`` filter here —
    the orchestrator must see every tool across every worker type so it can
    plan holistically. Language-level filtering still applies at the
    coder-worker ``AgentDefinition`` level inside the SDK query.
    """
    return list(ORCHESTRATOR_MCP_TOOL_NAMES)


def build_all_orchestrator_servers() -> dict[str, Any]:
    """Return the ``mcp_servers`` dict for the orchestrator SDK prototype.

    Registers the coder servers (inherited) + the Phase 2 orchestrator-only
    database server. The orchestrator LLM sees everything the coder sees plus
    SQL tools; per-worker filtering inside
    ``orchestrator_sdk.py`` (via ``AgentDefinition.allowed_tools``) is the
    second-level guard so the coder sub-agent doesn't accidentally call
    ``execute_sql_query``.
    """
    return {
        **build_all_coder_servers(),
        "database": build_database_server(),
    }


__all__ = [
    "CODER_MCP_TOOL_NAMES",
    "ORCHESTRATOR_MCP_TOOL_NAMES",
    "build_all_coder_servers",
    "build_all_orchestrator_servers",
    "build_database_server",
    "build_file_ops_server",
    "build_s3_server",
    "build_sandbox_server",
    "mcp_tool_names",
    "orchestrator_mcp_tool_names",
]
