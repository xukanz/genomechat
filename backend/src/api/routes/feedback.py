"""Message feedback API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.feedback import (
    ConversationFeedbackList,
    MessageFeedback,
    MessageFeedbackCreate,
)
from src.models.user import User
from src.service.auth.dependencies import get_current_user
from src.service.storage.feedback_service import FeedbackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=MessageFeedback, status_code=status.HTTP_201_CREATED)
async def create_or_update_feedback(
    feedback_data: MessageFeedbackCreate,
    current_user: User = Depends(get_current_user),
) -> MessageFeedback:
    """Create or update feedback for a message (upsert behavior).

    Args:
        feedback_data: Feedback data including conversation_id, message_index, type, note
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Created or updated feedback

    Raises:
        HTTPException 400: If conversation not found or doesn't belong to user
        HTTPException 401: If not authenticated
        HTTPException 500: If operation fails
    """
    try:
        feedback_service = FeedbackService()
        feedback = feedback_service.create_or_update_feedback(current_user.id, feedback_data)
        return feedback

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            f"Failed to create/update feedback for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save feedback",
        ) from e


@router.get("/conversation/{conversation_id}", response_model=ConversationFeedbackList)
async def list_conversation_feedback(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConversationFeedbackList:
    """List all feedback for a specific conversation.

    Used for batch loading feedback states.

    Args:
        conversation_id: Conversation's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        ConversationFeedbackList with feedback entries

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 500: If list operation fails
    """
    try:
        feedback_service = FeedbackService()
        feedback = feedback_service.list_conversation_feedback(current_user.id, conversation_id)
        return ConversationFeedbackList(feedback=feedback, count=len(feedback))

    except Exception as e:
        logger.error(
            f"Failed to list conversation feedback for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list feedback",
        ) from e


@router.get("/message", response_model=MessageFeedback | None)
async def get_message_feedback(
    conversation_id: str = Query(..., description="Conversation ID"),
    message_index: int = Query(..., ge=0, description="Message index in conversation"),
    current_user: User = Depends(get_current_user),
) -> MessageFeedback | None:
    """Get feedback for a specific message.

    Args:
        conversation_id: Conversation's unique identifier
        message_index: Index of the message in the conversation
        current_user: Current authenticated user (injected by dependency)

    Returns:
        MessageFeedback if exists, None otherwise

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 500: If get operation fails
    """
    try:
        feedback_service = FeedbackService()
        feedback = feedback_service.get_message_feedback(
            current_user.id, conversation_id, message_index
        )
        return feedback

    except Exception as e:
        logger.error(
            f"Failed to get message feedback for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feedback",
        ) from e


@router.delete("/{feedback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feedback(
    feedback_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete feedback by ID.

    Args:
        feedback_id: Feedback's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        204 No Content on successful deletion

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If feedback not found or doesn't belong to user
        HTTPException 500: If delete operation fails
    """
    try:
        feedback_service = FeedbackService()
        success = feedback_service.delete_feedback(feedback_id, current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
            )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete feedback {feedback_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete feedback",
        ) from e


@router.delete(
    "/message/{conversation_id}/{message_index}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_feedback_by_message(
    conversation_id: str,
    message_index: int,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete feedback for a specific message.

    Args:
        conversation_id: Conversation's unique identifier
        message_index: Index of the message in the conversation
        current_user: Current authenticated user (injected by dependency)

    Returns:
        204 No Content on successful deletion

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If feedback not found
        HTTPException 500: If delete operation fails
    """
    try:
        feedback_service = FeedbackService()
        success = feedback_service.delete_feedback_by_message(
            current_user.id, conversation_id, message_index
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found",
            )

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete feedback for message {message_index} "
            f"in conversation {conversation_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete feedback",
        ) from e
