"""Tests for project snippet API endpoints."""

import pytest
from fastapi.testclient import TestClient

from main import app
from src.models.user import UserCreate
from src.service.auth.user_service import UserService
from src.service.storage.project_service import ProjectService

client = TestClient(app)


@pytest.fixture
def test_user_data():
    """Fixture for test user data."""
    return {
        "email": "snippettest@example.com",
        "name": "Snippet Test User",
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


@pytest.fixture
def sample_project(registered_user):
    """Fixture that creates a sample project for testing snippets."""
    headers = get_auth_headers(registered_user["access_token"])

    project_data = {
        "name": "Snippet Test Project",
        "description": "Project for testing snippets",
    }

    response = client.post("/projects", json=project_data, headers=headers)
    assert response.status_code == 201

    return response.json()


def get_auth_headers(access_token: str) -> dict:
    """Helper to get authorization headers."""
    return {"Authorization": f"Bearer {access_token}"}


def test_list_snippets_empty(registered_user, sample_project):
    """Test listing snippets when project has no snippets."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.get(f"/projects/{sample_project['id']}/snippets", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "snippets" in data
    assert "count" in data
    assert data["count"] == 0
    assert len(data["snippets"]) == 0


def test_create_snippet_success(registered_user, sample_project):
    """Test creating a new snippet."""
    headers = get_auth_headers(registered_user["access_token"])

    snippet_data = {
        "name": "TCR Diversity Analysis",
        "category": "domain_specific",
        "description": "Calculate Shannon diversity index",
        "code": "from scipy.stats import entropy\n\ndef tcr_diversity(counts):\n    return entropy(counts, base=2)",
        "enabled": True,
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "TCR Diversity Analysis"
    assert data["category"] == "domain_specific"
    assert data["description"] == "Calculate Shannon diversity index"
    assert "id" in data
    assert "created_at" in data
    assert data["enabled"] is True


def test_create_snippet_minimal(registered_user, sample_project):
    """Test creating snippet with minimal required data."""
    headers = get_auth_headers(registered_user["access_token"])

    snippet_data = {
        "name": "Simple Plot",
        "description": "Creates a simple line plot",
        "code": "import matplotlib.pyplot as plt\nplt.plot([1,2,3])",
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Simple Plot"
    assert data["category"] == "custom"  # Default category
    assert data["description"] == "Creates a simple line plot"
    assert data["enabled"] is True  # Default enabled


def test_create_snippet_validation_error_empty_name(registered_user, sample_project):
    """Test creating snippet with empty name fails."""
    headers = get_auth_headers(registered_user["access_token"])

    snippet_data = {
        "name": "",  # Empty name
        "description": "Test description",
        "code": "print('test')",
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 422  # Validation error


def test_create_snippet_validation_error_empty_code(registered_user, sample_project):
    """Test creating snippet with empty code fails."""
    headers = get_auth_headers(registered_user["access_token"])

    snippet_data = {
        "name": "Test Snippet",
        "description": "Test description",
        "code": "",  # Empty code
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 422  # Validation error


def test_create_snippet_validation_error_empty_description(registered_user, sample_project):
    """Test creating snippet with empty description fails."""
    headers = get_auth_headers(registered_user["access_token"])

    snippet_data = {
        "name": "Test Snippet",
        "description": "",  # Empty description
        "code": "print('test')",
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 422  # Validation error


def test_create_snippet_validation_error_missing_description(registered_user, sample_project):
    """Test creating snippet without description fails."""
    headers = get_auth_headers(registered_user["access_token"])

    snippet_data = {
        "name": "Test Snippet",
        # No description field
        "code": "print('test')",
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 422  # Validation error


def test_list_snippets_with_data(registered_user, sample_project):
    """Test listing snippets returns created snippets."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create two snippets
    snippet_data_1 = {
        "name": "Snippet 1",
        "description": "First test snippet",
        "code": "print('snippet 1')",
        "category": "visualization",
    }
    snippet_data_2 = {
        "name": "Snippet 2",
        "description": "Second test snippet",
        "code": "print('snippet 2')",
        "category": "data_processing",
    }

    client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data_1,
        headers=headers,
    )
    client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data_2,
        headers=headers,
    )

    # List snippets
    response = client.get(f"/projects/{sample_project['id']}/snippets", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["snippets"]) == 2

    names = [s["name"] for s in data["snippets"]]
    assert "Snippet 1" in names
    assert "Snippet 2" in names


def test_update_snippet(registered_user, sample_project):
    """Test updating a snippet."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a snippet
    snippet_data = {
        "name": "Original Name",
        "description": "Original description",
        "code": "print('original')",
    }
    create_response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )
    snippet_id = create_response.json()["id"]

    # Update the snippet
    update_data = {
        "name": "Updated Name",
        "description": "Added description",
        "category": "statistics",
    }
    response = client.put(
        f"/projects/{sample_project['id']}/snippets/{snippet_id}",
        json=update_data,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Added description"
    assert data["category"] == "statistics"
    assert data["code"] == "print('original')"  # Code unchanged


def test_update_snippet_not_found(registered_user, sample_project):
    """Test updating a non-existent snippet returns 404."""
    headers = get_auth_headers(registered_user["access_token"])

    update_data = {"name": "Updated Name"}
    response = client.put(
        f"/projects/{sample_project['id']}/snippets/nonexistent-id",
        json=update_data,
        headers=headers,
    )

    assert response.status_code == 404


def test_delete_snippet(registered_user, sample_project):
    """Test deleting a snippet."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a snippet
    snippet_data = {
        "name": "To Delete",
        "description": "Snippet to be deleted",
        "code": "print('delete me')",
    }
    create_response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )
    snippet_id = create_response.json()["id"]

    # Delete the snippet
    response = client.delete(
        f"/projects/{sample_project['id']}/snippets/{snippet_id}",
        headers=headers,
    )

    assert response.status_code == 204

    # Verify it's deleted
    list_response = client.get(f"/projects/{sample_project['id']}/snippets", headers=headers)
    snippets = list_response.json()["snippets"]
    assert all(s["id"] != snippet_id for s in snippets)


def test_delete_snippet_not_found(registered_user, sample_project):
    """Test deleting a non-existent snippet returns 404."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.delete(
        f"/projects/{sample_project['id']}/snippets/nonexistent-id",
        headers=headers,
    )

    assert response.status_code == 404


def test_toggle_snippet(registered_user, sample_project):
    """Test toggling a snippet's enabled status."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create an enabled snippet
    snippet_data = {
        "name": "Toggle Test",
        "description": "Snippet for toggle testing",
        "code": "print('toggle')",
        "enabled": True,
    }
    create_response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )
    snippet_id = create_response.json()["id"]
    assert create_response.json()["enabled"] is True

    # Toggle to disabled
    toggle_response = client.patch(
        f"/projects/{sample_project['id']}/snippets/{snippet_id}/toggle",
        headers=headers,
    )

    assert toggle_response.status_code == 200
    assert toggle_response.json()["enabled"] is False

    # Toggle back to enabled
    toggle_response_2 = client.patch(
        f"/projects/{sample_project['id']}/snippets/{snippet_id}/toggle",
        headers=headers,
    )

    assert toggle_response_2.status_code == 200
    assert toggle_response_2.json()["enabled"] is True


def test_toggle_snippet_not_found(registered_user, sample_project):
    """Test toggling a non-existent snippet returns 404."""
    headers = get_auth_headers(registered_user["access_token"])

    response = client.patch(
        f"/projects/{sample_project['id']}/snippets/nonexistent-id/toggle",
        headers=headers,
    )

    assert response.status_code == 404


def test_snippets_unauthorized():
    """Test accessing snippets without authentication."""
    # List snippets without auth
    response = client.get("/projects/some-project-id/snippets")
    assert response.status_code == 403

    # Create snippet without auth
    response = client.post(
        "/projects/some-project-id/snippets",
        json={"name": "Test", "code": "print('test')"},
    )
    assert response.status_code == 403


def test_snippet_size_limit(registered_user, sample_project):
    """Test that snippets exceeding size limits are rejected."""
    headers = get_auth_headers(registered_user["access_token"])

    # Create a snippet with code exceeding 10KB limit
    large_code = "x = " + "1" * 15000  # Over 10KB

    snippet_data = {
        "name": "Large Snippet",
        "description": "Snippet with oversized code",
        "code": large_code,
    }

    response = client.post(
        f"/projects/{sample_project['id']}/snippets",
        json=snippet_data,
        headers=headers,
    )

    assert response.status_code == 422  # Validation error (model validation)


def test_snippet_categories(registered_user, sample_project):
    """Test creating snippets with different valid categories."""
    headers = get_auth_headers(registered_user["access_token"])

    categories = [
        "visualization",
        "data_processing",
        "statistics",
        "file_operations",
        "domain_specific",
        "custom",
    ]

    for category in categories:
        snippet_data = {
            "name": f"Test {category}",
            "description": f"Test snippet for {category} category",
            "code": f"# {category} snippet",
            "category": category,
        }

        response = client.post(
            f"/projects/{sample_project['id']}/snippets",
            json=snippet_data,
            headers=headers,
        )

        assert response.status_code == 201
        assert response.json()["category"] == category
