"""Tests for DuckDB connection and Parquet file querying."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.config.database import DatabaseSettings, DatabaseType
from src.service.database.connections.duckdb_connection import DuckDBConnection


class TestDuckDBConnection:
    """Tests for DuckDBConnection class."""

    def test_init(self):
        """Test DuckDBConnection initialization."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
            parquet_glob_pattern="**/*.parquet",
            hive_partitioning=True,
        )
        conn = DuckDBConnection(settings)
        assert conn.settings == settings
        assert conn.conn is None
        assert conn.data_path is None

    def test_resolve_data_path_not_set(self):
        """Test that ValueError is raised when duckdb_data_path is not set."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path=None,
        )
        conn = DuckDBConnection(settings)
        with pytest.raises(ValueError, match="DuckDB data path not specified"):
            conn._resolve_data_path()

    @patch("src.service.database.connections.duckdb_connection.resolve_data_path")
    def test_resolve_data_path_local(self, mock_resolve):
        """Local paths are delegated to the centralized resolver and stringified."""
        mock_resolve.return_value = Path("/data/gwas")

        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="/data/gwas",
        )
        conn = DuckDBConnection(settings)
        result = conn._resolve_data_path()

        assert result == "/data/gwas"
        assert conn._is_s3 is False
        mock_resolve.assert_called_once_with("/data/gwas")

    def test_resolve_data_path_s3_bypasses_filesystem(self):
        """S3 paths are returned as-is (no local existence check) and flag _is_s3."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="s3://my-bucket/gwas/",
        )
        conn = DuckDBConnection(settings)

        assert conn._resolve_data_path() == "s3://my-bucket/gwas"
        assert conn._is_s3 is True

    def test_connect_without_duckdb_installed(self):
        """Test that ImportError is raised when duckdb is not installed."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
        )
        conn = DuckDBConnection(settings)

        # A None entry in sys.modules makes `import duckdb` raise ImportError,
        # which is what connect() is expected to re-raise with install guidance.
        with patch.dict("sys.modules", {"duckdb": None}):
            with pytest.raises(ImportError, match="duckdb"):
                conn.connect()

    def test_execute_query_without_connection(self):
        """Test that RuntimeError is raised when executing without connection."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
        )
        conn = DuckDBConnection(settings)
        with pytest.raises(RuntimeError, match="Connection not established"):
            conn.execute_query("SELECT 1")

    def test_execute_query_df_without_connection(self):
        """Test that RuntimeError is raised when executing df without connection."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
        )
        conn = DuckDBConnection(settings)
        with pytest.raises(RuntimeError, match="Connection not established"):
            conn.execute_query_df("SELECT 1")

    @patch("duckdb.connect")
    def test_connect_creates_in_memory_connection(self, mock_duckdb_connect):
        """Test that connect creates an in-memory DuckDB connection."""
        # Setup mocks
        mock_conn = MagicMock()
        mock_duckdb_connect.return_value = mock_conn

        # Create a temp directory for the test
        with patch.object(DuckDBConnection, "_resolve_data_path") as mock_resolve:
            mock_resolve.return_value = Path("/data/test")

            settings = DatabaseSettings(
                database_type=DatabaseType.DUCKDB,
                duckdb_data_path="/data/test",
            )
            conn = DuckDBConnection(settings)
            result = conn.connect()

            mock_duckdb_connect.assert_called_once_with(
                ":memory:",
                config={"threads": 4, "memory_limit": "4GB"},
            )
            assert result == mock_conn
            assert conn.conn == mock_conn

    def test_build_parquet_query(self):
        """Test building parquet query path."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="/data/gwas",
            parquet_glob_pattern="**/*.parquet",
            hive_partitioning=True,
        )
        conn = DuckDBConnection(settings)
        conn.data_path = Path("/data/gwas")

        result = conn._build_parquet_query("clonotype_data")
        assert "clonotype_data" in result
        assert "read_parquet" in result
        assert "hive_partitioning=true" in result

    def test_close(self):
        """Test closing the connection."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
        )
        conn = DuckDBConnection(settings)
        mock_conn = MagicMock()
        conn.conn = mock_conn

        conn.close()

        mock_conn.close.assert_called_once()
        assert conn.conn is None

    def test_close_when_not_connected(self):
        """Test closing when not connected (should not raise)."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
        )
        conn = DuckDBConnection(settings)
        conn.close()  # Should not raise


class TestDuckDBConnectionIntegration:
    """Integration tests for DuckDB connection (require duckdb package)."""

    @pytest.fixture
    def mock_settings(self, tmp_path):
        """Create settings with a temporary directory."""
        return DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path=str(tmp_path),
            parquet_glob_pattern="**/*.parquet",
            hive_partitioning=True,
        )

    def test_execute_simple_query(self, mock_settings, tmp_path):
        """Test executing a simple query."""
        import duckdb

        conn = DuckDBConnection(mock_settings)
        conn.conn = duckdb.connect(":memory:")
        conn.data_path = tmp_path

        columns, rows = conn.execute_query("SELECT 1 as value, 'test' as name")

        assert columns == ["value", "name"]
        assert rows == [(1, "test")]

        conn.close()

    def test_execute_query_df(self, mock_settings, tmp_path):
        """Test executing query and returning DataFrame."""
        import duckdb
        import pandas as pd

        conn = DuckDBConnection(mock_settings)
        conn.conn = duckdb.connect(":memory:")
        conn.data_path = tmp_path

        df = conn.execute_query_df("SELECT 1 as value, 'test' as name")

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["value", "name"]
        assert len(df) == 1
        assert df.iloc[0]["value"] == 1
        assert df.iloc[0]["name"] == "test"

        conn.close()


class TestFlatParquetLayout:
    """Plain `<table>.parquet` files in the data directory.

    This is how the genomics profiles are built. Before flat discovery existed
    no views were created for them, so the bare table names the schema
    description advertises — and that `get_random_subsamples` emits — failed
    with a catalog error while the data sat right there on disk.
    """

    @pytest.fixture
    def flat_dir(self, tmp_path):
        import duckdb

        con = duckdb.connect()
        for name, n in (("genes", 3), ("exons", 5)):
            con.execute(
                f"COPY (SELECT * FROM range({n}) t(id)) "
                f"TO '{tmp_path / f'{name}.parquet'}' (FORMAT PARQUET)"
            )
        con.close()
        return tmp_path

    def _conn(self, data_path):
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path=str(data_path),
            parquet_glob_pattern="*.parquet",
            hive_partitioning=False,
        )
        conn = DuckDBConnection(settings)
        conn.data_path = str(data_path)
        return conn

    def test_discovers_flat_tables(self, flat_dir):
        assert self._conn(flat_dir)._get_local_tables() == ["exons", "genes"]

    def test_pattern_points_at_the_file(self, flat_dir):
        pattern = self._conn(flat_dir)._get_local_parquet_pattern("genes")
        assert pattern.endswith("genes.parquet")

    def test_views_make_bare_table_names_queryable(self, flat_dir):
        import duckdb

        conn = self._conn(flat_dir)
        conn.conn = duckdb.connect(":memory:")
        conn.create_table_views()

        # The whole point: no path, no read_parquet, just the table name.
        assert conn.conn.execute("SELECT count(*) FROM genes").fetchone()[0] == 3
        assert conn.conn.execute("SELECT count(*) FROM exons").fetchone()[0] == 5
        conn.close()

    def test_missing_directory_returns_no_tables(self, tmp_path):
        # Previously raised FileNotFoundError out of iterdir().
        assert self._conn(tmp_path / "does_not_exist")._get_local_tables() == []

    def test_empty_directory_returns_no_tables(self, tmp_path):
        assert self._conn(tmp_path)._get_local_tables() == []

    def test_create_views_raises_when_nothing_is_built(self, tmp_path):
        """An unbuilt profile must fail loudly, not connect with zero tables.

        The data directory normally exists even when unbuilt because it holds
        schema_description.yaml, so path resolution cannot catch this.
        """
        import duckdb

        conn = self._conn(tmp_path)
        conn.conn = duckdb.connect(":memory:")
        with pytest.raises(FileNotFoundError, match="build_genomics_databases"):
            conn.create_table_views()
        conn.close()
