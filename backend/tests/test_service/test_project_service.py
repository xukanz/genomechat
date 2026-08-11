"""Tests for project service."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.models.project import Project, ProjectCreate, ProjectUpdate
from src.service.storage.project_service import ProjectService


@pytest.fixture
def mock_mongodb_database():
    """Mock MongoDB database and collections."""
    with patch("src.service.storage.project_service.get_mongodb_database") as mock_get_db:
        mock_db = MagicMock()
        mock_projects_collection = MagicMock()
        mock_conversations_collection = MagicMock()

        def get_collection(name):
            if name == "projects":
                return mock_projects_collection
            elif name == "conversations":
                return mock_conversations_collection
            return MagicMock()

        mock_db.__getitem__.side_effect = get_collection
        mock_db.name = "test_db"
        mock_get_db.return_value = mock_db
        yield mock_db, mock_projects_collection, mock_conversations_collection


@pytest.fixture
def project_service(mock_mongodb_database):
    """Create ProjectService instance with mocked database."""
    mock_db, mock_projects_collection, mock_conversations_collection = mock_mongodb_database
    service = ProjectService(db_name="test_db")
    service.projects_collection = mock_projects_collection
    service.conversations_collection = mock_conversations_collection
    return service


def test_project_service_init(mock_mongodb_database):
    """Test ProjectService initialization."""
    service = ProjectService(db_name="test_db")
    assert service.projects_collection is not None
    assert service.conversations_collection is not None
    assert service.db is not None


def test_ensure_default_project_exists(project_service):
    """Test ensuring default project exists when it already exists."""
    mock_collection = project_service.projects_collection

    # Mock: default project exists
    mock_collection.find_one.return_value = {
        "project_id": "proj-123",
        "user_id": "user-456",
        "name": "All Chats",
        "description": "Default project",
        "color": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_default": True,
        "conversation_count": 5,
        "last_conversation_at": datetime.utcnow(),
    }

    project = project_service.ensure_default_project("user-456")

    assert project.id == "proj-123"
    assert project.name == "All Chats"
    assert project.is_default is True
    mock_collection.insert_one.assert_not_called()


def test_ensure_default_project_creates(project_service):
    """Test ensuring default project creates when it doesn't exist."""
    mock_collection = project_service.projects_collection

    # Mock: no default project exists
    mock_collection.find_one.return_value = None
    mock_collection.insert_one.return_value = None

    project = project_service.ensure_default_project("user-456")

    assert project.name == "All Chats"
    assert project.user_id == "user-456"
    assert project.is_default is True
    mock_collection.insert_one.assert_called_once()


def test_create_project(project_service):
    """Test creating a new project."""
    mock_collection = project_service.projects_collection
    mock_collection.insert_one.return_value = None

    project_data = ProjectCreate(
        name="Research Project", description="My research", color="#FF5733"
    )

    project = project_service.create_project("user-123", project_data)

    assert project.name == "Research Project"
    assert project.description == "My research"
    assert project.color == "#FF5733"
    assert project.user_id == "user-123"
    assert project.is_default is False
    assert project.conversation_count == 0
    mock_collection.insert_one.assert_called_once()


def test_list_user_projects(project_service):
    """Test listing user projects."""
    mock_collection = project_service.projects_collection

    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = [
        {
            "project_id": "proj-1",
            "user_id": "user-123",
            "name": "Project 1",
            "description": "First project",
            "color": "#FF0000",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_default": False,
            "conversation_count": 3,
            "last_conversation_at": datetime.utcnow(),
        },
        {
            "project_id": "proj-2",
            "user_id": "user-123",
            "name": "All Chats",
            "description": "Default",
            "color": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "is_default": True,
            "conversation_count": 10,
            "last_conversation_at": datetime.utcnow(),
        },
    ]
    mock_cursor.sort.return_value = mock_cursor
    mock_collection.find.return_value = mock_cursor

    projects = project_service.list_user_projects("user-123")

    assert len(projects) == 2
    assert projects[0].name == "Project 1"
    assert projects[1].name == "All Chats"
    mock_collection.find.assert_called_once_with({"user_id": "user-123"})


def test_get_project(project_service):
    """Test getting a specific project."""
    mock_collection = project_service.projects_collection

    mock_collection.find_one.return_value = {
        "project_id": "proj-123",
        "user_id": "user-456",
        "name": "My Project",
        "description": "Test",
        "color": "#00FF00",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_default": False,
        "conversation_count": 5,
        "last_conversation_at": datetime.utcnow(),
    }

    project = project_service.get_project("proj-123", "user-456")

    assert project is not None
    assert project.id == "proj-123"
    assert project.name == "My Project"
    mock_collection.find_one.assert_called_once_with(
        {"project_id": "proj-123", "user_id": "user-456"}
    )


def test_get_project_not_found(project_service):
    """Test getting a non-existent project."""
    mock_collection = project_service.projects_collection
    mock_collection.find_one.return_value = None

    project = project_service.get_project("proj-999", "user-456")

    assert project is None


def test_get_project_unauthorized(project_service):
    """Test getting a project from different user."""
    mock_collection = project_service.projects_collection
    mock_collection.find_one.return_value = None

    project = project_service.get_project("proj-123", "wrong-user")

    assert project is None
    mock_collection.find_one.assert_called_once_with(
        {"project_id": "proj-123", "user_id": "wrong-user"}
    )


def test_update_project(project_service):
    """Test updating project metadata."""
    mock_collection = project_service.projects_collection
    mock_result = MagicMock()
    mock_result.modified_count = 1
    mock_collection.update_one.return_value = mock_result

    updates = ProjectUpdate(name="Updated Name", color="#0000FF")

    success = project_service.update_project("proj-123", "user-456", updates)

    assert success is True
    mock_collection.update_one.assert_called_once()

    # Verify update included the new values
    call_args = mock_collection.update_one.call_args
    assert call_args[0][0] == {"project_id": "proj-123", "user_id": "user-456"}
    update_doc = call_args[0][1]["$set"]
    assert update_doc["name"] == "Updated Name"
    assert update_doc["color"] == "#0000FF"
    assert "updated_at" in update_doc


def test_update_project_not_found(project_service):
    """Test updating non-existent project."""
    mock_collection = project_service.projects_collection
    mock_result = MagicMock()
    mock_result.modified_count = 0
    mock_collection.update_one.return_value = mock_result

    updates = ProjectUpdate(name="Updated Name")

    success = project_service.update_project("proj-999", "user-456", updates)

    assert success is False


def test_delete_project_moves_conversations(project_service):
    """Test deleting project moves conversations to default project."""
    mock_projects = project_service.projects_collection
    mock_conversations = project_service.conversations_collection

    # Mock get_project to return a non-default project
    with (
        patch.object(project_service, "get_project") as mock_get_project,
        patch.object(project_service, "ensure_default_project") as mock_ensure_default,
        patch.object(project_service, "_update_conversation_count") as mock_update_count,
    ):
        mock_project = MagicMock()
        mock_project.is_default = False
        mock_get_project.return_value = mock_project

        mock_default = MagicMock()
        mock_default.id = "default-proj-id"
        mock_ensure_default.return_value = mock_default

        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_projects.delete_one.return_value = mock_result

        success = project_service.delete_project("proj-123", "user-456")

        assert success is True
        mock_conversations.update_many.assert_called_once()
        mock_update_count.assert_called_once_with("default-proj-id")


def test_delete_default_project_fails(project_service):
    """Test cannot delete default project."""
    with patch.object(project_service, "get_project") as mock_get_project:
        mock_project = MagicMock()
        mock_project.is_default = True
        mock_get_project.return_value = mock_project

        success = project_service.delete_project("proj-123", "user-456")

        assert success is False


def test_move_conversation_to_project(project_service):
    """Test moving conversation to different project."""
    mock_projects = project_service.projects_collection
    mock_conversations = project_service.conversations_collection

    with (
        patch.object(project_service, "get_project") as mock_get_project,
        patch.object(project_service, "_update_conversation_count") as mock_update_count,
    ):
        mock_project = MagicMock()
        mock_get_project.return_value = mock_project

        # Mock existing conversation
        mock_conversations.find_one.return_value = {
            "conversation_id": "conv-123",
            "user_id": "user-456",
            "project_id": "old-proj-id",
        }

        mock_result = MagicMock()
        mock_result.modified_count = 1
        mock_conversations.update_one.return_value = mock_result

        success = project_service.move_conversation_to_project(
            "conv-123", "new-proj-id", "user-456"
        )

        assert success is True
        assert mock_update_count.call_count == 2  # Old and new project


def test_move_conversation_project_not_found(project_service):
    """Test moving conversation to non-existent project."""
    with patch.object(project_service, "get_project") as mock_get_project:
        mock_get_project.return_value = None

        success = project_service.move_conversation_to_project("conv-123", "proj-999", "user-456")

        assert success is False


def test_move_conversation_not_found(project_service):
    """Test moving non-existent conversation."""
    mock_conversations = project_service.conversations_collection

    with patch.object(project_service, "get_project") as mock_get_project:
        mock_get_project.return_value = MagicMock()
        mock_conversations.find_one.return_value = None

        success = project_service.move_conversation_to_project("conv-999", "proj-123", "user-456")

        assert success is False


def test_update_conversation_count(project_service):
    """Test updating conversation count for a project."""
    mock_projects = project_service.projects_collection
    mock_conversations = project_service.conversations_collection

    # Mock conversation count
    mock_conversations.count_documents.return_value = 5

    # Mock latest conversation
    mock_conversations.find_one.return_value = {"updated_at": datetime.utcnow()}

    project_service._update_conversation_count("proj-123")

    mock_projects.update_one.assert_called_once()
    call_args = mock_projects.update_one.call_args
    assert call_args[0][0] == {"project_id": "proj-123"}
    update_doc = call_args[0][1]["$set"]
    assert update_doc["conversation_count"] == 5
    assert "last_conversation_at" in update_doc
