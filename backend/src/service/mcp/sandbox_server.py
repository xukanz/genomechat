"""In-process MCP server exposing Python + R sandbox execution to the SDK.

Wraps the existing ``_sandbox_utils`` helpers. **Never** duplicates business
logic — the real sandbox call, payload builder, response formatter, and S3
file tracking all live in ``src.tools._sandbox_utils`` and are reused
verbatim.

Because the MCP server runs in the same Python process as the backend, the
``thread_id_context`` / ``database_id_context``
ContextVars set by the FastAPI request task propagate naturally into the
handler. The ``_sandbox_utils._track_s3_files`` call chain that reads
``thread_id_context`` inside ``format_sandbox_response`` continues to work
with no additional plumbing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from claude_agent_sdk import create_sdk_mcp_server, tool

from src.config.settings import settings
from src.service.mcp._span_helpers import traced_mcp_tool
from src.tools._sandbox_utils import (
    build_sandbox_payload,
    call_sandbox,
    format_sandbox_response,
)

logger = logging.getLogger(__name__)


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def _opt_list(v: Any) -> list | None:
    """Return v if it's a non-empty list, else None. SDK schemas encode ``list`` as
    JSON array, and Sonnet often omits them — defaulting to ``[]`` is fine but we
    convert to ``None`` so ``build_sandbox_payload`` skips the field entirely."""
    return v if isinstance(v, list) and v else None


def _opt_dict(v: Any) -> dict | None:
    return v if isinstance(v, dict) and v else None


def _opt_str(v: Any) -> str | None:
    return v if isinstance(v, str) and v else None


@tool(
    "execute_code",
    (
        "Execute Python code in a sandboxed environment with S3 access. Use this tool "
        "when the user asks you to run, execute, or test Python code. The code will be "
        "executed safely in an isolated sandbox with resource limits."
    ),
    {
        "source": str,
        "stdin": str,
        "cmd_args": list,
        "limits": dict,
        "s3_inputs": list,
        "s3_outputs": list,
    },
)
@traced_mcp_tool("execute_code")
async def execute_code_mcp(args: dict[str, Any]) -> dict[str, Any]:
    """Delegate to ``_sandbox_utils`` — same semantics as ``tools.execute_code``."""
    source = args.get("source") or ""
    if not source:
        return _err("execute_code requires a non-empty 'source' argument.")

    try:
        payload = build_sandbox_payload(
            source=source,
            stdin=_opt_str(args.get("stdin")),
            cmd_args=_opt_list(args.get("cmd_args")),
            limits=_opt_dict(args.get("limits")),
            s3_inputs=_opt_list(args.get("s3_inputs")),
            s3_outputs=_opt_list(args.get("s3_outputs")),
        )
        result = await call_sandbox(settings.sandbox_url, settings.sandbox_timeout, payload)
        return _ok(format_sandbox_response(result))
    except httpx.TimeoutException:
        logger.error("Sandbox request timed out (MCP)")
        return _err("Error: Code execution timed out. The code may be taking too long to run.")
    except httpx.HTTPStatusError as e:
        logger.error("Sandbox HTTP error %s (MCP)", e.response.status_code)
        return _err(
            f"Error: Sandbox service returned error {e.response.status_code}. Please try again."
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected error executing code (MCP)")
        return _err(f"Error executing code: {e}")


@tool(
    "execute_r_code",
    (
        "Execute R code in a sandboxed environment with S3 access. Use this tool for "
        "R statistical analysis, ggplot2 visualizations, survival analysis, and "
        "genomics plots (Manhattan / Q-Q via qqman)."
    ),
    {
        "source": str,
        "limits": dict,
        "s3_inputs": list,
        "s3_outputs": list,
    },
)
@traced_mcp_tool("execute_r_code")
async def execute_r_code_mcp(args: dict[str, Any]) -> dict[str, Any]:
    """Delegate to ``_sandbox_utils`` — same semantics as ``tools.execute_r_code``."""
    source = args.get("source") or ""
    if not source:
        return _err("execute_r_code requires a non-empty 'source' argument.")

    try:
        payload = build_sandbox_payload(
            source=source,
            limits=_opt_dict(args.get("limits")),
            s3_inputs=_opt_list(args.get("s3_inputs")),
            s3_outputs=_opt_list(args.get("s3_outputs")),
        )
        result = await call_sandbox(settings.r_sandbox_url, settings.r_sandbox_timeout, payload)
        return _ok(format_sandbox_response(result))
    except httpx.TimeoutException:
        logger.error("R sandbox request timed out (MCP)")
        return _err("Error: R code execution timed out. The code may be taking too long to run.")
    except httpx.HTTPStatusError as e:
        logger.error("R sandbox HTTP error %s (MCP)", e.response.status_code)
        return _err(
            f"Error: R sandbox service returned error {e.response.status_code}. Please try again."
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected error executing R code (MCP)")
        return _err(f"Error executing R code: {e}")


def build_sandbox_server() -> Any:
    """Return the MCP server config object exposing both sandbox tools."""
    return create_sdk_mcp_server(
        name="sandbox",
        version="1.0.0",
        tools=[execute_code_mcp, execute_r_code_mcp],
    )


__all__ = ["build_sandbox_server", "execute_code_mcp", "execute_r_code_mcp"]
