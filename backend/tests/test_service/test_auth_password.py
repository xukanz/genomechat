"""Tests for password utilities."""

import pytest

from src.service.auth.password import (
    hash_password,
    validate_password_strength,
    verify_password,
)


def test_hash_password():
    """Test password hashing."""
    password = "TestPassword123!"
    hashed = hash_password(password)

    assert isinstance(hashed, str)
    assert len(hashed) > 0
    assert hashed != password


def test_verify_password_correct():
    """Test password verification with correct password."""
    password = "TestPassword123!"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True


def test_verify_password_incorrect():
    """Test password verification with incorrect password."""
    password = "TestPassword123!"
    wrong_password = "WrongPassword123!"
    hashed = hash_password(password)

    assert verify_password(wrong_password, hashed) is False


def test_validate_password_strength_valid():
    """Test password strength validation with valid password."""
    password = "SecurePass123!"
    is_valid, error = validate_password_strength(password)

    assert is_valid is True
    assert error == ""


def test_validate_password_strength_too_short():
    """Test password strength validation with too short password."""
    password = "Short1!"
    is_valid, error = validate_password_strength(password)

    assert is_valid is False
    assert "8 characters" in error


def test_validate_password_strength_no_uppercase():
    """Test password strength validation without uppercase."""
    password = "lowercase123!"
    is_valid, error = validate_password_strength(password)

    assert is_valid is False
    assert "uppercase" in error.lower()


def test_validate_password_strength_no_lowercase():
    """Test password strength validation without lowercase."""
    password = "UPPERCASE123!"
    is_valid, error = validate_password_strength(password)

    assert is_valid is False
    assert "lowercase" in error.lower()


def test_validate_password_strength_no_number():
    """Test password strength validation without number."""
    password = "NoNumberPass!"
    is_valid, error = validate_password_strength(password)

    assert is_valid is False
    assert "number" in error.lower()


def test_validate_password_strength_no_special_char():
    """Test password strength validation without special character."""
    password = "NoSpecial123"
    is_valid, error = validate_password_strength(password)

    assert is_valid is False
    assert "special" in error.lower()


def test_password_hashing_different_salts():
    """Test that same password produces different hashes (due to salt)."""
    password = "SamePassword123!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Hashes should be different due to random salt
    assert hash1 != hash2

    # But both should verify correctly
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True
