"""LangChain tool for executing Python code in a sandboxed environment."""

import logging
from typing import Optional

from langchain_core.tools import tool

from src.config.settings import settings
from src.service.observability import trace_tool
from src.tools._sandbox_utils import build_sandbox_payload, call_sandbox, format_sandbox_response

logger = logging.getLogger(__name__)


@trace_tool
@tool
async def execute_code(
    source: str,
    stdin: Optional[str] = None,
    cmd_args: Optional[list[str]] = None,
    limits: Optional[dict] = None,
    s3_inputs: Optional[list[dict]] = None,
    s3_outputs: Optional[list[dict]] = None,
) -> str:
    """Execute Python code in a sandboxed environment with S3 access.

    Use this tool when the user asks you to run, execute, or test Python code.
    The code will be executed safely in an isolated sandbox with resource limits.

    Args:
        source: Python source code to execute (required)
        stdin: Optional standard input for the program
        cmd_args: Optional command-line arguments as a list of strings
        limits: Optional execution limits dict with keys:
            - wall_ms: Maximum wall-clock time in milliseconds (1-10000)
            - cpu_s: Maximum CPU time in seconds (1-10)
            - mem_mb: Maximum memory in MB (32-512)
        s3_inputs: Optional list of S3 file references available to the code.
                   Format: [{"bucket": "bucket-name", "key": "path/to/file.csv"}]
        s3_outputs: Optional list of S3 files the code should create.
                    Format: [{"bucket": "bucket-name", "key": "path/to/output.csv"}]

    Returns:
        Formatted string with execution results including stdout, stderr, exit code,
        generated images, and S3 file references
    """
    try:
        payload = build_sandbox_payload(source, stdin, cmd_args, limits, s3_inputs, s3_outputs)
        result = await call_sandbox(settings.sandbox_url, settings.sandbox_timeout, payload)
        return format_sandbox_response(result)
    except Exception as e:
        return _handle_sandbox_error(e)


def _handle_sandbox_error(e: Exception) -> str:
    """Format sandbox errors for the agent."""
    import httpx

    if isinstance(e, httpx.TimeoutException):
        logger.error("Sandbox request timed out")
        return "Error: Code execution timed out. The code may be taking too long to run."
    elif isinstance(e, httpx.HTTPStatusError):
        logger.error(f"Sandbox HTTP error: {e.response.status_code}")
        return f"Error: Sandbox service returned error {e.response.status_code}. Please try again."
    else:
        logger.error(f"Unexpected error executing code: {e}", exc_info=True)
        return f"Error executing code: {str(e)}"
