"""Tests for JWT token utilities."""

import pytest
from datetime import timedelta

from src.service.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_id_from_token,
    verify_refresh_token,
)


def test_create_access_token():
    """Test access token creation."""
    user_id = "test-user-123"
    token = create_access_token(user_id)

    assert isinstance(token, str)
    assert len(token) > 0

    # Decode and verify
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "access"
    assert "exp" in payload


def test_create_refresh_token():
    """Test refresh token creation."""
    user_id = "test-user-123"
    token = create_refresh_token(user_id)

    assert isinstance(token, str)
    assert len(token) > 0

    # Decode and verify
    payload = decode_token(token)
    assert payload["sub"] == user_id
    assert payload["type"] == "refresh"
    assert "exp" in payload


def test_get_user_id_from_token():
    """Test extracting user ID from token."""
    user_id = "test-user-456"
    token = create_access_token(user_id)

    extracted_id = get_user_id_from_token(token)
    assert extracted_id == user_id


def test_verify_refresh_token():
    """Test refresh token verification."""
    user_id = "test-user-789"
    token = create_refresh_token(user_id)

    verified_id = verify_refresh_token(token)
    assert verified_id == user_id


def test_verify_refresh_token_with_access_token_fails():
    """Test that access token cannot be used as refresh token."""
    user_id = "test-user-999"
    access_token = create_access_token(user_id)

    with pytest.raises(ValueError, match="not a refresh token"):
        verify_refresh_token(access_token)


def test_invalid_token_raises_error():
    """Test that invalid token raises ValueError."""
    invalid_token = "invalid.token.here"

    with pytest.raises(ValueError):
        decode_token(invalid_token)


def test_expired_token_raises_error():
    """Test that expired token raises ValueError."""
    user_id = "test-user-expired"
    # Create token with very short expiration
    token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))

    with pytest.raises(ValueError):
        decode_token(token)


def test_custom_expiration():
    """Test token creation with custom expiration."""
    user_id = "test-user-custom"
    custom_delta = timedelta(hours=2)
    token = create_access_token(user_id, expires_delta=custom_delta)

    payload = decode_token(token)
    assert payload["sub"] == user_id
