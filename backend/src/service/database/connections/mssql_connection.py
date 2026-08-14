import pandas as pd
import threading
from queue import Empty, Full, Queue
from typing import List, Any, Tuple
import logging

from src.config.database import DatabaseSettings
from src.service.database.database_connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Import pyodbc at the module level for easier testing
try:
    import pyodbc

    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False
    pyodbc = None


class MSSQLConnection(DatabaseConnection):
    """MSSQL connection with simple connection pooling support."""

    # Constants for connection settings
    ENCRYPT = "yes"  # Changed from "Mandatory" to "yes" which is a valid value
    TRUST_SERVER_CERTIFICATE = "yes"  # Changed from "True" to "yes" which is a valid value
    CONNECTION_TIMEOUT = 15
    APPLICATION_INTENT = "ReadOnly"  # Changed from ReadWrite to ReadOnly

    # Class-level connection pools (shared across instances with same settings)
    _pools: dict = {}
    _pools_lock = threading.Lock()
    _max_pool_size = 10

    def __init__(self, settings: DatabaseSettings):
        logger.info("⎄ Initializing MSSQL connection")
        self.settings = settings
        self.conn = None
        self._pool_key = None

        if not PYODBC_AVAILABLE:
            logger.warning("⎄ pyodbc not available - MSSQL connections will not work")

    def _get_pool_key(self) -> str:
        """Generate a unique key for the connection pool based on settings."""
        return f"{self.settings.host}:{self.settings.port}:{self.settings.database_name}:{self.settings.username}"

    def _build_connection_string(self) -> str:
        """Build the ODBC connection string."""
        return (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.settings.host};"
            f"DATABASE={self.settings.database_name};"
            f"UID={self.settings.username};"
            f"PWD={self.settings.password};"
            f"Connection Timeout={self.CONNECTION_TIMEOUT};"
            f"Encrypt={self.ENCRYPT};"
            f"TrustServerCertificate={self.TRUST_SERVER_CERTIFICATE};"
            f"ApplicationIntent={self.APPLICATION_INTENT};"
        )

    def _get_pool(self) -> Queue:
        """Get or create a connection pool for this database configuration."""
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for MSSQL connections")

        pool_key = self._get_pool_key()

        # Check if pool already exists
        if pool_key not in self._pools:
            with self._pools_lock:
                # Double-check after acquiring lock
                if pool_key not in self._pools:
                    connection_pool = Queue(maxsize=self._max_pool_size)
                    self._pools[pool_key] = connection_pool
                    logger.info(
                        f"⎄ Created MSSQL connection pool for {self.settings.host}:{self.settings.port}"
                    )

        self._pool_key = pool_key
        return self._pools[pool_key]

    def _create_connection(self):
        """Create a new MSSQL connection."""
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for MSSQL connections")

        connection_string = self._build_connection_string()
        try:
            conn = pyodbc.connect(connection_string)
            logger.info("⎄ Created new MSSQL connection")
            return conn
        except Exception as e:
            logger.error(f"Failed to create MSSQL connection: {str(e)}")
            raise

    def connect(self):
        """Get a connection from the pool or create a new one."""
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for MSSQL connections")

        if self.conn is None:
            connection_pool = self._get_pool()
            try:
                # Try to get connection from pool (non-blocking)
                try:
                    self.conn = connection_pool.get_nowait()
                    logger.info("⎄ Obtained MSSQL connection from pool")
                except Empty:
                    # Pool is empty, create new connection
                    self.conn = self._create_connection()
            except Exception as e:
                logger.error(f"Failed to get connection: {str(e)}")
                raise

        return self.conn

    def execute_query(self, query: str) -> Tuple[List[str], List[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple."""
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for MSSQL connections")

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
            logger.error(f"Failed to execute MSSQL query: {str(e)}")
            raise

    def execute_query_df(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame."""
        if not PYODBC_AVAILABLE:
            raise ImportError("pyodbc is required for MSSQL connections")

        if self.conn is None:
            self.connect()

        try:
            return pd.read_sql_query(query, self.conn)
        except Exception as e:
            logger.error(f"Failed to execute MSSQL query to DataFrame: {str(e)}")
            raise

    def close(self) -> None:
        """Return the connection to the pool or close it if pool is full."""
        if self.conn is not None and self._pool_key is not None:
            try:
                connection_pool = self._pools.get(self._pool_key)
                if connection_pool:
                    # Try to return connection to pool (non-blocking)
                    try:
                        connection_pool.put_nowait(self.conn)
                        logger.info("⎄ Returned MSSQL connection to pool")
                    except Full:
                        # Pool is full, close the connection
                        self.conn.close()
                        logger.info("⎄ Closed MSSQL connection (pool full)")
                else:
                    self.conn.close()
                    logger.info("⎄ Closed MSSQL connection")
            except Exception as e:
                logger.error(f"Error managing connection: {str(e)}")
                # Ensure connection is closed on error
                try:
                    self.conn.close()
                except Exception:
                    pass
            finally:
                self.conn = None
