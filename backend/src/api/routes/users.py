"""User management API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.user import User, UserSearchResult, UserUpdate
from src.service.auth.dependencies import get_current_user
from src.service.auth.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=UserSearchResult)
async def search_users(
    q: str = Query(..., min_length=2, description="Search query (min 2 characters)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    current_user: User = Depends(get_current_user),
) -> UserSearchResult:
    """Search users by email or name for sharing."""
    try:
        user_service = UserService()
        users = user_service.search_users(q, current_user.id, limit)
        return UserSearchResult(users=users, count=len(users))

    except Exception as e:
        logger.error(f"Failed to search users: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search users",
        ) from e


@router.patch("/me", response_model=User)
async def update_current_user(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> User:
    """Update current user's profile information."""
    try:
        if update_data.name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        user_service = UserService()
        updated_user = user_service.update_user(current_user.id, name=update_data.name)

        if updated_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return updated_user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user profile",
        ) from e
