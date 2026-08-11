"""FastAPI security dependencies for authentication."""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.models.user import User
from src.service.auth.jwt import get_user_id_from_token
from src.service.auth.user_service import UserService

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """FastAPI dependency to get the current authenticated user.

    This function validates the JWT token from the Authorization header
    and returns the user if valid.

    Args:
        credentials: HTTP Bearer credentials from Authorization header

    Returns:
        User object for the authenticated user

    Raises:
        HTTPException: If token is invalid or user not found

    Example:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"message": f"Hello {user.name}"}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token = credentials.credentials
        user_id = get_user_id_from_token(token)

        # Get user from database
        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        if user is None:
            raise credentials_exception

        return user

    except ValueError as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {e}")
        raise credentials_exception from e


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[User]:
    """FastAPI dependency for optional authentication.

    Returns the authenticated user if a valid token is provided,
    otherwise returns None. Useful for routes that support both
    authenticated and anonymous users.

    Args:
        credentials: Optional HTTP Bearer credentials from Authorization header

    Returns:
        User object if authenticated, None otherwise

    Example:
        @router.post("/chat")
        async def chat(user: Optional[User] = Depends(get_optional_user)):
            user_id = user.id if user else "anonymous"
            # ... rest of handler
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        user_id = get_user_id_from_token(token)

        # Get user from database
        user_service = UserService()
        user = user_service.get_user_by_id(user_id)

        return user

    except (ValueError, HTTPException):
        # Invalid token - treat as anonymous user
        logger.debug("Invalid token in optional auth, treating as anonymous")
        return None
    except Exception as e:
        logger.warning(f"Error in optional auth: {e}, treating as anonymous")
        return None
