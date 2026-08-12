"""Integration tests for MongoDB and S3 integration.

These tests require MongoDB and S3 to be configured.
Run with: pytest tests/test_integration_mongodb_s3.py -v

Set environment variables:
- MONGODB_URI: MongoDB connection string
- AWS_DEFAULT_BUCKET: S3 bucket name
- AWS_ACCESS_KEY_ID: AWS access key
- AWS_SECRET_ACCESS_KEY: AWS secret key
"""

import pytest
import os
import pandas as pd
from datetime import datetime

from src.service.database.connections.mongodb_connection import MongoDBConnection
from src.service.auth.user_service import UserService
from src.service.storage.conversation_service import ConversationService
from src.service.storage.file_storage_service import FileStorageService
from src.models.file_storage import FileRecordCreate, FileType
from src.models.user import UserCreate


# Skip integration tests if MongoDB/S3 not configured
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGODB_CONNECTION_STRING")
AWS_BUCKET = os.getenv("AWS_DEFAULT_BUCKET")
SKIP_INTEGRATION = not MONGODB_URI or not AWS_BUCKET


@pytest.mark.skipif(SKIP_INTEGRATION, reason="MongoDB URI or AWS bucket not configured")
class TestMongoDBIntegration:
    """Integration tests for MongoDB services."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test database."""
        # Use test database
        self.test_db_name = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        yield
        # Cleanup: Drop test database
        try:
            conn = MongoDBConnection(db_name=self.test_db_name)
            client = conn.connect()
            client.drop_database(self.test_db_name)
            conn.close()
        except Exception:
            pass

    def test_mongodb_connection(self):
        """Test MongoDB connection."""
        conn = MongoDBConnection(db_name=self.test_db_name)
        client = conn.connect()

        assert client is not None
        db = conn.get_database()
        assert db is not None
        assert db.name == self.test_db_name

    def test_user_service_crud(self):
        """Test UserService CRUD operations."""
        service = UserService(db_name=self.test_db_name)

        # Create user
        user_data = UserCreate(
            email=f"test_{datetime.now().timestamp()}@example.com",
            name="Test User",
            # validate_password_strength requires 8+ chars with an uppercase,
            # a lowercase, a digit and a special character.
            password="TestPassword123!",
        )
        user = service.create_user(user_data)
        assert user.email == user_data.email
        assert user.id is not None

        # Get user by ID
        retrieved_user = service.get_user_by_id(user.id)
        assert retrieved_user is not None
        assert retrieved_user.email == user.email

        # Get user by email
        retrieved_by_email = service.get_user_by_email(user.email)
        assert retrieved_by_email is not None
        assert retrieved_by_email.id == user.id

        # Delete user
        deleted = service.delete_user(user.id)
        assert deleted is True

        # Verify deleted
        assert service.get_user_by_id(user.id) is None

    def test_conversation_service_crud(self):
        """Test ConversationService CRUD operations."""
        service = ConversationService(db_name=self.test_db_name)

        user_id = "test-user-123"
        conversation_id = "test-conv-456"

        # Create conversation
        conversation = service.create_conversation(
            conversation_id=conversation_id, user_id=user_id, title="Test Conversation"
        )
        assert conversation.id == conversation_id
        assert conversation.user_id == user_id

        # Get conversation
        retrieved = service.get_conversation(conversation_id, user_id)
        assert retrieved is not None
        assert retrieved.title == "Test Conversation"

        # Update timestamp
        updated = service.update_timestamp(conversation_id, user_id)
        assert updated is True

        # List user conversations
        conversations = service.list_user_conversations(user_id)
        assert len(conversations) >= 1
        assert any(c.id == conversation_id for c in conversations)

        # Delete conversation
        deleted = service.delete_conversation(conversation_id, user_id)
        assert deleted is True

        # Verify deleted
        assert service.get_conversation(conversation_id, user_id) is None


@pytest.mark.skipif(SKIP_INTEGRATION, reason="MongoDB URI or AWS bucket not configured")
class TestS3Integration:
    """Integration tests for S3 query results storage."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test database."""
        self.test_db_name = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        yield
        # Cleanup
        try:
            conn = MongoDBConnection(db_name=self.test_db_name)
            client = conn.connect()
            client.drop_database(self.test_db_name)
            conn.close()
        except Exception:
            pass

    def test_file_storage_service_save_and_retrieve(self):
        """Test saving and retrieving files via FileStorageService."""
        service = FileStorageService(db_name=self.test_db_name)

        # Create test DataFrame
        test_df = pd.DataFrame({"col1": [1, 2, 3, 4, 5], "col2": ["a", "b", "c", "d", "e"]})

        # Save file (query result)
        file_data = FileRecordCreate(
            user_id="test-user-123",
            thread_id="test-user-123:test-conv-456",
            file_type=FileType.QUERY_RESULT,
            s3_bucket=AWS_BUCKET,
            s3_key=f"test/users/test-user-123/query_results/test_{datetime.now().timestamp()}.csv",
            content_type="csv",
            size_bytes=0,  # Will be calculated
            metadata={
                "query": "SELECT * FROM test",
                "description": "Integration test query",
            },
        )

        saved_result = service.save_file_from_dataframe(test_df, file_data)
        assert saved_result.file_id is not None
        assert saved_result.s3_bucket == AWS_BUCKET
        assert saved_result.file_type == FileType.QUERY_RESULT

        # Retrieve by file_id
        retrieved = service.get_by_file_id(saved_result.file_id, user_id="test-user-123")
        assert retrieved is not None
        assert retrieved.file_id == saved_result.file_id
        assert retrieved.s3_key == file_data.s3_key

        # List by user
        user_results = service.list_by_user("test-user-123")
        assert len(user_results) >= 1
        assert any(r.file_id == saved_result.file_id for r in user_results)

        # List by thread
        thread_results = service.list_by_thread(
            "test-user-123:test-conv-456", user_id="test-user-123"
        )
        assert len(thread_results) >= 1
        assert any(r.file_id == saved_result.file_id for r in thread_results)

        # List by file type
        query_results = service.list_by_file_type(FileType.QUERY_RESULT, user_id="test-user-123")
        assert len(query_results) >= 1
        assert any(r.file_id == saved_result.file_id for r in query_results)

        # Cleanup: Delete test file
        service.delete_file(saved_result.file_id, user_id="test-user-123")
