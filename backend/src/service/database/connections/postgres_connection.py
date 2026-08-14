import pandas as pd
import threading
from typing import List, Any, Tuple
import logging

from src.config.database import DatabaseSettings
from src.service.database.database_connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Import psycopg2 with optional handling
try:
    import psycopg2
    from psycopg2 import pool

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None
    pool = None


class PostgresConnection(DatabaseConnection):
    """PostgreSQL connection with connection pooling support."""

    # Class-level connection pool (shared across instances with same settings)
    _pools: dict = {}
    _pools_lock = threading.Lock()

    def __init__(self, settings: DatabaseSettings):
        logger.info("⎄ Initializing PostgreSQL connection")
        self.settings = settings
        self.conn = None
        self._pool_key = None

        if not PSYCOPG2_AVAILABLE:
            logger.warning("⎄ psycopg2 not available - PostgreSQL connections will not work")

    def _get_pool_key(self) -> str:
        """Generate a unique key for the connection pool based on settings."""
        return f"{self.settings.host}:{self.settings.port}:{self.settings.database_name}:{self.settings.username}"

    def _get_pool(self):
        """Get or create a connection pool for this database configuration."""
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgreSQL connections. Install with: pip install psycopg2-binary"
            )

        pool_key = self._get_pool_key()

        # Check if pool already exists
        if pool_key not in self._pools:
            with self._pools_lock:
                # Double-check after acquiring lock
                if pool_key not in self._pools:
                    try:
                        connection_pool = pool.ThreadedConnectionPool(
                            minconn=1,
                            maxconn=10,
                            dbname=self.settings.database_name,
                            user=self.settings.username,
                            password=self.settings.password,
                            host=self.settings.host,
                            port=self.settings.port,
                        )
                        self._pools[pool_key] = connection_pool
                        logger.info(
                            f"⎄ Created PostgreSQL connection pool for {self.settings.host}:{self.settings.port}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to create PostgreSQL connection pool: {str(e)}")
                        raise

        self._pool_key = pool_key
        return self._pools[pool_key]

    def connect(self):
        """Get a connection from the pool."""
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgreSQL connections. Install with: pip install psycopg2-binary"
            )

        if self.conn is None:
            connection_pool = self._get_pool()
            try:
                self.conn = connection_pool.getconn()
                logger.info("⎄ Obtained PostgreSQL connection from pool")
            except Exception as e:
                logger.error(f"Failed to get connection from pool: {str(e)}")
                raise

        return self.conn

    def execute_query(self, query: str) -> Tuple[List[str], List[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple."""
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL connections")

        if self.conn is None:
            self.connect()

        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            # Get column names and data
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            data = cursor.fetchall()
            cursor.close()
            return columns, data
        except Exception as e:
            logger.error(f"Failed to execute PostgreSQL query: {str(e)}")
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

        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL connections")

        if self.conn is None:
            self.connect()

        # Capture the connection object to pass to executor thread
        # PostgreSQL connections (psycopg2) are thread-safe by default
        conn = self.conn

        # Wrap pd.read_sql_query in ThreadPoolExecutor with timeout
        # This prevents blocking the event loop in async contexts
        def _execute_query():
            # Use the captured connection object
            # PostgreSQL connections are thread-safe, so this works across threads
            return pd.read_sql_query(query, conn)

        # Use ThreadPoolExecutor to run query with timeout
        # This works in both sync and async contexts
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_execute_query)
                try:
                    result_df = future.result(timeout=timeout)
                    logger.debug(f"PostgreSQL query executed successfully in {timeout}s timeout")
                    return result_df
                except concurrent.futures.TimeoutError:
                    logger.error(f"PostgreSQL query execution timed out after {timeout} seconds")
                    raise TimeoutError(
                        f"PostgreSQL query execution timed out after {timeout} seconds. "
                        f"The query may be too complex or the database may be locked. "
                        f"Consider simplifying the query or checking database locks."
                    )
        except TimeoutError:
            # Re-raise timeout errors as-is
            raise
        except Exception as e:
            logger.error(f"Failed to execute PostgreSQL query to DataFrame: {str(e)}")
            raise

    def close(self) -> None:
        """Return the connection to the pool."""
        if self.conn is not None and self._pool_key is not None:
            try:
                connection_pool = self._pools.get(self._pool_key)
                if connection_pool:
                    connection_pool.putconn(self.conn)
                    logger.info("⎄ Returned PostgreSQL connection to pool")
                else:
                    self.conn.close()
                    logger.info("⎄ Closed PostgreSQL connection")
            except Exception as e:
                logger.error(f"Error returning connection to pool: {str(e)}")
            finally:
                self.conn = None
