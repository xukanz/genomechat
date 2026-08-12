"""S3 operations tools for backend agent."""

import logging
from typing import Optional

from langchain_core.tools import tool
from botocore.exceptions import ClientError

from src.service.observability import trace_tool
from src.service.s3 import get_s3_client
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Truncation limits to prevent context window overflow
MAX_CSV_PREVIEW_ROWS = 50  # Number of rows to show for CSV files
MAX_CONTENT_CHARS = 50000  # ~12.5K tokens max for non-CSV files


def _truncate_csv_content(content: str, key: str) -> str:
    """Truncate CSV content to show only head rows with metadata.

    Returns a preview of the CSV with row/column counts for context.
    """
    lines = content.split("\n")
    # Filter out empty lines for accurate count
    non_empty_lines = [line for line in lines if line.strip()]
    total_rows = len(non_empty_lines) - 1  # Subtract header row

    if total_rows <= MAX_CSV_PREVIEW_ROWS:
        # Small file, return as-is
        return content

    # Get header and first N data rows
    header = lines[0] if lines else ""
    data_lines = [line for line in lines[1:] if line.strip()][:MAX_CSV_PREVIEW_ROWS]

    # Count columns from header
    num_columns = len(header.split(",")) if header else 0

    # Build truncated output with metadata
    preview_content = "\n".join([header] + data_lines)

    truncation_notice = (
        f"\n\n--- TRUNCATED ---\n"
        f"Showing first {MAX_CSV_PREVIEW_ROWS} of {total_rows} rows ({num_columns} columns).\n"
        f"For full data processing, use execute_code tool with s3_inputs parameter:\n"
        f"  s3_inputs=[{{'bucket': 'BUCKET', 'key': '{key}', 'local_path': 'data.csv'}}]\n"
        f"This downloads the file directly to sandbox for efficient processing."
    )

    return preview_content + truncation_notice


def _truncate_content(content: str, key: str) -> str:
    """Truncate non-CSV content to character limit."""
    if len(content) <= MAX_CONTENT_CHARS:
        return content

    truncated = content[:MAX_CONTENT_CHARS]

    truncation_notice = (
        f"\n\n--- TRUNCATED ---\n"
        f"Showing first {MAX_CONTENT_CHARS:,} of {len(content):,} characters.\n"
        f"For full file processing, use execute_code tool with s3_inputs parameter:\n"
        f"  s3_inputs=[{{'bucket': 'BUCKET', 'key': '{key}', 'local_path': 'file.txt'}}]"
    )

    return truncated + truncation_notice


@trace_tool
@tool
async def read_file_from_s3(bucket: Optional[str] = None, key: Optional[str] = None) -> str:
    """Read a file from S3 and return its content (truncated for large files).

    Use this to get a PREVIEW of file contents for understanding data structure.
    Returns first 50 rows for CSV files, or first 50K characters for other files.

    **For processing large files**: Use execute_code tool with s3_inputs parameter
    instead - this downloads files directly to sandbox without context overhead.

    Args:
        bucket: S3 bucket name (optional, uses default if not provided)
        key: S3 object key (file path)

    Returns:
        File content (truncated if large) with metadata, or error message
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = settings.aws_default_bucket
        if bucket is None:
            return "Error: Bucket name must be provided or AWS_DEFAULT_BUCKET must be set"

    # Validate bucket if whitelist is configured
    if not settings.validate_s3_bucket(bucket):
        return (
            f"Error: Bucket '{bucket}' is not in the allowed list. "
            f"Allowed buckets: {', '.join(settings.allowed_s3_buckets_list)}"
        )

    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=bucket, Key=key)
        content = obj["Body"].read().decode("utf-8")
        logger.info(f"Successfully read file from s3://{bucket}/{key}")

        # Apply smart truncation based on file type
        if key and key.lower().endswith(".csv"):
            content = _truncate_csv_content(content, key)
        else:
            content = _truncate_content(content, key)

        return content
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = f"Error reading from S3: {error_code}"
        logger.error(f"{error_msg} - s3://{bucket}/{key}")
        return f"Error: {error_msg}"
    except Exception as e:
        error_msg = f"Unexpected error reading from S3: {str(e)}"
        logger.error(f"{error_msg} - s3://{bucket}/{key}")
        return f"Error: {error_msg}"


@trace_tool
@tool
async def list_s3_files(bucket: Optional[str] = None, prefix: str = "") -> str:
    """List files in an S3 bucket with optional prefix filter.

    Use this to discover available files in an S3 bucket before processing them.

    Args:
        bucket: S3 bucket name (optional, uses default if not provided)
        prefix: Optional prefix to filter files (e.g., 'data/raw/')

    Returns:
        Comma-separated list of file keys, or error message if listing fails
    """
    # Use default bucket if not provided
    if bucket is None:
        bucket = settings.aws_default_bucket
        if bucket is None:
            return "Error: Bucket name must be provided or AWS_DEFAULT_BUCKET must be set"

    # Validate bucket if whitelist is configured
    if not settings.validate_s3_bucket(bucket):
        return (
            f"Error: Bucket '{bucket}' is not in the allowed list. "
            f"Allowed buckets: {', '.join(settings.allowed_s3_buckets_list)}"
        )

    try:
        s3 = get_s3_client()
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        keys = [obj["Key"] for obj in response.get("Contents", [])]
        if keys:
            result = ", ".join(keys)
            logger.info(f"Listed {len(keys)} files from s3://{bucket}/{prefix}")
            return result
        else:
            return f"No files found in s3://{bucket}/{prefix}"
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        error_msg = f"Error listing S3 files: {error_code}"
        logger.error(f"{error_msg} - s3://{bucket}/{prefix}")
        return f"Error: {error_msg}"
    except Exception as e:
        error_msg = f"Unexpected error listing S3 files: {str(e)}"
        logger.error(f"{error_msg} - s3://{bucket}/{prefix}")
        return f"Error: {error_msg}"
