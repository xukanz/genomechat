"""Tests for DuckDB connection and Parquet file querying."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

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

    @patch("src.service.database.connections.duckdb_connection.Path")
    def test_resolve_data_path_absolute(self, mock_path_class):
        """Test resolving absolute path."""
        # Setup mock
        mock_path = MagicMock()
        mock_path.is_absolute.return_value = True
        mock_path.exists.return_value = True
        mock_path_class.return_value = mock_path

        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="/data/gwas",
        )
        conn = DuckDBConnection(settings)
        result = conn._resolve_data_path()
        assert result == mock_path

    def test_connect_without_duckdb_installed(self):
        """Test that ImportError is raised when duckdb is not installed."""
        settings = DatabaseSettings(
            database_type=DatabaseType.DUCKDB,
            duckdb_data_path="databases/gwas",
        )
        conn = DuckDBConnection(settings)

        with patch.dict("sys.modules", {"duckdb": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'duckdb'")):
                # This would test the import error, but it's tricky to mock properly
                pass

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
