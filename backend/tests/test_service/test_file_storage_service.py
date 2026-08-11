"""Tests for unified file storage service."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import pandas as pd

from src.service.storage.file_storage_service import FileStorageService
from src.models.file_storage import FileRecordCreate, FileType


@pytest.fixture
def mock_mongodb_database():
    """Mock MongoDB database and collection."""
    with patch("src.service.storage.file_storage_service.get_mongodb_database") as mock_get_db:
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db
        yield mock_db, mock_collection


@pytest.fixture
def mock_s3_client():
    """Mock S3 client."""
    with patch("src.service.storage.file_storage_service.get_s3_client") as mock_get_s3:
        mock_client = MagicMock()
        mock_get_s3.return_value = mock_client
        yield mock_client


@pytest.fixture
def file_storage_service(mock_mongodb_database, mock_s3_client):
    """Create FileStorageService instance with mocked dependencies."""
    mock_db, mock_collection = mock_mongodb_database
    service = FileStorageService(db_name="test_db")
    service.files_collection = mock_collection
    service.s3_client = mock_s3_client
    return service


@pytest.fixture
def sample_dataframe():
    """Sample DataFrame for testing."""
    return pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})


def test_file_storage_service_init(mock_mongodb_database, mock_s3_client):
    """Test FileStorageService initialization."""
    service = FileStorageService(db_name="test_db")
    assert service.files_collection is not None
    assert service.s3_client is not None
    assert service.db is not None


def test_save_file(file_storage_service):
    """Test saving file to S3 and MongoDB."""
    file_data = FileRecordCreate(
        user_id="user-123",
        thread_id="user-123:conv-456",
        file_type=FileType.CODER_OUTPUT,
        s3_bucket="test-bucket",
        s3_key="users/user-123/test.txt",
        content_type="txt",
        size_bytes=100,
        metadata={"source": "test"},
    )
    content = b"test content"

    # Mock collection insert
    file_storage_service.files_collection.insert_one = MagicMock()

    result = file_storage_service.save_file(file_data, content)

    # Verify S3 put_object was called
    file_storage_service.s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="users/user-123/test.txt",
        Body=content,
    )

    # Verify MongoDB insert was called
    assert file_storage_service.files_collection.insert_one.called
    assert result.file_id is not None
    assert result.user_id == "user-123"
    assert result.file_type == FileType.CODER_OUTPUT


def test_save_file_from_dataframe(file_storage_service, sample_dataframe):
    """Test saving DataFrame as CSV."""
    file_data = FileRecordCreate(
        user_id="user-123",
        thread_id="user-123:conv-456",
        file_type=FileType.QUERY_RESULT,
        s3_bucket="test-bucket",
        s3_key="users/user-123/query.csv",
        content_type="csv",
        size_bytes=0,  # Will be calculated
        metadata={},
    )

    # Mock collection insert
    file_storage_service.files_collection.insert_one = MagicMock()

    result = file_storage_service.save_file_from_dataframe(sample_dataframe, file_data)

    # Verify S3 put_object was called with CSV content
    assert file_storage_service.s3_client.put_object.called
    call_args = file_storage_service.s3_client.put_object.call_args
    assert call_args[1]["Bucket"] == "test-bucket"
    assert call_args[1]["Key"] == "users/user-123/query.csv"

    # Verify metadata includes DataFrame info
    assert result.metadata["row_count"] == 3
    assert result.metadata["column_count"] == 2
    assert result.metadata["columns"] == ["col1", "col2"]


def test_save_file_from_content(file_storage_service):
    """Test saving file from string content."""
    file_data = FileRecordCreate(
        user_id="user-123",
        thread_id="user-123:conv-456",
        file_type=FileType.CODER_OUTPUT,
        s3_bucket="test-bucket",
        s3_key="users/user-123/test.txt",
        content_type="txt",
        size_bytes=0,  # Will be calculated
        metadata={},
    )
    content = "test content"

    # Mock collection insert
    file_storage_service.files_collection.insert_one = MagicMock()

    result = file_storage_service.save_file_from_content(content, file_data)

    # Verify S3 put_object was called with encoded content
    file_storage_service.s3_client.put_object.assert_called_once()
    call_args = file_storage_service.s3_client.put_object.call_args
    assert call_args[1]["Body"] == content.encode("utf-8")
    assert result.size_bytes == len(content.encode("utf-8"))


def test_track_existing_file(file_storage_service):
    """Test tracking an existing S3 file."""
    file_data = FileRecordCreate(
        user_id="user-123",
        thread_id="user-123:conv-456",
        file_type=FileType.CODER_OUTPUT,
        s3_bucket="test-bucket",
        s3_key="users/user-123/existing.txt",
        content_type="txt",
        size_bytes=0,  # Will be fetched from S3
        metadata={"source": "execute_code"},
    )

    # Mock S3 head_object to get file size
    file_storage_service.s3_client.head_object = MagicMock(return_value={"ContentLength": 200})
    file_storage_service.files_collection.insert_one = MagicMock()

    result = file_storage_service.track_existing_file(file_data)

    # Verify S3 head_object was called to get size
    file_storage_service.s3_client.head_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="users/user-123/existing.txt",
    )

    # Verify MongoDB insert was called (but not S3 put_object)
    assert file_storage_service.files_collection.insert_one.called
    assert file_storage_service.s3_client.put_object.called is False
    assert result.size_bytes == 200


def test_get_by_file_id(file_storage_service):
    """Test getting file record by file_id."""
    file_id = "abc12345"
    mock_doc = {
        "file_id": file_id,
        "user_id": "user-123",
        "thread_id": "user-123:conv-456",
        "file_type": "coder_output",
        "s3_bucket": "test-bucket",
        "s3_key": "users/user-123/test.txt",
        "content_type": "txt",
        "size_bytes": 100,
        "metadata": {},
        "created_at": datetime.utcnow(),
    }

    file_storage_service.files_collection.find_one = MagicMock(return_value=mock_doc)

    result = file_storage_service.get_by_file_id(file_id, "user-123")

    assert result is not None
    assert result.file_id == file_id
    assert result.user_id == "user-123"
    assert result.file_type == FileType.CODER_OUTPUT

    # Verify query includes user_id for authorization
    call_args = file_storage_service.files_collection.find_one.call_args[0][0]
    assert call_args["file_id"] == file_id
    assert call_args["user_id"] == "user-123"


def test_get_by_file_id_not_found(file_storage_service):
    """Test getting file record when not found."""
    file_storage_service.files_collection.find_one = MagicMock(return_value=None)

    result = file_storage_service.get_by_file_id("nonexistent", "user-123")

    assert result is None


def test_list_by_user(file_storage_service):
    """Test listing files by user."""
    mock_docs = [
        {
            "file_id": "file1",
            "user_id": "user-123",
            "thread_id": "user-123:conv-456",
            "file_type": "query_result",
            "s3_bucket": "test-bucket",
            "s3_key": "users/user-123/file1.csv",
            "content_type": "csv",
            "size_bytes": 100,
            "metadata": {},
            "created_at": datetime.utcnow(),
        },
        {
            "file_id": "file2",
            "user_id": "user-123",
            "thread_id": "user-123:conv-456",
            "file_type": "coder_output",
            "s3_bucket": "test-bucket",
            "s3_key": "users/user-123/file2.txt",
            "content_type": "txt",
            "size_bytes": 200,
            "metadata": {},
            "created_at": datetime.utcnow(),
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.__iter__ = MagicMock(return_value=iter(mock_docs))
    file_storage_service.files_collection.find = MagicMock(return_value=mock_cursor)

    results = file_storage_service.list_by_user("user-123")

    assert len(results) == 2
    assert results[0].file_id == "file1"
    assert results[1].file_id == "file2"


def test_list_by_thread(file_storage_service):
    """Test listing files by thread."""
    thread_id = "user-123:conv-456"
    mock_docs = [
        {
            "file_id": "file1",
            "user_id": "user-123",
            "thread_id": thread_id,
            "file_type": "query_result",
            "s3_bucket": "test-bucket",
            "s3_key": "users/user-123/file1.csv",
            "content_type": "csv",
            "size_bytes": 100,
            "metadata": {},
            "created_at": datetime.utcnow(),
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.__iter__ = MagicMock(return_value=iter(mock_docs))
    file_storage_service.files_collection.find = MagicMock(return_value=mock_cursor)

    results = file_storage_service.list_by_thread(thread_id, "user-123")

    assert len(results) == 1
    assert results[0].thread_id == thread_id

    # Verify query includes user_id for authorization
    call_args = file_storage_service.files_collection.find.call_args[0][0]
    assert call_args["thread_id"] == thread_id
    assert call_args["user_id"] == "user-123"


def test_list_by_file_type(file_storage_service):
    """Test listing files by file type."""
    mock_docs = [
        {
            "file_id": "file1",
            "user_id": "user-123",
            "thread_id": "user-123:conv-456",
            "file_type": "query_result",
            "s3_bucket": "test-bucket",
            "s3_key": "users/user-123/file1.csv",
            "content_type": "csv",
            "size_bytes": 100,
            "metadata": {},
            "created_at": datetime.utcnow(),
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.__iter__ = MagicMock(return_value=iter(mock_docs))
    file_storage_service.files_collection.find = MagicMock(return_value=mock_cursor)

    results = file_storage_service.list_by_file_type(FileType.QUERY_RESULT)

    assert len(results) == 1
    assert results[0].file_type == FileType.QUERY_RESULT

    # Verify query includes file_type
    call_args = file_storage_service.files_collection.find.call_args[0][0]
    assert call_args["file_type"] == "query_result"


def test_delete_file(file_storage_service):
    """Test deleting file from S3 and MongoDB."""
    file_id = "abc12345"
    mock_doc = {
        "file_id": file_id,
        "user_id": "user-123",
        "thread_id": "user-123:conv-456",
        "file_type": "coder_output",
        "s3_bucket": "test-bucket",
        "s3_key": "users/user-123/test.txt",
        "content_type": "txt",
        "size_bytes": 100,
        "metadata": {},
        "created_at": datetime.utcnow(),
    }

    file_storage_service.files_collection.find_one = MagicMock(return_value=mock_doc)
    file_storage_service.files_collection.delete_one = MagicMock(
        return_value=MagicMock(deleted_count=1)
    )

    result = file_storage_service.delete_file(file_id, "user-123")

    # Verify S3 delete was called
    file_storage_service.s3_client.delete_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="users/user-123/test.txt",
    )

    # Verify MongoDB delete was called
    assert file_storage_service.files_collection.delete_one.called
    assert result is True


def test_delete_file_not_found(file_storage_service):
    """Test deleting file when not found."""
    file_storage_service.files_collection.find_one = MagicMock(return_value=None)

    result = file_storage_service.delete_file("nonexistent", "user-123")

    assert result is False
    assert file_storage_service.s3_client.delete_object.called is False


def test_get_file_content(file_storage_service):
    """Test retrieving file content from S3."""
    file_id = "abc12345"
    mock_doc = {
        "file_id": file_id,
        "user_id": "user-123",
        "thread_id": "user-123:conv-456",
        "file_type": "coder_output",
        "s3_bucket": "test-bucket",
        "s3_key": "users/user-123/test.txt",
        "content_type": "txt",
        "size_bytes": 100,
        "metadata": {},
        "created_at": datetime.utcnow(),
    }

    file_storage_service.files_collection.find_one = MagicMock(return_value=mock_doc)
    file_storage_service.s3_client.get_object = MagicMock(
        return_value={"Body": MagicMock(read=MagicMock(return_value=b"file content"))}
    )

    content = file_storage_service.get_file_content(file_id, "user-123")

    assert content == b"file content"
    file_storage_service.s3_client.get_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="users/user-123/test.txt",
    )
