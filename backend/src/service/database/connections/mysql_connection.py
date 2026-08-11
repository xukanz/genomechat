import pandas as pd
import threading
from typing import List, Any, Tuple
import logging

logger = logging.getLogger(__name__)
from src.config.database import DatabaseSettings
from src.service.database.database_connection import DatabaseConnection

# Import mysql.connector with optional handling
try:
    import mysql.connector
    from mysql.connector import pooling

    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    mysql = None
    pooling = None


class MySQLConnection(DatabaseConnection):
    """MySQL connection with connection pooling support."""

    # Class-level connection pools (shared across instances with same settings)
    _pools: dict = {}
    _pools_lock = threading.Lock()

    def __init__(self, settings: DatabaseSettings):
        logger.info("⎄ Initializing MySQL connection")
        self.settings = settings
        self.conn = None
        self._pool_key = None

        if not MYSQL_AVAILABLE:
            logger.warning(
                "⎄ mysql-connector-python not available - MySQL connections will not work"
            )

    def _get_pool_key(self) -> str:
        """Generate a unique key for the connection pool based on settings."""
        return f"{self.settings.host}:{self.settings.port}:{self.settings.database_name}:{self.settings.username}"

    def _get_pool(self):
        """Get or create a connection pool for this database configuration."""
        if not MYSQL_AVAILABLE:
            raise ImportError(
                "mysql-connector-python is required for MySQL connections. Install with: pip install mysql-connector-python"
            )

        pool_key = self._get_pool_key()

        # Check if pool already exists
        if pool_key not in self._pools:
            with self._pools_lock:
                # Double-check after acquiring lock
                if pool_key not in self._pools:
                    try:
                        pool_config = {
                            "database": self.settings.database_name,
                            "user": self.settings.username,
                            "password": self.settings.password,
                            "host": self.settings.host,
                            "port": self.settings.port,
                            "pool_name": f"mysql_pool_{pool_key}",
                            "pool_size": 10,
                            "pool_reset_session": True,
                        }
                        connection_pool = pooling.MySQLConnectionPool(**pool_config)
                        self._pools[pool_key] = connection_pool
                        logger.info(
                            f"⎄ Created MySQL connection pool for {self.settings.host}:{self.settings.port}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to create MySQL connection pool: {str(e)}")
                        raise

        self._pool_key = pool_key
        return self._pools[pool_key]

    def connect(self):
        """Get a connection from the pool."""
        if not MYSQL_AVAILABLE:
            raise ImportError(
                "mysql-connector-python is required for MySQL connections. Install with: pip install mysql-connector-python"
            )

        if self.conn is None:
            connection_pool = self._get_pool()
            try:
                self.conn = connection_pool.get_connection()
                logger.info("⎄ Obtained MySQL connection from pool")
            except Exception as e:
                logger.error(f"Failed to get connection from pool: {str(e)}")
                raise

        return self.conn

    def execute_query(self, query: str) -> Tuple[List[str], List[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple."""
        if not MYSQL_AVAILABLE:
            raise ImportError("mysql-connector-python is required for MySQL connections")

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
            logger.error(f"Failed to execute MySQL query: {str(e)}")
            raise

    def execute_query_df(self, query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame."""
        if not MYSQL_AVAILABLE:
            raise ImportError("mysql-connector-python is required for MySQL connections")

        if self.conn is None:
            self.connect()

        try:
            return pd.read_sql_query(query, self.conn)
        except Exception as e:
            logger.error(f"Failed to execute MySQL query to DataFrame: {str(e)}")
            raise

    def close(self) -> None:
        """Return the connection to the pool."""
        if self.conn is not None:
            try:
                self.conn.close()
                logger.info("⎄ Returned MySQL connection to pool")
            except Exception as e:
                logger.error(f"Error returning connection to pool: {str(e)}")
            finally:
                self.conn = None
