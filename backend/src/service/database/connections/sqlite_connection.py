import logging
import threading
from typing import Any

import pandas as pd

from src.config.database import DatabaseSettings
from src.config.paths import resolve_data_path
from src.service.database.database_connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SQLiteConnection(DatabaseConnection):
    def __init__(self, settings: DatabaseSettings):
        logger.info("Initializing SQLite connection")
        self.settings = settings
        # Use thread-local storage for the connection object
        self.thread_local = threading.local()
        # Ensure conn attribute doesn't exist directly on the instance initially
        # The connection will be stored under self.thread_local.conn
        self.db_path = self._resolve_db_path()

    def _resolve_db_path(self) -> str:
        """Resolve SQLite database path.

        Uses centralized path resolution for consistent behavior across
        local development, Docker, and Kubernetes deployments.

        Returns:
            Resolved path to SQLite database file

        Raises:
            FileNotFoundError: If database file not found
            ValueError: If sqlite_path not configured
        """
        if not self.settings.sqlite_path:
            raise ValueError(
                "SQLite database path not specified. "
                "Set sqlite_path in database settings or use DB_REGISTRY_CLINVAR_DATA_PATH_OVERRIDE."
            )

        resolved = resolve_data_path(self.settings.sqlite_path)
        logger.info(f"SQLite database path resolved: {resolved}")
        return str(resolved)

    def connect(self):
        logger.info(f"⎄ Connecting to SQLite database at {self.db_path}")
        try:
            import sqlite3

            # Check if connection already exists for this thread
            if not hasattr(self.thread_local, "conn") or self.thread_local.conn is None:
                # SQLite connections should be per-thread
                self.thread_local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                # Set busy_timeout to 5 minutes (300000 milliseconds) to handle concurrent access
                # This prevents database locks from blocking indefinitely
                self.thread_local.conn.execute("PRAGMA busy_timeout = 300000")
                logger.info("⎄ Successfully connected to SQLite (timeout: 5 minutes)")

            return self.thread_local.conn
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {str(e)}")
            raise

    def execute_query(self, query: str) -> tuple[list[str], list[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple."""
        try:
            # Get thread-local connection
            if not hasattr(self.thread_local, "conn") or self.thread_local.conn is None:
                self.connect()

            cursor = self.thread_local.conn.cursor()
            cursor.execute(query)

            # Get column names and data
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data = cursor.fetchall()
            cursor.close()
            return columns, data
        except Exception as e:
            logger.error(f"Failed to execute SQLite query: {str(e)}")
            raise

    def execute_query_df(self, query: str, timeout: float = 300.0) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame.

        Args:
            query: SQL query string to execute
            timeout: Maximum execution time in seconds (default: 300 seconds / 5 minutes)

        Returns:
            pandas DataFrame with query results

        Raises:
            TimeoutError: If query execution exceeds timeout
            Exception: Other database errors
        """
        import concurrent.futures

        try:
            # Get thread-local connection in the current thread
            if not hasattr(self.thread_local, "conn") or self.thread_local.conn is None:
                self.connect()

            # Capture the connection object to pass to executor thread
            # SQLite connections with check_same_thread=False can be used across threads
            conn = self.thread_local.conn

            # Wrap pd.read_sql_query in ThreadPoolExecutor with timeout
            # This prevents blocking the event loop in async contexts
            def _execute_query():
                # Use the captured connection object instead of thread_local
                # This works because SQLite connection was created with check_same_thread=False
                return pd.read_sql_query(query, conn)

            # Use ThreadPoolExecutor to run query with timeout
            # This works in both sync and async contexts
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_execute_query)
                try:
                    result_df = future.result(timeout=timeout)
                    logger.debug(f"SQL query executed successfully in {timeout}s timeout")
                    return result_df
                except concurrent.futures.TimeoutError:
                    logger.error(f"SQL query execution timed out after {timeout} seconds")
                    raise TimeoutError(
                        f"SQL query execution timed out after {timeout} seconds. "
                        f"The query may be too complex or the database may be locked. "
                        f"Consider simplifying the query or checking database locks."
                    )
        except TimeoutError:
            # Re-raise timeout errors as-is
            raise
        except Exception as e:
            logger.error(f"Failed to execute SQLite query to DataFrame: {str(e)}")
            raise

    def close(self):
        """Close the database connection."""
        if hasattr(self.thread_local, "conn") and self.thread_local.conn:
            self.thread_local.conn.close()
            self.thread_local.conn = None
            logger.info("⎄ SQLite connection closed")

    def __del__(self):
        """Cleanup on destruction."""
        try:
            self.close()
        except Exception:
            # Ignore errors during cleanup
            pass
