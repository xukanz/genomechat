"""Database configuration settings.

Defines DatabaseSettings and DatabaseType enum for database connection management.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.config.database_registry import DatabaseProfileConfig

from pydantic_settings import BaseSettings


class DatabaseType(str, Enum):
    """Supported database types."""

    POSTGRES = "postgres"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    ATHENA = "athena"
    BIGQUERY = "bigquery"
    MSSQL = "mssql"
    DUCKDB = "duckdb"


class DatabaseSettings(BaseSettings):
    """Database connection settings loaded from environment variables."""

    # Common settings
    database_type: DatabaseType = DatabaseType.SQLITE
    database_name: Optional[str] = None

    # Schema information
    database_schema_path: Optional[str] = None

    # AWS Athena specific
    s3_staging_dir: Optional[str] = None
    region_name: Optional[str] = None

    # SQL database specific
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    local: bool = False

    # SQLite specific
    sqlite_path: Optional[str] = "data/database.db"

    # DuckDB/Parquet specific
    duckdb_data_path: Optional[str] = None
    parquet_glob_pattern: Optional[str] = "**/*.parquet"
    hive_partitioning: bool = True

    # Vector database paths
    vector_db_path: str = "data/lancedb"
    query_examples_path: Optional[str] = None
    vector_table_name: str = "sql_query_pairs"

    model_config = {
        "validate_assignment": True,
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @classmethod
    def from_profile(
        cls,
        profile: "DatabaseProfileConfig",
    ) -> "DatabaseSettings":
        """Create DatabaseSettings from a DatabaseProfileConfig.

        Bridges the database registry to settings used by DatabaseManager.

        Args:
            profile: Active database profile from registry

        Returns:
            DatabaseSettings configured for the profile
        """
        # Resolve straight off the enum rather than a partial lookup table.
        # The previous map covered only three types and silently fell back to
        # SQLITE, so a profile declaring anything else built settings for the
        # wrong engine and failed much later, somewhere unrelated.
        try:
            db_type = DatabaseType(profile.database_type.lower())
        except ValueError as exc:
            raise ValueError(
                f"Profile {profile.name!r} declares unsupported database_type "
                f"{profile.database_type!r}. Valid types: "
                f"{[t.value for t in DatabaseType]}"
            ) from exc

        settings_dict = {
            "database_type": db_type,
            "database_name": profile.name,
            "database_schema_path": profile.schema_path,
        }

        if db_type == DatabaseType.SQLITE:
            settings_dict["sqlite_path"] = profile.data_path
        elif db_type == DatabaseType.DUCKDB:
            settings_dict["duckdb_data_path"] = profile.data_path
            settings_dict["parquet_glob_pattern"] = profile.parquet_glob_pattern
            settings_dict["hive_partitioning"] = profile.hive_partitioning

        return cls(**settings_dict)
