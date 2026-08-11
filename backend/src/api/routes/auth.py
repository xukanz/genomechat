"""Authentication API routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.config.settings import settings
from src.models.user import RefreshTokenRequest, TokenResponse, User, UserCreate
from src.service.auth.dependencies import get_current_user
from src.service.auth.jwt import (
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
)
from src.service.auth.password import verify_password
from src.service.auth.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])
user_service = UserService()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(user_data: UserCreate) -> TokenResponse:
    """Register a new user.

    Creates a new user account and returns access and refresh tokens.

    Args:
        user_data: User registration data (email, name, password)

    Returns:
        TokenResponse with access token, refresh token, and user details

    Raises:
        HTTPException 400: If validation fails or email already registered
        HTTPException 500: If registration fails

    Example:
        POST /auth/register
        {
            "email": "user@example.com",
            "name": "John Doe",
            "password": "SecurePass123!"
        }
    """
    try:
        # Create user (password validation happens in UserCreate model)
        user = user_service.create_user(user_data)

        # Generate tokens
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        logger.info(f"User registered: {user.email}")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=user,
        )

    except ValueError as e:
        logger.warning(f"Registration failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        ) from e


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Login endpoint using OAuth2 password flow.

    Authenticates user with email and password, returns access and refresh tokens.

    Args:
        form_data: OAuth2 form with username (email) and password

    Returns:
        TokenResponse with access token, refresh token, and user details

    Raises:
        HTTPException 401: If credentials are invalid

    Note:
        OAuth2 uses 'username' field, but we treat it as email

    Example:
        POST /auth/login
        Content-Type: application/x-www-form-urlencoded
        username=user@example.com&password=SecurePass123!
    """
    try:
        # Get user by email (OAuth2 uses 'username' field)
        user_in_db = user_service.get_user_by_email(form_data.username)

        # Verify user exists and password is correct
        if not user_in_db or not verify_password(form_data.password, user_in_db.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Create tokens
        access_token = create_access_token(user_in_db.id)
        refresh_token = create_refresh_token(user_in_db.id)

        logger.info(f"User logged in: {user_in_db.email}")

        # Convert UserInDB to User (remove password)
        user = User(
            id=user_in_db.id,
            email=user_in_db.email,
            name=user_in_db.name,
            role=user_in_db.role,
            created_at=user_in_db.created_at,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=user,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed",
        ) from e


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest) -> TokenResponse:
    """Refresh access token using refresh token.

    Validates a refresh token and returns a new access token.

    Args:
        request: RefreshTokenRequest with refresh_token

    Returns:
        TokenResponse with new access token, refresh token, and user details

    Raises:
        HTTPException 401: If refresh token is invalid or expired

    Example:
        POST /auth/refresh
        {
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        }
    """
    try:
        # Verify refresh token and get user ID
        user_id = verify_refresh_token(request.refresh_token)

        # Get user from database
        user = user_service.get_user_by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Generate new tokens
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        logger.info(f"Token refreshed for user: {user.email}")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=user,
        )

    except ValueError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed",
        ) from e


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)) -> User:
    """Get current authenticated user information.

    Returns the user details for the authenticated user based on the JWT token.

    Args:
        current_user: Current user from JWT token (injected by dependency)

    Returns:
        Current user details

    Raises:
        HTTPException 401: If token is invalid

    Example:
        GET /auth/me
        Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    return current_user


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    """Logout endpoint (placeholder for future token blacklisting).

    Note:
        Since JWT tokens are stateless, logout is primarily handled client-side
        by deleting tokens. This endpoint can be extended in the future to
        implement token blacklisting if needed.

    Args:
        current_user: Current user from JWT token (injected by dependency)

    Returns:
        Success message

    Example:
        POST /auth/logout
        Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    logger.info(f"User logged out: {current_user.email}")
    return {"message": "Logged out successfully"}
