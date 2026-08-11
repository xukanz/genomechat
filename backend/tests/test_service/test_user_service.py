"""Tests for user service."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from src.service.auth.user_service import UserService
from src.models.user import UserCreate


@pytest.fixture
def mock_mongodb_database():
    """Mock MongoDB database and collection."""
    with patch("src.service.auth.user_service.get_mongodb_database") as mock_get_db:
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db
        yield mock_db, mock_collection


@pytest.fixture
def user_service(mock_mongodb_database):
    """Create UserService instance with mocked database."""
    mock_db, mock_collection = mock_mongodb_database
    service = UserService(db_name="test_db")
    service.users_collection = mock_collection
    return service


def test_user_service_init(mock_mongodb_database):
    """Test UserService initialization."""
    service = UserService(db_name="test_db")
    assert service.users_collection is not None
    assert service.db is not None


def test_create_user_success(user_service):
    """Test creating a user successfully."""
    mock_collection = user_service.users_collection

    # Mock: email doesn't exist
    mock_collection.find_one.return_value = None
    # Mock: insert_one succeeds
    mock_collection.insert_one.return_value = None

    user_data = UserCreate(email="test@example.com", name="Test User", password="password123")

    user = user_service.create_user(user_data)

    assert user.email == "test@example.com"
    assert user.name == "Test User"
    assert user.id is not None
    mock_collection.insert_one.assert_called_once()


def test_create_user_duplicate_email(user_service):
    """Test creating a user with duplicate email raises ValueError."""
    mock_collection = user_service.users_collection

    # Mock: email already exists
    mock_collection.find_one.return_value = {"user_id": "existing-id", "email": "test@example.com"}

    user_data = UserCreate(email="test@example.com", name="Test User", password="password123")

    with pytest.raises(ValueError, match="Email already registered"):
        user_service.create_user(user_data)


def test_get_user_by_email(user_service):
    """Test getting user by email."""
    mock_collection = user_service.users_collection

    mock_user_doc = {
        "user_id": "user-123",
        "email": "test@example.com",
        "name": "Test User",
        "hashed_password": "$2b$12$hashed",
        "role": "user",
        "created_at": datetime.utcnow(),
    }
    mock_collection.find_one.return_value = mock_user_doc

    user = user_service.get_user_by_email("test@example.com")

    assert user is not None
    assert user.email == "test@example.com"
    assert user.id == "user-123"
    assert user.hashed_password == "$2b$12$hashed"


def test_get_user_by_email_not_found(user_service):
    """Test getting user by email when not found."""
    mock_collection = user_service.users_collection
    mock_collection.find_one.return_value = None

    user = user_service.get_user_by_email("nonexistent@example.com")

    assert user is None


def test_get_user_by_id(user_service):
    """Test getting user by ID."""
    mock_collection = user_service.users_collection

    mock_user_doc = {
        "user_id": "user-123",
        "email": "test@example.com",
        "name": "Test User",
        "role": "user",
        "created_at": datetime.utcnow(),
    }
    mock_collection.find_one.return_value = mock_user_doc

    user = user_service.get_user_by_id("user-123")

    assert user is not None
    assert user.id == "user-123"
    assert user.email == "test@example.com"


def test_get_user_by_id_not_found(user_service):
    """Test getting user by ID when not found."""
    mock_collection = user_service.users_collection
    mock_collection.find_one.return_value = None

    user = user_service.get_user_by_id("nonexistent-id")

    assert user is None


def test_delete_user(user_service):
    """Test deleting a user."""
    mock_collection = user_service.users_collection
    mock_collection.delete_one.return_value = MagicMock(deleted_count=1)

    result = user_service.delete_user("user-123")

    assert result is True
    mock_collection.delete_one.assert_called_once_with({"user_id": "user-123"})
