"""Tests for conversation service."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime

from src.service.storage.conversation_service import ConversationService
from src.models.conversation import Conversation


@pytest.fixture
def mock_mongodb_database():
    """Mock MongoDB database and collection."""
    with patch("src.service.storage.conversation_service.get_mongodb_database") as mock_get_db:
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db
        yield mock_db, mock_collection


@pytest.fixture
def conversation_service(mock_mongodb_database):
    """Create ConversationService instance with mocked database."""
    mock_db, mock_collection = mock_mongodb_database
    service = ConversationService(db_name="test_db")
    service.conversations_collection = mock_collection
    return service


def test_conversation_service_init(mock_mongodb_database):
    """Test ConversationService initialization."""
    service = ConversationService(db_name="test_db")
    assert service.conversations_collection is not None
    assert service.db is not None


def test_generate_thread_id(conversation_service):
    """Test thread_id generation."""
    user_id = "user-123"
    conversation_id = "conv-456"

    thread_id = conversation_service._generate_thread_id(user_id, conversation_id)

    assert thread_id == "user-123:conv-456"


def test_create_conversation(conversation_service):
    """Test creating a conversation."""
    mock_collection = conversation_service.conversations_collection

    # Mock: conversation doesn't exist
    mock_collection.find_one.return_value = None
    # Mock: insert_one succeeds
    mock_collection.insert_one.return_value = None

    conversation = conversation_service.create_conversation(
        conversation_id="conv-123", user_id="user-456", title="Test Conversation"
    )

    assert conversation.id == "conv-123"
    assert conversation.user_id == "user-456"
    assert conversation.title == "Test Conversation"
    mock_collection.insert_one.assert_called_once()

    # Verify thread_id was included in insert
    call_args = mock_collection.insert_one.call_args[0][0]
    assert call_args["thread_id"] == "user-456:conv-123"


def test_list_user_conversations(conversation_service):
    """Test listing user conversations."""
    mock_collection = conversation_service.conversations_collection

    mock_conversations = [
        {
            "conversation_id": "conv-1",
            "user_id": "user-123",
            "title": "Conversation 1",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
        {
            "conversation_id": "conv-2",
            "user_id": "user-123",
            "title": "Conversation 2",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.__iter__.return_value = iter(mock_conversations)
    mock_collection.find.return_value.sort.return_value = mock_cursor

    conversations = conversation_service.list_user_conversations("user-123")

    assert len(conversations) == 2
    assert conversations[0].id == "conv-1"
    assert conversations[1].id == "conv-2"


def test_get_conversation(conversation_service):
    """Test getting a conversation."""
    mock_collection = conversation_service.conversations_collection

    mock_conversation_doc = {
        "conversation_id": "conv-123",
        "user_id": "user-456",
        "title": "Test Conversation",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    mock_collection.find_one.return_value = mock_conversation_doc

    conversation = conversation_service.get_conversation("conv-123", "user-456")

    assert conversation is not None
    assert conversation.id == "conv-123"
    assert conversation.user_id == "user-456"

    # Verify user_id filter was used
    call_args = mock_collection.find_one.call_args[0][0]
    assert call_args["conversation_id"] == "conv-123"
    assert call_args["user_id"] == "user-456"


def test_get_conversation_unauthorized(conversation_service):
    """Test getting conversation with wrong user_id returns None."""
    mock_collection = conversation_service.conversations_collection
    mock_collection.find_one.return_value = None  # Not found due to user_id mismatch

    conversation = conversation_service.get_conversation("conv-123", "wrong-user")

    assert conversation is None
