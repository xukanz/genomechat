"""MongoDB connection class following the same pattern as other database connections."""

import logging
import threading
from typing import Optional

import pandas as pd
from pymongo import MongoClient
from pymongo.database import Database

from src.config.settings import settings
from src.service.database.database_connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Import pymongo with optional handling
try:
    from pymongo import MongoClient

    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    MongoClient = None


class MongoDBConnection(DatabaseConnection):
    """MongoDB connection with singleton client pattern.

    Follows the same OOP pattern as other database connections.
    Note: MongoDB doesn't use SQL, so execute_query methods raise NotImplementedError.
    Use get_database() for MongoDB-specific operations.
    """

    # Class-level singleton MongoDB client (shared across all instances)
    _client: Optional[MongoClient] = None
    _client_lock = threading.Lock()

    def __init__(self, db_name: Optional[str] = None):
        """Initialize MongoDB connection.

        Args:
            db_name: MongoDB database name (defaults to mongodb_db_name from settings)

        Note:
            Unlike other connections, MongoDB doesn't use DatabaseSettings.
            Settings come from src.config.settings (mongodb_uri, mongodb_db_name).
        """
        logger.info("⎄ Initializing MongoDB connection")
        self.db_name = db_name or getattr(settings, "mongodb_db_name", "langgraph_checkpoints")
        self.client = None
        self.db: Optional[Database] = None

        if not PYMONGO_AVAILABLE:
            logger.warning("⎄ pymongo not available - MongoDB connections will not work")

    def _get_client(self) -> MongoClient:
        """Get or create the singleton MongoDB client.

        Returns:
            MongoDB client instance (singleton, shared across all instances)

        Raises:
            ValueError: If MongoDB URI is not configured
            ImportError: If pymongo is not available
        """
        if not PYMONGO_AVAILABLE:
            raise ImportError(
                "pymongo is required for MongoDB connections. Install with: pip install pymongo"
            )

        if MongoDBConnection._client is None:
            with MongoDBConnection._client_lock:
                # Double-check after acquiring lock
                if MongoDBConnection._client is None:
                    # Support both MONGODB_URI and MONGODB_CONNECTION_STRING env vars
                    mongodb_uri = getattr(settings, "mongodb_uri", None) or getattr(
                        settings, "mongodb_connection_string", None
                    )
                    if not mongodb_uri:
                        raise ValueError(
                            "MongoDB URI required. Set MONGODB_URI or MONGODB_CONNECTION_STRING "
                            "environment variable."
                        )

                    logger.info(
                        f"Creating MongoDB client: {mongodb_uri.split('@')[-1] if '@' in mongodb_uri else 'local'}"
                    )
                    MongoDBConnection._client = MongoClient(mongodb_uri)

        return MongoDBConnection._client

    def connect(self) -> MongoClient:
        """Establish connection to MongoDB.

        Returns:
            MongoDB client instance (singleton)

        Raises:
            ValueError: If MongoDB URI is not configured
            ImportError: If pymongo is not available
        """
        if not PYMONGO_AVAILABLE:
            raise ImportError(
                "pymongo is required for MongoDB connections. Install with: pip install pymongo"
            )

        if self.client is None:
            self.client = self._get_client()
            self.db = self.client[self.db_name]
            logger.info(f"⎄ Connected to MongoDB database: {self.db_name}")

        return self.client

    def get_database(self) -> Database:
        """Get MongoDB database instance.

        Returns:
            MongoDB database instance

        Raises:
            ValueError: If not connected
        """
        if self.db is None:
            self.connect()
        return self.db

    def execute_query(self, query: str):
        """Execute a SQL query - NOT SUPPORTED for MongoDB.

        MongoDB doesn't use SQL queries. Use get_database() for MongoDB operations.

        Raises:
            NotImplementedError: MongoDB doesn't support SQL queries
        """
        raise NotImplementedError(
            "MongoDB doesn't support SQL queries. "
            "Use get_database() to access MongoDB collections directly."
        )

    def execute_query_df(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return DataFrame - NOT SUPPORTED for MongoDB.

        MongoDB doesn't use SQL queries. Use get_database() for MongoDB operations.

        Raises:
            NotImplementedError: MongoDB doesn't support SQL queries
        """
        raise NotImplementedError(
            "MongoDB doesn't support SQL queries. "
            "Use get_database() to access MongoDB collections directly."
        )

    def close(self) -> None:
        """Close the MongoDB connection.

        Note: Client is singleton, so this only clears the instance reference.
        The actual client remains open for other instances to use.
        """
        # Don't close the singleton client - it's shared
        # Just clear instance references
        self.client = None
        self.db = None
        logger.info("⎄ MongoDB connection references cleared")

    @classmethod
    def close_all(cls) -> None:
        """Close the singleton MongoDB client.

        Should be called on application shutdown.
        """
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            logger.info("⎄ MongoDB singleton client closed")


# Module-level cache for database instances (one per db_name)
_db_cache: dict[str, Database] = {}
_db_cache_lock = threading.Lock()


# Convenience functions for backward compatibility and easy access
def get_mongodb_client() -> MongoClient:
    """Get or create the singleton MongoDB client.

    Returns:
        MongoDB client instance (singleton)
    """
    # Access the singleton client directly without creating wrapper instance
    if MongoDBConnection._client is not None:
        return MongoDBConnection._client

    # Create a temporary instance just to initialize the client
    conn = MongoDBConnection()
    return conn.connect()


def get_mongodb_database(db_name: Optional[str] = None) -> Database:
    """Get MongoDB database instance (cached per db_name).

    Uses module-level caching to avoid creating new MongoDBConnection
    instances on every call, while still allowing multiple database names.

    Args:
        db_name: Database name (defaults to mongodb_db_name from settings)

    Returns:
        MongoDB database instance (cached)
    """
    # Resolve default db_name
    resolved_name = db_name or getattr(settings, "mongodb_db_name", "langgraph_checkpoints")

    # Check cache first (fast path without lock)
    if resolved_name in _db_cache:
        return _db_cache[resolved_name]

    # Cache miss - need to create (with lock for thread safety)
    with _db_cache_lock:
        # Double-check after acquiring lock
        if resolved_name in _db_cache:
            return _db_cache[resolved_name]

        # Create connection and cache the database
        conn = MongoDBConnection(db_name=resolved_name)
        db = conn.get_database()
        _db_cache[resolved_name] = db
        return db
