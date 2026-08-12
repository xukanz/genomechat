"""DuckDB connection for querying Parquet files.

Provides a DuckDB-based connection for querying partitioned Parquet files,
supporting hive-style partitioning and glob patterns for efficient data access.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.config.database import DatabaseSettings
from src.config.paths import is_s3_path, resolve_data_path
from src.service.database.database_connection import DatabaseConnection

logger = logging.getLogger(__name__)


class DuckDBConnection(DatabaseConnection):
    """DuckDB connection for querying Parquet files.

    Supports:
    - In-memory DuckDB for Parquet querying
    - Hive-style partitioned Parquet directories
    - Glob patterns for multi-file queries
    - S3 paths (with httpfs extension - future support)
    """

    def __init__(self, settings: DatabaseSettings):
        """Initialize DuckDB connection.

        Args:
            settings: Database settings containing duckdb_data_path and parquet options
        """
        logger.info("⎄ Initializing DuckDB connection")
        self.settings = settings
        self.conn: Optional[Any] = None  # duckdb.DuckDBPyConnection
        self.data_path: Optional[str] = None  # String to support both S3 and local paths
        self._is_s3: bool = False

    def _resolve_data_path(self) -> str:
        """Resolve Parquet data directory path from settings.

        Uses centralized path resolution for consistent behavior across
        local development, Docker, and Kubernetes deployments.

        Returns:
            Resolved path string (S3 URL or local path)

        Raises:
            FileNotFoundError: If path cannot be resolved (for local paths)
            ValueError: If duckdb_data_path is not set
        """
        if not self.settings.duckdb_data_path:
            raise ValueError(
                "DuckDB data path not specified. "
                "Set duckdb_data_path in database settings or use DB_REGISTRY_GWAS_DATA_PATH_OVERRIDE."
            )

        data_path = self.settings.duckdb_data_path

        # Handle S3 paths (return as-is, DuckDB will use httpfs extension)
        if is_s3_path(data_path):
            logger.info(f"Using S3 path for DuckDB: {data_path}")
            self._is_s3 = True
            return data_path.rstrip("/")

        # Use centralized path resolution for local paths
        resolved = resolve_data_path(data_path)
        logger.info(f"DuckDB data path resolved: {resolved}")
        return str(resolved)

    def connect(self) -> Any:
        """Initialize DuckDB in-memory connection for Parquet querying.

        Returns:
            DuckDB connection object

        Raises:
            ImportError: If duckdb is not installed
            FileNotFoundError: If data path cannot be resolved
        """
        try:
            import duckdb
        except ImportError as e:
            raise ImportError(
                "DuckDB is required for Parquet queries. Install with: uv add duckdb"
            ) from e

        logger.info("⎄ Connecting to DuckDB (in-memory)")

        # Resolve data path
        self.data_path = self._resolve_data_path()

        # Create in-memory connection with optimized settings
        self.conn = duckdb.connect(
            ":memory:",
            config={
                "threads": 4,
                "memory_limit": "4GB",
            },
        )

        # Configure S3 access if using S3 path
        if self._is_s3:
            self._configure_s3_access()

        logger.info(f"⎄ DuckDB connected. Data path: {self.data_path}")
        return self.conn

    def _configure_s3_access(self) -> None:
        """Configure DuckDB httpfs extension for S3 access.

        Installs and loads the httpfs extension, then configures AWS credentials
        from Settings (which supports Vault Secrets).
        """
        if self.conn is None:
            return

        logger.info("⎄ Configuring DuckDB httpfs extension for S3 access")

        # Install and load httpfs extension
        self.conn.execute("INSTALL httpfs;")
        self.conn.execute("LOAD httpfs;")

        # Get AWS credentials from Settings (supports Vault Secrets)
        aws_access_key, aws_secret_key, aws_region, aws_session_token = self._get_aws_credentials()

        if aws_access_key and aws_secret_key:
            self.conn.execute(f"SET s3_access_key_id='{aws_access_key}';")
            self.conn.execute(f"SET s3_secret_access_key='{aws_secret_key}';")
            self.conn.execute(f"SET s3_region='{aws_region}';")
            if aws_session_token:
                self.conn.execute(f"SET s3_session_token='{aws_session_token}';")
            logger.info(f"⎄ S3 credentials configured for region: {aws_region}")
        else:
            # Fall back to credential chain (IAM role, etc.)
            logger.warning(
                "⎄ No explicit AWS credentials found, "
                "attempting to use default credential chain (IAM role)"
            )

    def _get_aws_credentials(self) -> tuple[Optional[str], Optional[str], str, Optional[str]]:
        """Get AWS credentials from Settings (with Vault Secrets support).

        Settings object loads from environment variables AND Vault Secrets,
        with Vault Secrets taking priority.

        Returns:
            Tuple of (access_key, secret_key, region, session_token)
        """
        # Import here to avoid circular dependency
        from src.config.settings import settings

        # Get from Settings (supports Vault Secrets)
        aws_access_key = settings.aws_access_key_id
        aws_secret_key = settings.aws_secret_access_key
        aws_region = settings.aws_default_region or "eu-central-1"
        aws_session_token = settings.aws_session_token

        # Log credential source (without exposing values)
        logger.info(
            f"⎄ AWS credentials from Settings: access_key={'SET' if aws_access_key else 'NOT SET'}, secret_key={'SET' if aws_secret_key else 'NOT SET'}"
        )

        # Fall back to environment variables if Settings doesn't have them
        if not aws_access_key:
            aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
            if aws_access_key:
                logger.info("⎄ AWS access_key loaded from environment variable")
        if not aws_secret_key:
            aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            if aws_secret_key:
                logger.info("⎄ AWS secret_key loaded from environment variable")
        if not aws_session_token:
            aws_session_token = os.getenv("AWS_SESSION_TOKEN")

        return aws_access_key, aws_secret_key, aws_region, aws_session_token

    def _build_parquet_query(self, table_name: str) -> str:
        """Build read_parquet query for a specific table.

        Constructs a DuckDB read_parquet call with glob pattern and
        hive partitioning support.

        Args:
            table_name: Name of the table subdirectory (e.g., 'clonotype_data')

        Returns:
            read_parquet SQL expression
        """
        if self.data_path is None:
            raise RuntimeError("Connection not established. Call connect() first.")

        hive_partitioning = self.settings.hive_partitioning

        # S3 paths require explicit glob patterns (no ** support)
        if self._is_s3:
            parquet_path = self._get_s3_parquet_pattern(table_name)
        else:
            # Local paths - use table-specific patterns
            parquet_path = self._get_local_parquet_pattern(table_name)

        return f"read_parquet('{parquet_path}', hive_partitioning={str(hive_partitioning).lower()})"

    def _get_local_parquet_pattern(self, table_name: str) -> str:
        """Get the local glob pattern for a specific table.

        Handles different directory structures:
        - Partition-first: data_path/cohort_type=*/table_name/**/*.parquet
        - Enriched (sample_metrics_enriched): data_path/table_name/cohort_type=*/*.parquet
        - Enriched (clonotype_data, gene_usage): data_path/table_name/cohort_type=*/dataset_name=*/*.parquet (via symlinks)
        - Enriched (cohort_summary): data_path/table_name/*.parquet (not partitioned)
        - Flat: data_path/table_name.parquet

        Args:
            table_name: Name of the table

        Returns:
            Local glob pattern with ** support
        """
        local_path = Path(self.data_path)

        # Flat layout, checked first but gated on the file actually being
        # there, so the partitioned patterns below stay reachable.
        flat = local_path / f"{table_name}.parquet"
        if flat.exists():
            return str(flat)

        # Table-specific patterns for enriched database
        enriched_patterns = {
            "sample_metrics_enriched": str(local_path / table_name / "cohort_type=*" / "*.parquet"),
            "clonotype_data": str(
                local_path / table_name / "cohort_type=*" / "dataset_name=*" / "*.parquet"
            ),
            "gene_usage": str(
                local_path
                / table_name
                / "cohort_type=*"
                / "dataset_name=*"
                / "chain_type=*"
                / "*.parquet"
            ),
            "cohort_summary": str(local_path / table_name / "*.parquet"),
        }

        # Check if this is an enriched database table
        if table_name in enriched_patterns:
            return enriched_patterns[table_name]

        # Default pattern for the partition-first structure
        # data_path/cohort_type=*/table_name/**/*.parquet
        glob_pattern = self.settings.parquet_glob_pattern or "**/*.parquet"
        return str(local_path / "cohort_type=*" / table_name / glob_pattern)

    def _is_enriched_path(self) -> bool:
        """Check if the data path points to the enriched database.

        Detects based on the path segment name — table-first ("enriched")
        data lives under a path containing 'enriched'.

        Returns:
            True if this is an enriched database path
        """
        if self.data_path is None:
            return False
        return "enriched" in str(self.data_path)

    def _get_s3_parquet_pattern(self, table_name: str) -> str:
        """Get the S3 glob pattern for a specific table.

        Handles two database layouts (S3 doesn't support ** glob):

        Partition-first (cohort-first):
        - sample_metrics:  cohort_type=X/sample_metrics/cohort_type=Y/dataset_name=Z/*.parquet
        - clonotype_data:  cohort_type=X/clonotype_data/cohort_type=Y/dataset_name=Z/*.parquet
        - gene_usage:      cohort_type=X/gene_usage/cohort_type=Y/dataset_name=Z/chain_type=W/*.parquet
        - cohort_metrics:  cohort_type=X/cohort_metrics/*.parquet

        Enriched (table-first, mirrors local enriched structure):
        - sample_metrics_enriched: sample_metrics_enriched/cohort_type=*/*.parquet
        - clonotype_data:           clonotype_data/cohort_type=*/dataset_name=*/*.parquet
        - gene_usage:               gene_usage/cohort_type=*/dataset_name=*/chain_type=*/*.parquet
        - cohort_summary:           cohort_summary/*.parquet

        Args:
            table_name: Name of the table

        Returns:
            S3-compatible glob pattern (no ** wildcards)
        """
        base = self.data_path

        if self._is_enriched_path():
            enriched_patterns = {
                "sample_metrics_enriched": f"{base}/sample_metrics_enriched/cohort_type=*/*.parquet",
                "clonotype_data": f"{base}/clonotype_data/cohort_type=*/dataset_name=*/*.parquet",
                "gene_usage": f"{base}/gene_usage/cohort_type=*/dataset_name=*/chain_type=*/*.parquet",
                "cohort_summary": f"{base}/cohort_summary/*.parquet",
            }
            return enriched_patterns.get(table_name, f"{base}/{table_name}/*/*.parquet")

        # Partition-first (cohort-first) layout
        original_patterns = {
            "cohort_metrics": f"{base}/cohort_type=*/cohort_metrics/*.parquet",
            "gene_usage": f"{base}/cohort_type=*/gene_usage/cohort_type=*/dataset_name=*/chain_type=*/*.parquet",
            "sample_metrics": f"{base}/cohort_type=*/sample_metrics/cohort_type=*/dataset_name=*/*.parquet",
            "clonotype_data": f"{base}/cohort_type=*/clonotype_data/cohort_type=*/dataset_name=*/*.parquet",
        }
        return original_patterns.get(table_name, f"{base}/cohort_type=*/{table_name}/*/*.parquet")

    def get_available_tables(self) -> list[str]:
        """Discover available tables from Parquet directory structure.

        Scans the data path for subdirectories that contain Parquet files.
        Supports both local paths and S3 paths.

        Returns:
            List of table names available for querying
        """
        if self.data_path is None:
            raise RuntimeError("Connection not established. Call connect() first.")

        # For S3 paths, use known table names
        if self._is_s3:
            return self._get_s3_tables()

        # For local paths, scan directory structure
        return self._get_local_tables()

    def _get_local_tables(self) -> list[str]:
        """Discover tables from local Parquet directory structure.

        Handles three patterns:
        1. Partition-first: data_path/cohort_type=*/table_name/**/*.parquet
        2. Enriched: data_path/table_name/cohort_type=*/*.parquet
        3. Flat: data_path/table_name.parquet — the layout the genomics
           profiles (gwas, ensembl) are built into.

        Without (3) no views are created for a flat profile, so the bare table
        names the schema description advertises cannot be resolved and
        ``SELECT ... FROM associations`` fails with a catalog error.
        """
        if self.data_path is None:
            return []

        local_path = Path(self.data_path)
        if not local_path.is_dir():
            # An unbuilt or misconfigured profile: report no tables rather than
            # letting iterdir() raise FileNotFoundError.
            logger.warning("⎄ Data path is not a directory: %s", local_path)
            return []

        tables = set()

        # Check if this is the enriched database (contains known enriched tables)
        enriched_tables = {
            "sample_metrics_enriched",
            "clonotype_data",
            "gene_usage",
            "cohort_summary",
        }
        is_enriched = any((local_path / table).exists() for table in enriched_tables)

        if is_enriched:
            # For enriched database, return all tables that exist (including symlinked ones)
            logger.info("⎄ Detected enriched database structure")
            for table in enriched_tables:
                if (local_path / table).exists():
                    tables.add(table)
                    logger.info(f"⎄ Discovered enriched table: {table}")
            return sorted(tables)

        # Pattern 1: partition-first (tables under partition directories)
        # Scan for table directories under partition directories
        for partition_dir in local_path.iterdir():
            if partition_dir.is_dir() and "=" in partition_dir.name:
                # This is a partition directory (e.g., cohort_type=ControlGroups)
                for table_dir in partition_dir.iterdir():
                    if table_dir.is_dir():
                        # Check if it contains Parquet files
                        parquet_files = list(table_dir.glob("**/*.parquet"))
                        if parquet_files:
                            tables.add(table_dir.name)

        # Pattern 3: flat — plain <table>.parquet files in the data directory.
        # Only consulted when the partition scan found nothing, so partitioned
        # and enriched layouts behave exactly as before.
        if not tables:
            tables = {p.stem for p in local_path.glob("*.parquet")}
            if tables:
                logger.info("⎄ Discovered %d flat Parquet table(s)", len(tables))

        return sorted(tables)

    def _get_s3_tables(self) -> list[str]:
        """Discover tables from S3 Parquet directory structure.

        Uses boto3 to list files in S3 and extract table names, since DuckDB's
        glob function has limited S3 support.
        """
        if self.conn is None or self.data_path is None:
            return []

        s3_path = str(self.data_path).rstrip("/")

        # Use known table names from the active schema (more reliable than S3 discovery)
        # Enriched database uses table-first layout with different table names
        if self._is_enriched_path():
            known_tables = {
                "sample_metrics_enriched",
                "clonotype_data",
                "gene_usage",
                "cohort_summary",
            }
        else:
            known_tables = {"clonotype_data", "sample_metrics", "gene_usage", "cohort_metrics"}

        # Try to verify at least one table exists via S3
        try:
            import boto3

            # Parse S3 path: s3://bucket/prefix
            path_parts = s3_path.replace("s3://", "").split("/", 1)
            bucket = path_parts[0]
            prefix = path_parts[1] if len(path_parts) > 1 else ""

            # Get credentials from Settings (supports Vault Secrets)
            aws_access_key, aws_secret_key, aws_region, aws_session_token = (
                self._get_aws_credentials()
            )

            s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                aws_session_token=aws_session_token,
                region_name=aws_region,
            )

            # Quick check: list first few files to confirm data exists
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/", MaxKeys=5)
            if response.get("KeyCount", 0) > 0:
                logger.info(f"⎄ Confirmed S3 data exists. Using tables: {sorted(known_tables)}")
            else:
                logger.warning(f"⎄ No files found in S3 path: {s3_path}")

        except Exception as e:
            logger.warning(f"Failed to verify S3 tables: {e}")

        return sorted(known_tables)

    def execute_query(self, query: str) -> tuple[list[str], list[Any]]:
        """Execute a SQL query and return results as (columns, data) tuple.

        Args:
            query: SQL query string to execute

        Returns:
            Tuple of (column_names, rows)

        Raises:
            RuntimeError: If connection not established
        """
        if self.conn is None:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            result = self.conn.execute(query)
            columns = [desc[0] for desc in result.description] if result.description else []
            rows = result.fetchall()
            return columns, rows
        except Exception as e:
            logger.error(f"Failed to execute DuckDB query: {e}")
            raise

    def execute_query_df(self, query: str, timeout: float = 300.0) -> pd.DataFrame:
        """Execute a SQL query and return results as a pandas DataFrame.

        Args:
            query: SQL query string to execute
            timeout: Maximum execution time in seconds (not enforced for DuckDB)

        Returns:
            pandas DataFrame with query results

        Raises:
            RuntimeError: If connection not established
        """
        if self.conn is None:
            raise RuntimeError("Connection not established. Call connect() first.")

        try:
            # DuckDB has native pandas integration
            result = self.conn.execute(query).fetchdf()
            logger.debug(f"DuckDB query returned {len(result)} rows")
            return result
        except Exception as e:
            logger.error(f"Failed to execute DuckDB query to DataFrame: {e}")
            raise

    def create_table_views(self) -> None:
        """Create views for all discovered Parquet tables.

        This allows SQL queries to reference tables by name instead of
        using read_parquet() directly.
        """
        if self.conn is None:
            raise RuntimeError("Connection not established. Call connect() first.")

        tables = self.get_available_tables()
        if not tables and not self._is_s3:
            # Surface an unbuilt profile here rather than letting the agent
            # discover it as a catalog error on its first query. The directory
            # itself usually exists (it holds schema_description.yaml), so
            # path resolution alone cannot catch this.
            raise FileNotFoundError(
                f"No Parquet tables found under {self.data_path}. Build the "
                f"dataset first: uv run python "
                f"scripts/build_genomics_databases.py --download"
            )

        for table_name in tables:
            parquet_expr = self._build_parquet_query(table_name)
            view_sql = f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM {parquet_expr}"
            try:
                self.conn.execute(view_sql)
                logger.info(f"⎄ Created view: {table_name}")
            except Exception as e:
                logger.warning(f"Failed to create view for {table_name}: {e}")

    def close(self) -> None:
        """Close the DuckDB connection."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None
            logger.info("⎄ DuckDB connection closed")
