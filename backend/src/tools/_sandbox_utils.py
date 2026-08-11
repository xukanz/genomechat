"""Shared utilities for sandbox code execution tools."""

import json
import logging
import os
from typing import Optional

import httpx

from src.utils.context import thread_id_context

logger = logging.getLogger(__name__)


async def call_sandbox(url: str, timeout: float, payload: dict) -> dict:
    """Call a sandbox service and return the JSON response.

    Args:
        url: Base URL of the sandbox service
        timeout: Request timeout in seconds
        payload: JSON payload for the /run endpoint

    Returns:
        JSON response dict from the sandbox
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{url}/run", json=payload)
        response.raise_for_status()
        return response.json()


def build_sandbox_payload(
    source: str,
    stdin: Optional[str] = None,
    cmd_args: Optional[list[str]] = None,
    limits: Optional[dict] = None,
    s3_inputs: Optional[list[dict]] = None,
    s3_outputs: Optional[list[dict]] = None,
) -> dict:
    """Build the request payload for a sandbox /run call.

    Args:
        source: Source code to execute
        stdin: Optional standard input
        cmd_args: Optional command-line arguments
        limits: Optional resource limits
        s3_inputs: Optional S3 input file references
        s3_outputs: Optional S3 output file references

    Returns:
        Payload dict ready for JSON serialization
    """
    payload: dict = {
        "source": source,
        "stdin": stdin or "",
        "args": cmd_args or [],
    }
    if limits:
        payload["limits"] = limits
    if s3_inputs:
        payload["s3_inputs"] = s3_inputs
    if s3_outputs:
        payload["s3_outputs"] = s3_outputs
    return payload


def format_sandbox_response(result: dict) -> str:
    """Format sandbox response for the agent.

    Processes stdout, stderr, exit code, files (base64), and S3 file references.
    Tracks S3 files in MongoDB via FileStorageService.

    Args:
        result: JSON response from the sandbox /run endpoint

    Returns:
        Formatted string with execution results
    """
    output_parts: list[str] = []

    if result.get("stdout"):
        output_parts.append(f"STDOUT:\n{result['stdout']}")

    if result.get("stderr"):
        output_parts.append(f"STDERR:\n{result['stderr']}")

    exit_code = result.get("exit_code", -1)
    output_parts.append(f"Exit code: {exit_code}")

    if result.get("truncated"):
        truncated = result["truncated"]
        if truncated.get("stdout"):
            output_parts.append("(Note: stdout was truncated)")
        if truncated.get("stderr"):
            output_parts.append("(Note: stderr was truncated)")

    # Collect S3 file basenames for dedup against local files
    s3_file_keys: set[str] = set()
    if result.get("s3_files"):
        s3_file_keys = {os.path.basename(f.get("key", "")) for f in result["s3_files"]}

    # Include local files (images/CSV) as markdown, skipping S3 duplicates
    if result.get("files"):
        for filename, base64_content in result["files"].items():
            if os.path.basename(filename) in s3_file_keys:
                continue
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif")):
                mime_type = (
                    "image/png"
                    if filename.lower().endswith(".png")
                    else "image/jpeg"
                    if filename.lower().endswith((".jpg", ".jpeg"))
                    else "image/gif"
                )
                output_parts.append(f"\n![{filename}](data:{mime_type};base64,{base64_content})")
            elif filename.lower().endswith(".svg"):
                output_parts.append(f"\n![{filename}](data:image/svg+xml;base64,{base64_content})")
            elif filename.lower().endswith(".csv"):
                output_parts.append(f"\n**File generated:** `{filename}` (CSV file)")

    # Track S3 files in MongoDB and emit markers for streaming
    if result.get("s3_files"):
        s3_files = result["s3_files"]
        if s3_files:
            output_parts.append("\n**S3 Files Created:**")
            _track_s3_files(s3_files, output_parts)

    if not output_parts:
        return "Code executed successfully with no output."

    return "\n\n".join(output_parts)


def _track_s3_files(s3_files: list[dict], output_parts: list[str]) -> None:
    """Track S3 files in MongoDB and append markers to output.

    Args:
        s3_files: List of S3 file reference dicts from sandbox response
        output_parts: Mutable list to append output strings to
    """
    try:
        from src.service.storage.file_storage_service import FileStorageService
        from src.models.file_storage import FileRecordCreate, FileType

        file_storage_service = FileStorageService()

        for s3_file in s3_files:
            bucket = s3_file.get("bucket", "")
            key = s3_file.get("key", "")
            output_parts.append(f"- s3://{bucket}/{key}")

            # S3_FILE marker for streaming file events
            s3_file_marker = json.dumps({"bucket": bucket, "key": key})
            output_parts.append(f"S3_FILE[{s3_file_marker}]")

            # Infer user_id from S3 key pattern: users/{user_id}/...
            user_id = None
            if key and key.startswith("users/"):
                parts = key.split("/")
                if len(parts) >= 2:
                    user_id = parts[1] if parts[1] != "anonymous" else None

            # Infer file type from key
            file_type = FileType.CODER_OUTPUT
            if "query_results" in key or "query" in key.lower():
                file_type = FileType.QUERY_RESULT
            elif (
                "analysis" in key.lower()
                or "report" in key.lower()
                or "visualization" in key.lower()
            ):
                file_type = FileType.ANALYSIS

            # Infer content type from extension
            content_type = "txt"
            if key:
                if key.endswith(".csv"):
                    content_type = "csv"
                elif key.endswith(".json"):
                    content_type = "json"
                elif key.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
                    content_type = key.split(".")[-1]
                elif key.endswith(".py"):
                    content_type = "py"
                elif key.endswith(".R"):
                    content_type = "r"
                elif "." in key:
                    content_type = key.split(".")[-1]

            # Get file size from S3
            try:
                s3_client = file_storage_service.s3_client
                head_response = s3_client.head_object(Bucket=bucket, Key=key)
                size_bytes = head_response.get("ContentLength", 0)
            except Exception:
                size_bytes = 0

            # Track in MongoDB
            thread_id = thread_id_context.get()
            file_data = FileRecordCreate(
                user_id=user_id,
                thread_id=thread_id,
                file_type=file_type,
                s3_bucket=bucket,
                s3_key=key,
                content_type=content_type,
                size_bytes=size_bytes,
                metadata={
                    "source": "sandbox_execution",
                    "s3_outputs": True,
                },
            )
            file_storage_service.track_existing_file(file_data)
            logger.info(f"Tracked S3 file in MongoDB: s3://{bucket}/{key}")
    except Exception as e:
        logger.warning(f"Failed to track S3 files in MongoDB: {e}")
