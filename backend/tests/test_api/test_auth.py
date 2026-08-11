"""Tests for authentication API endpoints."""

import pytest
from fastapi.testclient import TestClient

from main import app
from src.models.user import UserCreate
from src.service.auth.user_service import UserService

client = TestClient(app)


@pytest.fixture
def test_user_data():
    """Fixture for test user data."""
    return {
        "email": "test@example.com",
        "name": "Test User",
        "password": "SecurePass123!",
    }


@pytest.fixture
def registered_user(test_user_data):
    """Fixture that creates a registered user."""
    user_service = UserService()
    user_data = UserCreate(**test_user_data)
    user = user_service.create_user(user_data)
    yield user
    # Cleanup
    try:
        user_service.delete_user(user.id)
    except Exception:
        pass


def test_register_success(test_user_data):
    """Test successful user registration."""
    response = client.post("/auth/register", json=test_user_data)

    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data
    assert data["user"]["email"] == test_user_data["email"]
    assert data["user"]["name"] == test_user_data["name"]
    assert "id" in data["user"]

    # Cleanup
    user_service = UserService()
    user_service.delete_user(data["user"]["id"])


def test_register_duplicate_email(test_user_data, registered_user):
    """Test registration with duplicate email."""
    response = client.post("/auth/register", json=test_user_data)

    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_register_weak_password(test_user_data):
    """Test registration with weak password."""
    weak_password_data = test_user_data.copy()
    weak_password_data["password"] = "weak"

    response = client.post("/auth/register", json=weak_password_data)

    assert response.status_code == 422  # Validation error


def test_login_success(test_user_data, registered_user):
    """Test successful login."""
    response = client.post(
        "/auth/login",
        data={
            "username": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "user" in data


def test_login_invalid_credentials(test_user_data, registered_user):
    """Test login with invalid credentials."""
    response = client.post(
        "/auth/login",
        data={
            "username": test_user_data["email"],
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"].lower()


def test_login_nonexistent_user():
    """Test login with non-existent user."""
    response = client.post(
        "/auth/login",
        data={
            "username": "nonexistent@example.com",
            "password": "SomePassword123!",
        },
    )

    assert response.status_code == 401


def test_refresh_token_success(test_user_data, registered_user):
    """Test token refresh."""
    # First login to get refresh token
    login_response = client.post(
        "/auth/login",
        data={
            "username": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    refresh_token = login_response.json()["refresh_token"]

    # Refresh token
    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_refresh_token_invalid():
    """Test refresh with invalid token."""
    response = client.post("/auth/refresh", json={"refresh_token": "invalid.token"})

    assert response.status_code == 401


def test_get_current_user(test_user_data, registered_user):
    """Test getting current user info."""
    # Login to get token
    login_response = client.post(
        "/auth/login",
        data={
            "username": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    access_token = login_response.json()["access_token"]

    # Get current user
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user_data["email"]
    assert data["name"] == test_user_data["name"]
    assert "id" in data


def test_get_current_user_no_token():
    """Test getting current user without token."""
    response = client.get("/auth/me")

    assert response.status_code == 403  # Forbidden (no credentials)


def test_get_current_user_invalid_token():
    """Test getting current user with invalid token."""
    response = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})

    assert response.status_code == 401


def test_logout(test_user_data, registered_user):
    """Test logout endpoint."""
    # Login to get token
    login_response = client.post(
        "/auth/login",
        data={
            "username": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    access_token = login_response.json()["access_token"]

    # Logout
    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert "message" in response.json()
