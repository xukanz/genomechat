"""Report management API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.report import Report, ReportCreate, ReportList, ReportUpdate
from src.models.user import User
from src.service.auth.dependencies import get_current_user
from src.service.storage.report_service import ReportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=Report, status_code=status.HTTP_201_CREATED)
async def create_report(
    report_data: ReportCreate,
    current_user: User = Depends(get_current_user),
) -> Report:
    """Create a new report from a bookmarked AI response.

    Args:
        report_data: Report creation data including conversation_id, title, content
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Created report with inherited project from conversation

    Raises:
        HTTPException 400: If conversation not found or doesn't belong to user
        HTTPException 401: If not authenticated
        HTTPException 500: If create operation fails
    """
    try:
        report_service = ReportService()
        report = report_service.create_report(current_user.id, report_data)
        return report

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            f"Failed to create report for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create report",
        ) from e


@router.get("", response_model=ReportList)
async def list_reports(
    project_id: Optional[str] = Query(None, description="Filter reports by project ID"),
    current_user: User = Depends(get_current_user),
) -> ReportList:
    """List all reports for the current user.

    Args:
        project_id: Optional project ID to filter reports
        current_user: Current authenticated user (injected by dependency)

    Returns:
        ReportList with user's reports ordered by most recent

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 500: If list operation fails
    """
    try:
        report_service = ReportService()
        reports = report_service.list_user_reports(current_user.id, project_id=project_id)
        return ReportList(reports=reports, count=len(reports))

    except Exception as e:
        logger.error(
            f"Failed to list reports for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list reports",
        ) from e


@router.get("/check", response_model=dict)
async def check_report_exists(
    conversation_id: str = Query(..., description="Conversation ID to check"),
    message_index: int = Query(..., ge=0, description="Message index in conversation"),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Check if a report exists for a specific message.

    Args:
        conversation_id: Conversation's unique identifier
        message_index: Index of the message in the conversation
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Dict with exists (bool) and report_id (str, optional)

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 500: If check operation fails
    """
    try:
        report_service = ReportService()
        report_id = report_service.check_report_exists(
            current_user.id, conversation_id, message_index
        )
        return {"exists": report_id is not None, "report_id": report_id}

    except Exception as e:
        logger.error(
            f"Failed to check report exists for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check report",
        ) from e


@router.get("/conversation/{conversation_id}", response_model=list)
async def list_conversation_reports(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> list:
    """List all reports for a specific conversation.

    Used for batch loading bookmark states.

    Args:
        conversation_id: Conversation's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        List of dicts with report_id and message_index

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 500: If list operation fails
    """
    try:
        report_service = ReportService()
        reports = report_service.list_conversation_reports(current_user.id, conversation_id)
        return reports

    except Exception as e:
        logger.error(
            f"Failed to list conversation reports for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversation reports",
        ) from e


@router.get("/{report_id}", response_model=Report)
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
) -> Report:
    """Get a specific report by ID.

    Args:
        report_id: Report's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Report if found and belongs to user

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If report not found or doesn't belong to user
        HTTPException 500: If get operation fails
    """
    try:
        report_service = ReportService()
        report = report_service.get_report(report_id, current_user.id)

        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get report {report_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get report",
        ) from e


@router.patch("/{report_id}", response_model=Report)
async def update_report(
    report_id: str,
    updates: ReportUpdate,
    current_user: User = Depends(get_current_user),
) -> Report:
    """Update report title.

    Args:
        report_id: Report's unique identifier
        updates: Fields to update (currently only title)
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Updated report

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If report not found or doesn't belong to user
        HTTPException 500: If update operation fails
    """
    try:
        report_service = ReportService()
        report = report_service.update_report(report_id, current_user.id, updates)

        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        return report

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update report {report_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update report",
        ) from e


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a report.

    Args:
        report_id: Report's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        204 No Content on successful deletion

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If report not found or doesn't belong to user
        HTTPException 500: If delete operation fails
    """
    try:
        report_service = ReportService()
        success = report_service.delete_report(report_id, current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Report not found",
            )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete report {report_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete report",
        ) from e
