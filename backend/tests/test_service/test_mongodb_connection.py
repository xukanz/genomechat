"""Tests for MongoDB connection."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.service.database.connections.mongodb_connection import (
    MongoDBConnection,
    get_mongodb_client,
    get_mongodb_database,
)


@pytest.fixture
def mock_settings():
    """Mock settings with MongoDB configuration."""
    with patch("src.service.database.connections.mongodb_connection.settings") as mock:
        mock.mongodb_uri = "mongodb://localhost:27017/test"
        mock.mongodb_db_name = "test_db"
        yield mock


@pytest.fixture
def mock_mongo_client():
    """Mock MongoDB client."""
    with patch(
        "src.service.database.connections.mongodb_connection.MongoClient"
    ) as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_db = MagicMock()
        mock_client.__getitem__.return_value = mock_db
        yield mock_client, mock_db


def test_mongodb_connection_init(mock_settings):
    """Test MongoDBConnection initialization."""
    conn = MongoDBConnection(db_name="test_db")
    assert conn.db_name == "test_db"
    assert conn.client is None
    assert conn.db is None


def test_mongodb_connection_connect(mock_settings, mock_mongo_client):
    """Test MongoDB connection."""
    mock_client, mock_db = mock_mongo_client

    conn = MongoDBConnection(db_name="test_db")
    client = conn.connect()

    assert client == mock_client
    assert conn.client == mock_client
    assert conn.db == mock_db


def test_mongodb_connection_get_database(mock_settings, mock_mongo_client):
    """Test getting database from connection."""
    mock_client, mock_db = mock_mongo_client

    # Reset singleton to ensure fresh test
    MongoDBConnection._client = None

    conn = MongoDBConnection(db_name="test_db")
    db = conn.get_database()

    # Verify database was returned and connection is established
    assert db is not None
    assert conn.db is not None
    assert conn.client is not None


def test_mongodb_connection_execute_query_raises_not_implemented(mock_settings):
    """Test that execute_query raises NotImplementedError."""
    conn = MongoDBConnection()

    with pytest.raises(NotImplementedError):
        conn.execute_query("SELECT * FROM users")


def test_mongodb_connection_execute_query_df_raises_not_implemented(mock_settings):
    """Test that execute_query_df raises NotImplementedError."""
    conn = MongoDBConnection()

    with pytest.raises(NotImplementedError):
        conn.execute_query_df("SELECT * FROM users")


def test_mongodb_connection_singleton(mock_settings, mock_mongo_client):
    """Test that MongoDB client is singleton across instances."""
    mock_client, mock_db = mock_mongo_client

    # Reset singleton
    MongoDBConnection._client = None

    conn1 = MongoDBConnection()
    client1 = conn1.connect()

    conn2 = MongoDBConnection()
    client2 = conn2.connect()

    # Both should return the same client instance
    assert client1 == client2
    assert MongoDBConnection._client == client1


def test_get_mongodb_client_convenience_function(mock_settings, mock_mongo_client):
    """Test convenience function get_mongodb_client."""
    mock_client, mock_db = mock_mongo_client

    # Reset singleton
    MongoDBConnection._client = None

    client = get_mongodb_client()
    assert client == mock_client


def test_get_mongodb_database_convenience_function(mock_settings, mock_mongo_client):
    """Test convenience function get_mongodb_database."""
    mock_client, mock_db = mock_mongo_client

    # Reset singleton
    MongoDBConnection._client = None

    db = get_mongodb_database("test_db")
    assert db == mock_db
