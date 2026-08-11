"""Tests for the public mcp package API."""

from __future__ import annotations


def test_coder_mcp_tool_names_matches_registered_server_tools():
    """CODER_MCP_TOOL_NAMES must be the full superset of what servers register.

    Catches the "renamed a tool, forgot to update the constant" class of bugs.
    """
    from src.service.mcp import CODER_MCP_TOOL_NAMES, build_all_coder_servers, mcp_tool_names
    from src.service.mcp.file_ops_server import (
        list_files_by_thread_mcp,
        list_files_by_type_mcp,
    )
    from src.service.mcp.s3_server import list_s3_files_mcp, read_file_from_s3_mcp
    from src.service.mcp.sandbox_server import execute_code_mcp, execute_r_code_mcp

    tools_by_server = {
        "sandbox": [execute_code_mcp, execute_r_code_mcp],
        "s3": [read_file_from_s3_mcp, list_s3_files_mcp],
        "file_ops": [list_files_by_thread_mcp, list_files_by_type_mcp],
    }

    expected = [
        f"mcp__{server}__{tool.name}" for server, tools in tools_by_server.items() for tool in tools
    ]

    # Constant is the full superset (auto mode).
    assert set(CODER_MCP_TOOL_NAMES) == set(expected)
    # Default call is auto and must return the superset.
    assert set(mcp_tool_names()) == set(CODER_MCP_TOOL_NAMES)
    assert set(mcp_tool_names("auto")) == set(CODER_MCP_TOOL_NAMES)

    servers = build_all_coder_servers()
    assert set(servers.keys()) == set(tools_by_server.keys())


def test_mcp_tool_names_python_mode_excludes_execute_r_code():
    """Python-only sessions must not see the R execute tool — matches coder.py:76-79."""
    from src.service.mcp import mcp_tool_names

    names = mcp_tool_names("python")
    assert "mcp__sandbox__execute_code" in names
    assert "mcp__sandbox__execute_r_code" not in names
    # Non-language-gated tools always present
    assert "mcp__s3__read_file_from_s3" in names
    assert "mcp__s3__list_s3_files" in names
    assert "mcp__file_ops__list_files_by_thread" in names
    assert "mcp__file_ops__list_files_by_type" in names


def test_mcp_tool_names_r_mode_excludes_execute_code():
    """R-only sessions must not see the Python execute tool."""
    from src.service.mcp import mcp_tool_names

    names = mcp_tool_names("r")
    assert "mcp__sandbox__execute_r_code" in names
    assert "mcp__sandbox__execute_code" not in names
    # Non-language-gated tools always present
    assert "mcp__s3__read_file_from_s3" in names


def test_mcp_tool_names_parity_with_langchain_coder():
    """The SDK tool surface must match what coder.create_coder_agent ships to
    the LangChain backend for the same code_language — this is the A/B honesty
    invariant flagged in the Codex adversarial review.
    """
    from src.service.mcp import mcp_tool_names

    # Encode the rule from coder.py:76-79 in one place.
    expected = {
        "python": {
            "execute_code": True,
            "execute_r_code": False,
        },
        "r": {
            "execute_code": False,
            "execute_r_code": True,
        },
        "auto": {
            "execute_code": True,
            "execute_r_code": True,
        },
    }
    for lang, expect in expected.items():
        names = mcp_tool_names(lang)
        assert ("mcp__sandbox__execute_code" in names) is expect["execute_code"], lang
        assert ("mcp__sandbox__execute_r_code" in names) is expect["execute_r_code"], lang


def test_build_all_coder_servers_returns_fresh_instances():
    """Each call builds a new server dict — avoids shared-state bugs across requests."""
    from src.service.mcp import build_all_coder_servers

    a = build_all_coder_servers()
    b = build_all_coder_servers()
    assert a is not b
    # Values too — new server config objects
    assert a["sandbox"] is not b["sandbox"]


# ---------------------------------------------------------------------------
# Phase 2 Workstream B — orchestrator superset + new server registrations
# ---------------------------------------------------------------------------


def test_orchestrator_mcp_tool_names_superset_of_coder():
    """ORCHESTRATOR_MCP_TOOL_NAMES must include every coder tool.

    The orchestrator AgentDefinition pattern expects to delegate any
    coder-capable task down; narrowing the superset would break those
    handoffs in the prototype.
    """
    from src.service.mcp import CODER_MCP_TOOL_NAMES, ORCHESTRATOR_MCP_TOOL_NAMES

    assert set(CODER_MCP_TOOL_NAMES).issubset(set(ORCHESTRATOR_MCP_TOOL_NAMES))


def test_orchestrator_mcp_tool_names_matches_registered_orchestrator_servers():
    """ORCHESTRATOR_MCP_TOOL_NAMES must enumerate exactly the tools the
    registered servers expose. Catches the "renamed a tool, forgot to update
    the constant" failure mode at import time (which is also when the real
    SDK options are built in production).
    """
    from src.service.mcp import (
        ORCHESTRATOR_MCP_TOOL_NAMES,
        build_all_orchestrator_servers,
        orchestrator_mcp_tool_names,
    )
    from src.service.mcp.database_server import (
        execute_sql_query_and_save_mcp,
        execute_sql_query_mcp,
        get_database_schema_mcp,
        get_random_subsamples_mcp,
    )
    from src.service.mcp.file_ops_server import (
        list_files_by_thread_mcp,
        list_files_by_type_mcp,
    )
    from src.service.mcp.s3_server import list_s3_files_mcp, read_file_from_s3_mcp
    from src.service.mcp.sandbox_server import execute_code_mcp, execute_r_code_mcp

    tools_by_server = {
        "sandbox": [execute_code_mcp, execute_r_code_mcp],
        "s3": [read_file_from_s3_mcp, list_s3_files_mcp],
        "file_ops": [list_files_by_thread_mcp, list_files_by_type_mcp],
        "database": [
            execute_sql_query_mcp,
            execute_sql_query_and_save_mcp,
            get_database_schema_mcp,
            get_random_subsamples_mcp,
        ],
    }

    expected = {
        f"mcp__{server}__{tool.name}" for server, tools in tools_by_server.items() for tool in tools
    }
    assert set(ORCHESTRATOR_MCP_TOOL_NAMES) == expected
    assert set(orchestrator_mcp_tool_names()) == expected

    servers = build_all_orchestrator_servers()
    assert set(servers.keys()) == set(tools_by_server.keys())


def test_build_all_orchestrator_servers_returns_fresh_instances():
    from src.service.mcp import build_all_orchestrator_servers

    a = build_all_orchestrator_servers()
    b = build_all_orchestrator_servers()
    assert a is not b
    assert a["database"] is not b["database"]
    assert a["sandbox"] is not b["sandbox"]
