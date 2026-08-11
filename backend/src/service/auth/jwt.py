"""JWT token creation and verification utilities."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from src.config.settings import settings

logger = logging.getLogger(__name__)


def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token for a user.

    Args:
        user_id: The user's ID to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token("user-123")
        >>> isinstance(token, str)
        True
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )

    to_encode = {"sub": user_id, "exp": expire, "type": "access"}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token for a user.

    Args:
        user_id: The user's ID to encode in the token

    Returns:
        Encoded JWT refresh token string

    Example:
        >>> token = create_refresh_token("user-123")
        >>> isinstance(token, str)
        True
    """
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)

    to_encode = {"sub": user_id, "exp": expire, "type": "refresh"}
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        Decoded token payload as dictionary

    Raises:
        ValueError: If token is invalid, expired, or malformed

    Example:
        >>> token = create_access_token("user-123")
        >>> payload = decode_token(token)
        >>> payload["sub"]
        'user-123'
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


def get_user_id_from_token(token: str) -> str:
    """Extract user ID from a JWT token.

    Args:
        token: JWT token string

    Returns:
        User ID from the token "sub" claim

    Raises:
        ValueError: If token is invalid or missing user ID

    Example:
        >>> token = create_access_token("user-123")
        >>> get_user_id_from_token(token)
        'user-123'
    """
    payload = decode_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise ValueError("Invalid token: missing user ID")
    return user_id


def verify_refresh_token(token: str) -> str:
    """Verify a refresh token and return the user ID.

    Args:
        token: Refresh token string

    Returns:
        User ID from the token

    Raises:
        ValueError: If token is invalid, expired, or not a refresh token

    Example:
        >>> token = create_refresh_token("user-123")
        >>> verify_refresh_token(token)
        'user-123'
    """
    payload = decode_token(token)
    token_type = payload.get("type")
    if token_type != "refresh":
        raise ValueError("Invalid token: not a refresh token")

    user_id: str = payload.get("sub")
    if user_id is None:
        raise ValueError("Invalid token: missing user ID")
    return user_id
