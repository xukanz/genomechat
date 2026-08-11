import logging
from typing import Any, List, Optional, Tuple

import pandas as pd
import yaml
from dotenv import load_dotenv

from src.config.database import DatabaseSettings, DatabaseType
from src.config.paths import resolve_path
from src.service.database.connections.athena_connection import AthenaConnection
from src.service.database.connections.duckdb_connection import DuckDBConnection
from src.service.database.connections.mssql_connection import MSSQLConnection
from src.service.database.connections.mysql_connection import MySQLConnection
from src.service.database.connections.postgres_connection import PostgresConnection
from src.service.database.connections.sqlite_connection import SQLiteConnection
from src.service.database.database_connection import DatabaseConnection

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and provides a unified interface for query execution.

    Uses lazy connection initialization - the database connection is only
    established when a query is executed, not when the manager is created.
    This allows schema loading and other metadata operations without
    requiring a working database connection.
    """

    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self._conn: Optional[DatabaseConnection] = None

    @property
    def conn(self) -> DatabaseConnection:
        """Get the database connection, initializing lazily if needed.

        Returns:
            Active database connection

        Raises:
            ValueError: If database type is not supported
            Various connection errors depending on database type
        """
        if self._conn is None:
            self._conn = self._create_connection()
            self._conn.connect()
            logger.info(f"Database connection established: {self.settings.database_type.value}")

            # For DuckDB connections, create table views to map Parquet files to table names
            if self.settings.database_type == DatabaseType.DUCKDB:
                from src.service.database.connections.duckdb_connection import DuckDBConnection

                if isinstance(self._conn, DuckDBConnection):
                    self._conn.create_table_views()
        return self._conn

    def _create_connection(self) -> DatabaseConnection:
        """Create the appropriate database connection based on settings."""
        if self.settings.database_type == DatabaseType.SQLITE:
            return SQLiteConnection(self.settings)
        elif self.settings.database_type == DatabaseType.POSTGRES:
            return PostgresConnection(self.settings)
        elif self.settings.database_type == DatabaseType.ATHENA:
            return AthenaConnection(self.settings)
        elif self.settings.database_type == DatabaseType.MYSQL:
            return MySQLConnection(self.settings)
        elif self.settings.database_type == DatabaseType.MSSQL:
            return MSSQLConnection(self.settings)
        elif self.settings.database_type == DatabaseType.DUCKDB:
            return DuckDBConnection(self.settings)
        else:
            raise ValueError(f"Unsupported database type: {self.settings.database_type}")

    def is_connected(self) -> bool:
        """Check if a database connection has been established.

        Returns:
            True if connected, False otherwise
        """
        return self._conn is not None

    def execute_query(self, query: str) -> Tuple[List[str], List[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple."""
        try:
            return self.conn.execute_query(query)
        except Exception as e:
            logger.error(f"Failed to execute query: {str(e)}")
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
        try:
            import inspect

            # Pass timeout to connection if it supports it
            if hasattr(self.conn, "execute_query_df"):
                sig = inspect.signature(self.conn.execute_query_df)
                if "timeout" in sig.parameters:
                    return self.conn.execute_query_df(query, timeout=timeout)
                else:
                    return self.conn.execute_query_df(query)
            else:
                raise AttributeError("Connection does not support execute_query_df")
        except Exception as e:
            logger.error(f"Failed to execute query to DataFrame: {str(e)}")
            raise

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.close()
        return False

    def load_schema_description(self, allowed_tables: list[str] | None = None) -> str:
        """Loads and formats the schema description from YAML file.

        This method does NOT require a database connection - it only reads
        the schema YAML file from the filesystem.

        Args:
            allowed_tables: When set, only include these tables in the output.
                           Table names are matched case-insensitively.

        Returns:
            Formatted schema description string

        Raises:
            ValueError: If schema path not configured
            FileNotFoundError: If schema file not found
        """
        if not self.settings.database_schema_path:
            raise ValueError("Database schema path not configured in settings")

        # Use centralized path resolution
        schema_path = resolve_path(
            self.settings.database_schema_path,
            must_exist=True,
        )

        logger.info(f"Loading schema from: {schema_path}")

        # Read and parse schema
        with open(schema_path, "r") as f:
            schema_data = yaml.safe_load(f)

        # Format the schema description
        description = "Database Schema:\n\n"

        # Build allowed set for case-insensitive matching
        allowed_set = {t.lower() for t in allowed_tables} if allowed_tables else None

        # Add tables and their columns
        for table_name, table_info in schema_data["schema"]["tables"].items():
            if allowed_set and table_name.lower() not in allowed_set:
                continue
            table_description = table_info.get("description", "No description available.")
            description += f"Table: {table_name}\n"
            description += f"  Description: {table_description}\n"
            description += "  Columns:\n"
            for column in table_info["columns"]:
                col_name = column["name"]
                col_type = column["type"]
                col_desc = column.get("description", "No description.")
                constraints = f", {column['constraints']}" if "constraints" in column else ""
                description += f"    - {col_name} ({col_type}{constraints}): {col_desc}\n"
            description += "\n"

        return description
