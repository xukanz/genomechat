"""File query tools for agents to discover and access created files."""

import logging
from typing import Optional

from langchain_core.tools import tool

from src.service.observability import trace_tool
from src.service.storage.file_storage_service import FileStorageService
from src.models.file_storage import FileType
from src.utils.context import thread_id_context

logger = logging.getLogger(__name__)


@trace_tool
@tool
async def list_files_by_thread(
    thread_id: Optional[str] = None,
    file_type: Optional[str] = None,
    limit: int = 20,
) -> str:
    """List files created in the current conversation thread with full metadata.

    Use this to find files that were created earlier in this conversation,
    such as query results or visualizations that you can reference or reuse.
    Includes file descriptions and all metadata.

    The thread_id is automatically extracted from the conversation context,
    so you don't need to provide it. If you do provide it, it will override
    the context value.

    Args:
        thread_id: Thread ID (format: user_id:conversation_id). Optional - if not provided,
                   will use thread_id from conversation context. Only provide this if you
                   want to search a different thread.
        file_type: Optional filter by file type: "query_result", "analysis", "coder_output"
        limit: Maximum number of files to return (default: 20)

    Returns:
        Formatted string listing files with file_id, description, S3 path, and all metadata
    """
    try:
        file_storage_service = FileStorageService()

        # Convert string file_type to enum if provided
        file_type_enum = None
        if file_type:
            try:
                file_type_enum = FileType(file_type)
            except ValueError:
                return f"Error: Invalid file_type '{file_type}'. Valid types: query_result, analysis, coder_output, other"

        # Get thread_id from parameter or context variable
        context_thread_id = thread_id_context.get()
        logger.debug(
            f"list_files_by_thread: thread_id param={thread_id}, "
            f"context_thread_id={context_thread_id}"
        )

        search_thread_id = thread_id or context_thread_id or "anonymous:unknown"
        logger.info(
            f"list_files_by_thread: Using thread_id='{search_thread_id}' "
            f"(source: {'parameter' if thread_id else 'context' if context_thread_id else 'default'})"
        )

        # Extract user_id from thread_id if format is user_id:conversation_id
        user_id = None
        if search_thread_id and ":" in search_thread_id:
            user_id_part = search_thread_id.split(":")[0]
            user_id = user_id_part if user_id_part != "anonymous" else None
            logger.debug(
                f"list_files_by_thread: Extracted user_id='{user_id}' "
                f"from thread_id='{search_thread_id}'"
            )
        else:
            logger.debug(
                f"list_files_by_thread: No user_id extracted from thread_id='{search_thread_id}' "
                f"(no ':' separator found)"
            )

        logger.info(
            f"list_files_by_thread: Querying files with thread_id='{search_thread_id}', "
            f"user_id={user_id}, file_type={file_type_enum}, limit={limit}"
        )

        files = file_storage_service.list_by_thread(
            thread_id=search_thread_id,
            user_id=user_id,
            file_type=file_type_enum,
            limit=limit,
        )

        logger.info(
            f"list_files_by_thread: Found {len(files)} file(s) for thread_id='{search_thread_id}'"
        )

        if not files:
            return f"No files found for thread '{search_thread_id}'" + (
                f" with type '{file_type}'" if file_type else ""
            )

        result_parts = [f"Found {len(files)} file(s) in thread '{search_thread_id}':\n"]

        for file_record in files:
            description = file_record.metadata.get("description", "No description")
            result_parts.append(
                f"\n📄 File ID: {file_record.file_id}\n"
                f"   Type: {file_record.file_type.value}\n"
                f"   Description: {description}\n"
                f"   S3 Path: s3://{file_record.s3_bucket}/{file_record.s3_key}\n"
                f"   Content Type: {file_record.content_type}\n"
                f"   Size: {file_record.size_bytes:,} bytes\n"
                f"   Created: {file_record.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )

            # Include all metadata fields
            if file_record.metadata:
                metadata_items = []
                for key, value in file_record.metadata.items():
                    if key != "description":  # Already shown above
                        # Format value nicely
                        if isinstance(value, list):
                            if len(value) <= 5:
                                metadata_items.append(f"   {key}: {', '.join(map(str, value))}")
                            else:
                                metadata_items.append(
                                    f"   {key}: {', '.join(map(str, value[:5]))}... ({len(value)} total)"
                                )
                        else:
                            metadata_items.append(f"   {key}: {value}")

                if metadata_items:
                    result_parts.append("   Metadata:")
                    result_parts.extend(metadata_items)

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Failed to list files by thread: {e}")
        return f"Error listing files: {str(e)}"


@trace_tool
@tool
async def list_files_by_type(
    file_type: str,
    thread_id: Optional[str] = None,
    limit: int = 20,
) -> str:
    """List files by type (query_result, analysis, coder_output) with full metadata.

    Use this to find all files of a specific type, such as all query results
    or all visualizations. Includes file descriptions and all metadata.

    The thread_id is automatically extracted from the conversation context,
    so you don't need to provide it. If you do provide it, it will override
    the context value.

    Args:
        file_type: File type to filter: "query_result", "analysis", "coder_output", "other"
        thread_id: Optional thread ID to filter by conversation (format: user_id:conversation_id).
                   If not provided, uses thread_id from conversation context.
        limit: Maximum number of files to return (default: 20)

    Returns:
        Formatted string listing files with file_id, description, S3 path, and all metadata
    """
    try:
        file_storage_service = FileStorageService()

        try:
            file_type_enum = FileType(file_type)
        except ValueError:
            return f"Error: Invalid file_type '{file_type}'. Valid types: query_result, analysis, coder_output, other"

        # Get thread_id from parameter or context variable
        context_thread_id = thread_id_context.get()
        logger.debug(
            f"list_files_by_type: thread_id param={thread_id}, "
            f"context_thread_id={context_thread_id}, file_type={file_type}"
        )

        search_thread_id = thread_id or context_thread_id

        if search_thread_id:
            logger.info(
                f"list_files_by_type: Using thread_id='{search_thread_id}' "
                f"(source: {'parameter' if thread_id else 'context'})"
            )
        else:
            logger.info(
                f"list_files_by_type: No thread_id provided or in context, "
                f"will search all files of type '{file_type}'"
            )

        # Extract user_id from thread_id if provided
        user_id = None
        if search_thread_id and ":" in search_thread_id:
            user_id_part = search_thread_id.split(":")[0]
            user_id = user_id_part if user_id_part != "anonymous" else None
            logger.debug(
                f"list_files_by_type: Extracted user_id='{user_id}' "
                f"from thread_id='{search_thread_id}'"
            )
        else:
            logger.debug(f"list_files_by_type: No user_id extracted (thread_id={search_thread_id})")

        # If thread_id available, use list_by_thread; otherwise list_by_file_type
        if search_thread_id:
            logger.info(
                f"list_files_by_type: Querying files by thread with thread_id='{search_thread_id}', "
                f"user_id={user_id}, file_type={file_type_enum}, limit={limit}"
            )
            files = file_storage_service.list_by_thread(
                thread_id=search_thread_id,
                user_id=user_id,
                file_type=file_type_enum,
                limit=limit,
            )
        else:
            logger.info(
                f"list_files_by_type: Querying files by type with file_type={file_type_enum}, "
                f"user_id={user_id}, limit={limit}"
            )
            files = file_storage_service.list_by_file_type(
                file_type=file_type_enum,
                user_id=user_id,
                limit=limit,
            )

        logger.info(
            f"list_files_by_type: Found {len(files)} file(s) "
            f"(type='{file_type}'"
            + (f", thread_id='{search_thread_id}'" if search_thread_id else "")
            + ")"
        )

        if not files:
            return f"No files found with type '{file_type}'" + (
                f" in thread '{search_thread_id}'" if search_thread_id else ""
            )

        result_parts = [f"Found {len(files)} {file_type} file(s):\n"]

        for file_record in files:
            description = file_record.metadata.get("description", "No description")
            result_parts.append(
                f"\n📄 File ID: {file_record.file_id}\n"
                f"   Description: {description}\n"
                f"   S3 Path: s3://{file_record.s3_bucket}/{file_record.s3_key}\n"
                f"   Content Type: {file_record.content_type}\n"
                f"   Size: {file_record.size_bytes:,} bytes\n"
                f"   Created: {file_record.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )

            # Include all metadata fields
            if file_record.metadata:
                metadata_items = []
                for key, value in file_record.metadata.items():
                    if key != "description":  # Already shown above
                        # Format value nicely
                        if isinstance(value, list):
                            if len(value) <= 5:
                                metadata_items.append(f"   {key}: {', '.join(map(str, value))}")
                            else:
                                metadata_items.append(
                                    f"   {key}: {', '.join(map(str, value[:5]))}... ({len(value)} total)"
                                )
                        else:
                            metadata_items.append(f"   {key}: {value}")

                if metadata_items:
                    result_parts.append("   Metadata:")
                    result_parts.extend(metadata_items)

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Failed to list files by type: {e}")
        return f"Error listing files: {str(e)}"
