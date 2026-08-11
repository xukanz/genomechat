"""Artifacts API routes for managing user-generated files and plots."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.file_storage import (
    ArtifactListResponse,
    BatchDownloadUrlItem,
    BatchDownloadUrlRequest,
    BatchDownloadUrlResponse,
    DownloadUrlResponse,
    FileType,
)
from src.models.user import User
from src.service.auth.dependencies import get_current_user
from src.service.storage.file_storage_service import FileStorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    thread_id: Optional[str] = Query(None, description="Filter by conversation thread ID"),
    project_id: Optional[str] = Query(
        None, description="Filter by project ID (shows artifacts from all conversations in project)"
    ),
    file_type: Optional[str] = Query(
        None, description="Filter by file type (query_result, coder_output, analysis, other)"
    ),
    content_type_pattern: Optional[str] = Query(
        None, description="Filter by content type pattern (e.g., 'image' for images)"
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of artifacts to return"),
    offset: int = Query(0, ge=0, description="Number of artifacts to skip for pagination"),
    current_user: User = Depends(get_current_user),
) -> ArtifactListResponse:
    """List user's artifacts with optional filtering.

    Returns artifacts with conversation metadata for display in the UI.
    Supports filtering by thread_id (conversation), project_id, and file_type.
    """
    try:
        service = FileStorageService()

        # Handle project_id filtering - get all conversations in project
        thread_ids = None
        if project_id:
            from src.service.storage.conversation_service import ConversationService
            from src.service.storage.project_service import ProjectService

            # Verify user has access to the project (owner or shared)
            project_service = ProjectService()
            project = project_service.get_project(project_id, current_user.id)
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
                )

            # Get all conversations in this project
            conversation_service = ConversationService()
            conversations = conversation_service.list_user_conversations(
                current_user.id, project_id=project_id
            )

            # Build list of thread_ids for all conversations in project
            # IMPORTANT: Use the conversation OWNER's user_id for thread_id (not current_user.id)
            thread_ids = [f"{conv.user_id}:{conv.id}" for conv in conversations]

            # If no conversations in project, return empty list
            if not thread_ids:
                return ArtifactListResponse(artifacts=[], count=0)

        # Validate thread_id authorization if provided (and not using project filter)
        if thread_id and not project_id:
            from src.service.storage.conversation_service import ConversationService

            # Parse conversation_id from thread_id (format: {user_id}:{conversation_id})
            parts = thread_id.split(":", 1)
            if len(parts) != 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid thread_id format"
                )
            conversation_id = parts[1]

            # Check if user has access to this conversation (owner or shared project)
            conversation_service = ConversationService()
            conversation = conversation_service.get_conversation(conversation_id, current_user.id)
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this conversation's artifacts",
                )

        # Parse file_type if provided
        file_type_enum = None
        if file_type:
            try:
                file_type_enum = FileType(file_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid file_type. Must be one of: {[ft.value for ft in FileType]}",
                )

        # Get artifacts with conversation metadata
        if thread_ids:
            # For project filtering: use optimized bulk query (single $in query)
            artifacts = service.list_artifacts_by_threads_with_metadata(
                thread_ids=thread_ids,
                file_type=file_type_enum,
                content_type_pattern=content_type_pattern,
                limit=limit,
                offset=offset,
            )

            logger.info(
                f"Listed {len(artifacts)} artifacts for user={current_user.id}, "
                f"project_id={project_id}, conversations={len(thread_ids)}, "
                f"file_type={file_type}, limit={limit}"
            )
        else:
            # For single conversation or all artifacts
            artifacts = service.list_artifacts_with_conversation_metadata(
                user_id=current_user.id,
                thread_id=thread_id,
                file_type=file_type_enum,
                content_type_pattern=content_type_pattern,
                limit=limit,
                offset=offset,
            )
            logger.info(
                f"Listed {len(artifacts)} artifacts for user={current_user.id}, "
                f"thread_id={thread_id}, file_type={file_type}, content_type={content_type_pattern}, "
                f"limit={limit}, offset={offset}"
            )

        return ArtifactListResponse(artifacts=artifacts, count=len(artifacts))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list artifacts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve artifacts"
        )


@router.get("/{file_id}/download", response_model=DownloadUrlResponse)
async def get_download_url(
    file_id: str,
    expires_in: int = Query(
        3600, ge=60, le=86400, description="URL expiration time in seconds (1 min to 24 hours)"
    ),
    current_user: User = Depends(get_current_user),
) -> DownloadUrlResponse:
    """Get presigned S3 URL for downloading an artifact.

    Returns a time-limited presigned URL that allows direct download from S3.
    The URL expires after the specified duration (default: 1 hour).
    """
    try:
        service = FileStorageService()

        # First try to get file by user_id (owner case)
        file_record = service.get_by_file_id(file_id, current_user.id)

        if file_record is None:
            # Not the owner - check if user has shared access to the file's conversation
            file_record = service.get_by_file_id(file_id, None)  # Get without user filter
            if file_record is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found"
                )

            # Check if user has shared access via the conversation's project
            thread_id = file_record.thread_id
            if thread_id:
                parts = thread_id.split(":", 1)
                if len(parts) == 2:
                    conversation_id = parts[1]
                    from src.service.storage.conversation_service import ConversationService

                    conversation_service = ConversationService()
                    conversation = conversation_service.get_conversation(
                        conversation_id, current_user.id
                    )
                    if conversation is None:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You do not have access to this artifact",
                        )
            else:
                # No thread_id - only owner can access
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have access to this artifact",
                )

        # Generate presigned URL (file_record is already retrieved and authorized)
        download_url = service.generate_download_url(
            file_id=file_id,
            user_id=None,  # Skip user_id check since we already authorized
            expires_in=expires_in,
        )

        if download_url is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Failed to generate download URL"
            )

        logger.info(f"Generated download URL for file_id={file_id}, user={current_user.id}")

        return DownloadUrlResponse(download_url=download_url, expires_in=expires_in)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate download URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL",
        )


@router.post("/batch-download-urls", response_model=BatchDownloadUrlResponse)
async def get_batch_download_urls(
    request: BatchDownloadUrlRequest,
    current_user: User = Depends(get_current_user),
) -> BatchDownloadUrlResponse:
    """Generate presigned S3 URLs for multiple artifacts in batch.

    Optimized endpoint for fetching download URLs for multiple files at once.
    Uses caching and bulk MongoDB queries for improved performance.

    Returns a list of file IDs with their corresponding download URLs.
    Files that don't exist or the user doesn't have access to will have null URLs.
    """
    try:
        service = FileStorageService()

        # Generate batch URLs (the service method handles caching and authorization)
        url_map = service.generate_batch_download_urls(
            file_ids=request.file_ids,
            user_id=current_user.id,
            expires_in=request.expires_in,
        )

        # Convert to response format
        urls = [
            BatchDownloadUrlItem(file_id=file_id, download_url=url)
            for file_id, url in url_map.items()
        ]

        logger.info(
            f"Batch generated {len([u for u in urls if u.download_url])} download URLs "
            f"for {len(request.file_ids)} requested files, user={current_user.id}"
        )

        return BatchDownloadUrlResponse(urls=urls, expires_in=request.expires_in)

    except Exception as e:
        logger.error(f"Failed to generate batch download URLs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate batch download URLs",
        )
