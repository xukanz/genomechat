"""Tests for database tool S3 integration."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.tools.database import execute_sql_query_and_save


@pytest.fixture
def mock_database_manager():
    """Mock database manager."""
    with patch("src.tools.database.get_database_manager") as mock_get_manager:
        mock_manager = MagicMock()
        mock_df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        mock_manager.execute_query_df.return_value = mock_df
        mock_get_manager.return_value = mock_manager
        yield mock_manager


@pytest.fixture
def mock_settings():
    """Mock settings."""
    with patch("src.config.settings.settings") as mock:
        mock.aws_default_bucket = "test-bucket"
        yield mock


@pytest.fixture
def mock_file_storage_service():
    """Mock FileStorageService.

    The tool imports the service lazily inside the function body, so the patch
    has to land on the defining module rather than on `src.tools.database`.
    """
    with patch("src.service.storage.file_storage_service.FileStorageService") as mock_service_class:
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.file_id = "test-file-id"
        mock_result.s3_bucket = "test-bucket"
        mock_result.s3_key = "users/user-123/query_results/test.csv"
        mock_service.save_file_from_dataframe.return_value = mock_result
        mock_service_class.return_value = mock_service
        yield mock_service


def test_execute_sql_query_and_save_with_s3(
    mock_database_manager, mock_settings, mock_file_storage_service
):
    """Test execute_sql_query_and_save saves to S3 when bucket is configured."""
    result = execute_sql_query_and_save.invoke(
        {"query": "SELECT * FROM test", "description": "Test query"}
    )

    # Verify FileStorageService was called
    mock_file_storage_service.save_file_from_dataframe.assert_called_once()

    # Verify result mentions S3
    assert "s3://" in result or "S3" in result
    assert "test-bucket" in result


def test_execute_sql_query_and_save_fallback_to_local(mock_database_manager):
    """Test execute_sql_query_and_save falls back to local filesystem when S3 not configured."""
    with patch("src.config.settings.settings") as mock_settings:
        mock_settings.aws_default_bucket = None

        with patch("src.tools.database.os.makedirs"):
            with patch("builtins.open", create=True):
                result = execute_sql_query_and_save.invoke(
                    {"query": "SELECT * FROM test", "description": "Test query"}
                )

                # Verify result mentions local path
                assert "outputs" in result or "Local path" in result


def test_execute_sql_query_and_save_empty_result(mock_database_manager):
    """Test execute_sql_query_and_save with empty result."""
    mock_database_manager.execute_query_df.return_value = pd.DataFrame()

    result = execute_sql_query_and_save.invoke(
        {"query": "SELECT * FROM empty_table", "description": "Empty query"}
    )

    assert "no results" in result.lower()
