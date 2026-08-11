"""LangChain tool for executing R code in a sandboxed environment."""

import logging
from typing import Optional

import httpx
from langchain_core.tools import tool

from src.config.settings import settings
from src.service.observability import trace_tool
from src.tools._sandbox_utils import build_sandbox_payload, call_sandbox, format_sandbox_response

logger = logging.getLogger(__name__)


@trace_tool
@tool
async def execute_r_code(
    source: str,
    limits: Optional[dict] = None,
    s3_inputs: Optional[list[dict]] = None,
    s3_outputs: Optional[list[dict]] = None,
) -> str:
    """Execute R code in a sandboxed environment with S3 access.

    Use this tool for R statistical analysis, ggplot2 visualizations,
    survival analysis, and genomics plots (Manhattan / Q-Q via qqman).

    Args:
        source: R source code to execute (required)
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
        payload = build_sandbox_payload(
            source, limits=limits, s3_inputs=s3_inputs, s3_outputs=s3_outputs
        )
        result = await call_sandbox(settings.r_sandbox_url, settings.r_sandbox_timeout, payload)
        return format_sandbox_response(result)
    except httpx.TimeoutException:
        logger.error("R sandbox request timed out")
        return "Error: R code execution timed out. The code may be taking too long to run."
    except httpx.HTTPStatusError as e:
        logger.error(f"R sandbox HTTP error: {e.response.status_code}")
        return (
            f"Error: R sandbox service returned error {e.response.status_code}. Please try again."
        )
    except Exception as e:
        logger.error(f"Unexpected error executing R code: {e}", exc_info=True)
        return f"Error executing R code: {str(e)}"
