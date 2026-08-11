"""Conversation management API routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from src.models.user import User
from src.models.conversation import (
    Conversation,
    ConversationList,
    ConversationWithMessages,
)
from src.service.storage.conversation_service import ConversationService
from src.service.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


class UpdateTitleRequest(BaseModel):
    """Request model for updating conversation title."""

    title: str


@router.get("", response_model=ConversationList)
async def list_conversations(
    project_id: Optional[str] = Query(None, description="Filter conversations by project ID"),
    current_user: User = Depends(get_current_user),
) -> ConversationList:
    """List all conversations for the current user.

    Args:
        project_id: Optional project ID to filter conversations
        current_user: Current authenticated user (injected by dependency)

    Returns:
        ConversationList with user's conversations ordered by most recent

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 500: If list operation fails
    """
    try:
        conversation_service = ConversationService()
        conversations = conversation_service.list_user_conversations(
            current_user.id, project_id=project_id
        )

        return ConversationList(conversations=conversations, count=len(conversations))

    except Exception as e:
        logger.error(f"Failed to list conversations for user {current_user.id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversations",
        ) from e


@router.get("/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> Conversation:
    """Get a specific conversation by ID.

    Args:
        conversation_id: Conversation's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Conversation metadata

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If conversation not found or doesn't belong to user
        HTTPException 500: If get operation fails

    Note:
        Only returns conversation if it belongs to the current user.
        Authorization is enforced by the service layer.
    """
    try:
        conversation_service = ConversationService()
        conversation = conversation_service.get_conversation(conversation_id, current_user.id)

        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        return conversation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get conversation {conversation_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversation",
        ) from e


@router.get("/{conversation_id}/history", response_model=ConversationWithMessages)
async def get_conversation_history(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConversationWithMessages:
    """Get conversation with full message history.

    Args:
        conversation_id: Conversation's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Conversation with complete message history from checkpointer

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If conversation not found or doesn't belong to user
        HTTPException 500: If get operation fails

    Note:
        Messages are retrieved from the LangGraph checkpointer.
        Returns empty messages array if no checkpoint exists.
    """
    try:
        conversation_service = ConversationService()
        conversation = await conversation_service.get_conversation_history(
            conversation_id, current_user.id
        )

        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        return conversation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get conversation history {conversation_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get conversation history",
        ) from e


@router.patch("/{conversation_id}", response_model=Conversation)
async def update_conversation_title(
    conversation_id: str,
    request: UpdateTitleRequest,
    current_user: User = Depends(get_current_user),
) -> Conversation:
    """Update conversation title.

    Args:
        conversation_id: Conversation's unique identifier
        request: Request body with new title
        current_user: Current authenticated user (injected by dependency)

    Returns:
        Updated conversation metadata

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If conversation not found or doesn't belong to user
        HTTPException 500: If update operation fails
    """
    try:
        conversation_service = ConversationService()

        # Update the title
        success = conversation_service.update_conversation_title(
            conversation_id, current_user.id, request.title
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Fetch and return updated conversation
        conversation = conversation_service.get_conversation(conversation_id, current_user.id)

        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        return conversation

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to update conversation {conversation_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation title",
        ) from e


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a conversation.

    Args:
        conversation_id: Conversation's unique identifier
        current_user: Current authenticated user (injected by dependency)

    Returns:
        204 No Content on successful deletion

    Raises:
        HTTPException 401: If not authenticated
        HTTPException 404: If conversation not found or doesn't belong to user
        HTTPException 500: If delete operation fails

    Note:
        This only deletes the conversation metadata.
        Checkpointer state may need separate cleanup (implementation dependent).
    """
    try:
        conversation_service = ConversationService()
        success = conversation_service.delete_conversation(conversation_id, current_user.id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Return 204 No Content (void return)
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to delete conversation {conversation_id} for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        ) from e
