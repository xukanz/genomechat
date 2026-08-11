"""Tests for project API endpoints."""

import uuid
import pytest
from fastapi.testclient import TestClient

from main import app
from src.models.user import UserCreate
from src.service.auth.user_service import UserService
from src.service.storage.project_service import ProjectService
from src.service.storage.conversation_service import ConversationService

client = TestClient(app)


@pytest.fixture
def test_user_data():
    """Fixture for test user data."""
    return {
        "email": "projecttest@example.com",
        "name": "Project Test User",
        "password": "SecurePass123!",
    }


@pytest.fixture
def registered_user(test_user_data):
    """Fixture that creates a registered user and returns auth tokens."""
    user_service = UserService()
    user_data = UserCreate(**test_user_data)
    user = user_service.create_user(user_data)

    # Get auth tokens
    response = client.post(
        "/auth/login",
        data={
            "username": test_user_data["email"],
            "password": test_user_data["password"],
        },
    )
    tokens = response.json()

    yield {"user": user, "access_token": tokens["access_token"]}

    # Cleanup
    try:
        # Delete all projects for this user
        project_service = ProjectService()
        projects = project_service.list_user_projects(user.id)
        for project in projects:
            try:
                project_service.delete_project(project.id, user.id)
            except Exception:
                pass

        user_service.delete_user(user.id)
    except Exception:
        pass


def get_auth_headers(access_token: str) -> dict:
    """Helper to get authorization headers."""
    return {"Authorization": f"Bearer {access_token}"}


def test_list_projects_empty(registered_user):
    """Test listing projects when only default project exists."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.get("/projects", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "projects" in data
    assert "count" in data
    # Should have at least the default "All Chats" project
    assert data["count"] >= 1
    default_project = next((p for p in data["projects"] if p["is_default"]), None)
    assert default_project is not None
    assert default_project["name"] == "All Chats"


def test_list_projects_unauthorized():
    """Test listing projects without authentication."""
    response = client.get("/projects")

    assert response.status_code == 403  # Forbidden without auth


def test_create_project_success(registered_user):
    """Test creating a new project."""
    headers = get_auth_headers(registered_user["access_token"])

    project_data = {
        "name": "Research Project",
        "description": "My research notes",
        "color": "#FF5733",
    }

    response = client.post("/projects", json=project_data, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Research Project"
    assert data["description"] == "My research notes"
    assert data["color"] == "#FF5733"
    assert data["is_default"] is False
    assert data["conversation_count"] == 0
    assert "id" in data
    assert "created_at" in data


def test_create_project_minimal(registered_user):
    """Test creating project with minimal data."""
    headers = get_auth_headers(registered_user["access_token"])

    project_data = {"name": "Minimal Project"}

    response = client.post("/projects", json=project_data, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Minimal Project"
    assert data["description"] is None
    assert data["color"] is None


def test_create_project_invalid_name(registered_user):
    """Test creating project with invalid name."""
    headers = get_auth_headers(registered_user["access_token"])

    project_data = {"name": ""}  # Empty name

    response = client.post("/projects", json=project_data, headers=headers)

    assert response.status_code == 422  # Validation error


def test_create_project_invalid_color(registered_user):
    """Test creating project with invalid color format."""
    headers = get_auth_headers(registered_user["access_token"])

    project_data = {
        "name": "Test Project",
        "color": "invalid-color",  # Not hex format
    }

    response = client.post("/projects", json=project_data, headers=headers)

    assert response.status_code == 422  # Validation error


def test_create_project_unauthorized():
    """Test creating project without authentication."""
    project_data = {"name": "Test Project"}

    response = client.post("/projects", json=project_data)

    assert response.status_code == 403  # Forbidden


def test_get_project_success(registered_user):
    """Test getting a specific project."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a project first
    create_response = client.post(
        "/projects",
        json={"name": "Test Project", "description": "Test"},
        headers=headers,
    )
    project_id = create_response.json()["id"]

    # Get the project
    response = client.get(f"/projects/{project_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == "Test Project"


def test_get_project_not_found(registered_user):
    """Test getting non-existent project."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.get("/projects/non-existent-id", headers=headers)

    assert response.status_code == 404


def test_get_project_unauthorized():
    """Test getting project without authentication."""
    response = client.get("/projects/some-id")

    assert response.status_code == 403


def test_update_project_success(registered_user):
    """Test updating project metadata."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a project
    create_response = client.post("/projects", json={"name": "Original Name"}, headers=headers)
    project_id = create_response.json()["id"]

    # Update the project
    update_data = {
        "name": "Updated Name",
        "description": "New description",
        "color": "#00FF00",
    }
    response = client.patch(f"/projects/{project_id}", json=update_data, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "New description"
    assert data["color"] == "#00FF00"


def test_update_project_partial(registered_user):
    """Test partial update of project."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a project
    create_response = client.post(
        "/projects",
        json={"name": "Original", "description": "Original desc"},
        headers=headers,
    )
    project_id = create_response.json()["id"]

    # Partial update (only name)
    response = client.patch(f"/projects/{project_id}", json={"name": "Updated"}, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["description"] == "Original desc"  # Unchanged


def test_update_project_not_found(registered_user):
    """Test updating non-existent project."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.patch("/projects/non-existent-id", json={"name": "Updated"}, headers=headers)

    assert response.status_code == 404


def test_update_project_unauthorized():
    """Test updating project without authentication."""
    response = client.patch("/projects/some-id", json={"name": "Updated"})

    assert response.status_code == 403


def test_delete_project_success(registered_user):
    """Test deleting a project."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a project
    create_response = client.post("/projects", json={"name": "To Delete"}, headers=headers)
    project_id = create_response.json()["id"]

    # Delete the project
    response = client.delete(f"/projects/{project_id}", headers=headers)

    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/projects/{project_id}", headers=headers)
    assert get_response.status_code == 404


def test_delete_default_project_fails(registered_user):
    """Test that default project cannot be deleted."""
    headers = get_auth_headers(registered_user["access_token"])

    # Get the default project
    list_response = client.get("/projects", headers=headers)
    projects = list_response.json()["projects"]
    default_project = next((p for p in projects if p["is_default"]), None)
    assert default_project is not None

    # Try to delete it
    response = client.delete(f"/projects/{default_project['id']}", headers=headers)

    assert response.status_code == 404  # Should fail


def test_delete_project_not_found(registered_user):
    """Test deleting non-existent project."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.delete("/projects/non-existent-id", headers=headers)

    assert response.status_code == 404


def test_delete_project_unauthorized():
    """Test deleting project without authentication."""
    response = client.delete("/projects/some-id")

    assert response.status_code == 403


def test_move_conversation_to_project_success(registered_user):
    """Test moving a conversation to a different project."""
    headers = get_auth_headers(registered_user["access_token"])
    user_id = registered_user["user"].id

    # Create a conversation with unique ID
    conversation_service = ConversationService()
    conversation = conversation_service.create_conversation(
        conversation_id=f"test-conv-{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        title="Test Conversation",
    )

    # Create a new project
    create_response = client.post("/projects", json={"name": "Target Project"}, headers=headers)
    target_project_id = create_response.json()["id"]

    # Move conversation to new project
    response = client.post(
        f"/projects/{target_project_id}/conversations/{conversation.id}/move",
        headers=headers,
    )

    assert response.status_code == 204

    # Verify conversation was moved
    moved_conversation = conversation_service.get_conversation(conversation.id, user_id)
    assert moved_conversation.project_id == target_project_id


def test_move_conversation_project_not_found(registered_user):
    """Test moving conversation to non-existent project."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.post(
        "/projects/non-existent-proj/conversations/some-conv/move",
        headers=headers,
    )

    assert response.status_code == 404


def test_move_conversation_not_found(registered_user):
    """Test moving non-existent conversation."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a project
    create_response = client.post("/projects", json={"name": "Target Project"}, headers=headers)
    project_id = create_response.json()["id"]

    # Try to move non-existent conversation
    response = client.post(
        f"/projects/{project_id}/conversations/non-existent-conv/move",
        headers=headers,
    )

    assert response.status_code == 404


def test_move_conversation_unauthorized():
    """Test moving conversation without authentication."""
    response = client.post("/projects/proj-id/conversations/conv-id/move")

    assert response.status_code == 403


def test_project_conversation_count_updates(registered_user):
    """Test that conversation counts update correctly."""
    headers = get_auth_headers(registered_user["access_token"])
    user_id = registered_user["user"].id

    # Create a project
    create_response = client.post("/projects", json={"name": "Count Test"}, headers=headers)
    project_id = create_response.json()["id"]

    # Initially should have 0 conversations
    get_response = client.get(f"/projects/{project_id}", headers=headers)
    assert get_response.json()["conversation_count"] == 0

    # Create conversations in this project with unique IDs
    conversation_service = ConversationService()
    for i in range(3):
        conversation_service.create_conversation(
            conversation_id=f"test-conv-count-{uuid.uuid4().hex[:8]}-{i}",
            user_id=user_id,
            title=f"Test {i}",
            project_id=project_id,
        )

    # Verify count increased
    project_service = ProjectService()
    project_service._update_conversation_count(project_id)

    get_response = client.get(f"/projects/{project_id}", headers=headers)
    assert get_response.json()["conversation_count"] == 3


def test_project_isolation_between_users():
    """Test that users can't access each other's projects."""
    # Create two users
    user1_data = {
        "email": "user1@example.com",
        "name": "User 1",
        "password": "SecurePass123!",
    }
    user2_data = {
        "email": "user2@example.com",
        "name": "User 2",
        "password": "SecurePass123!",
    }

    user_service = UserService()

    # Register user 1
    response1 = client.post("/auth/register", json=user1_data)
    user1_tokens = response1.json()
    headers1 = get_auth_headers(user1_tokens["access_token"])

    # Register user 2
    response2 = client.post("/auth/register", json=user2_data)
    user2_tokens = response2.json()
    headers2 = get_auth_headers(user2_tokens["access_token"])

    try:
        # User 1 creates a project
        create_response = client.post(
            "/projects", json={"name": "User 1 Project"}, headers=headers1
        )
        project_id = create_response.json()["id"]

        # User 2 tries to access User 1's project
        get_response = client.get(f"/projects/{project_id}", headers=headers2)
        assert get_response.status_code == 404  # Should not be able to see it

        # User 2 tries to update User 1's project
        update_response = client.patch(
            f"/projects/{project_id}", json={"name": "Hacked"}, headers=headers2
        )
        assert update_response.status_code == 404  # Should not be able to update

        # User 2 tries to delete User 1's project
        delete_response = client.delete(f"/projects/{project_id}", headers=headers2)
        assert delete_response.status_code == 404  # Should not be able to delete

    finally:
        # Cleanup
        try:
            user_service.delete_user(user1_tokens["user"]["id"])
            user_service.delete_user(user2_tokens["user"]["id"])
        except Exception:
            pass
