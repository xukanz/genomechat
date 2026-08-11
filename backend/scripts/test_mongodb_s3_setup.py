#!/usr/bin/env python3
"""Quick test script to verify MongoDB and S3 setup.

This script tests the basic functionality without running full pytest suite.
Run with: python scripts/test_mongodb_s3_setup.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.service.database.connections.mongodb_connection import (
    MongoDBConnection,
    get_mongodb_database,
)
from src.service.auth.user_service import UserService
from src.service.storage.conversation_service import ConversationService
from src.service.storage.file_storage_service import FileStorageService
from src.models.user import UserCreate
from src.models.file_storage import FileRecordCreate, FileType
import pandas as pd


def test_mongodb_connection():
    """Test MongoDB connection."""
    print("Testing MongoDB connection...")
    try:
        conn = MongoDBConnection()
        client = conn.connect()
        db = conn.get_database()
        print(f"✓ Connected to MongoDB database: {db.name}")
        return True
    except Exception as e:
        print(f"✗ MongoDB connection failed: {e}")
        return False


def test_user_service():
    """Test UserService."""
    print("\nTesting UserService...")
    try:
        service = UserService()

        # Test create user
        user_data = UserCreate(
            email=f"test_{pd.Timestamp.now().timestamp()}@example.com",
            name="Test User",
            password="testpassword123",
        )
        user = service.create_user(user_data)
        print(f"✓ Created user: {user.email} (ID: {user.id})")

        # Test get user
        retrieved = service.get_user_by_id(user.id)
        assert retrieved is not None
        print(f"✓ Retrieved user: {retrieved.email}")

        # Cleanup
        service.delete_user(user.id)
        print(f"✓ Deleted test user")
        return True
    except Exception as e:
        print(f"✗ UserService test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_conversation_service():
    """Test ConversationService."""
    print("\nTesting ConversationService...")
    try:
        service = ConversationService()

        user_id = "test-user-123"
        conversation_id = "test-conv-456"

        # Create conversation
        conversation = service.create_conversation(
            conversation_id=conversation_id, user_id=user_id, title="Test Conversation"
        )
        print(f"✓ Created conversation: {conversation.title} (ID: {conversation.id})")

        # Test thread_id format
        thread_id = service._generate_thread_id(user_id, conversation_id)
        assert thread_id == f"{user_id}:{conversation_id}"
        print(f"✓ Thread ID format correct: {thread_id}")

        # Get conversation
        retrieved = service.get_conversation(conversation_id, user_id)
        assert retrieved is not None
        print(f"✓ Retrieved conversation: {retrieved.title}")

        # Cleanup
        service.delete_conversation(conversation_id, user_id)
        print(f"✓ Deleted test conversation")
        return True
    except Exception as e:
        print(f"✗ ConversationService test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_file_storage_service():
    """Test FileStorageService with S3."""
    print("\nTesting FileStorageService with S3...")
    try:
        service = FileStorageService()

        # Check if S3 bucket is configured
        from src.config.settings import settings

        if not settings.aws_default_bucket:
            print("⚠ AWS_DEFAULT_BUCKET not set, skipping S3 test")
            return True

        # Create test DataFrame
        test_df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

        # Save file (query result)
        file_data = FileRecordCreate(
            user_id="test-user-123",
            thread_id="test-user-123:test-conv-456",
            file_type=FileType.QUERY_RESULT,
            s3_bucket=settings.aws_default_bucket,
            s3_key=f"test/users/test-user-123/query_results/test_{pd.Timestamp.now().timestamp()}.csv",
            content_type="csv",
            size_bytes=0,  # Will be calculated
            metadata={
                "query": "SELECT * FROM test",
                "description": "Test query",
            },
        )

        saved_result = service.save_file_from_dataframe(test_df, file_data)
        print(f"✓ Saved file to S3: s3://{saved_result.s3_bucket}/{saved_result.s3_key}")
        print(f"  File ID: {saved_result.file_id}")
        print(f"  File Type: {saved_result.file_type.value}")

        # Retrieve
        retrieved = service.get_by_file_id(saved_result.file_id, user_id="test-user-123")
        assert retrieved is not None
        print(f"✓ Retrieved file record from MongoDB")

        # Cleanup
        service.delete_file(saved_result.file_id, user_id="test-user-123")
        print(f"✓ Deleted test file and S3 object")
        return True
    except Exception as e:
        print(f"✗ FileStorageService test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("MongoDB and S3 Integration Test")
    print("=" * 60)

    results = []

    # Test MongoDB connection
    results.append(("MongoDB Connection", test_mongodb_connection()))

    # Test UserService
    results.append(("UserService", test_user_service()))

    # Test ConversationService
    results.append(("ConversationService", test_conversation_service()))

    # Test FileStorageService
    results.append(("FileStorageService", test_file_storage_service()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {name}")

    all_passed = all(result[1] for result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed. Check output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
