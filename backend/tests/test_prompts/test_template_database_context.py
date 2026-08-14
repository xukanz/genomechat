"""Tests for prompt template processing with database context."""

from unittest.mock import patch, MagicMock

from src.prompts.template import (
    get_database_context_vars,
    get_processed_prompt_with_database_context,
    _get_sql_dialect_notes,
)


class TestGetDatabaseContextVars:
    """Tests for get_database_context_vars function."""

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = MagicMock(
                name="clinvar",
                display_name="ClinVar",
                database_type="sqlite",
                description="Test description",
                sql_dialect="sqlite",
            )
            result = get_database_context_vars()
            assert isinstance(result, dict)

    def test_contains_required_keys(self):
        """Test that result contains all required keys."""
        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = MagicMock(
                name="clinvar",
                display_name="ClinVar",
                database_type="sqlite",
                description="Test description",
                sql_dialect="sqlite",
            )
            result = get_database_context_vars()

            required_keys = [
                "DATABASE_NAME",
                "DATABASE_DISPLAY_NAME",
                "DATABASE_TYPE",
                "DATABASE_DESCRIPTION",
                "SQL_DIALECT",
                "SQL_DIALECT_NOTES",
            ]
            for key in required_keys:
                assert key in result, f"Missing key: {key}"

    def test_clinvar_context(self):
        """Test context for the ClinVar profile."""
        from src.config.database_registry import DatabaseProfileConfig

        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = DatabaseProfileConfig(
                name="clinvar",
                display_name="ClinVar",
                database_type="sqlite",
                data_path="databases/clinvar/clinvar.db",
                schema_path="databases/clinvar/schema_description.yaml",
                context_file="clinvar_context.md",
                sql_dialect="sqlite",
                description="ClinVar database description",
            )
            result = get_database_context_vars()

            assert result["DATABASE_NAME"] == "clinvar"
            assert result["DATABASE_DISPLAY_NAME"] == "ClinVar"
            assert result["DATABASE_TYPE"] == "sqlite"
            assert result["SQL_DIALECT"] == "SQLite"
            assert "SQLite SQL Notes" in result["SQL_DIALECT_NOTES"]

    def test_duckdb_context(self):
        """Test context for a DuckDB/Parquet profile."""
        from src.config.database_registry import DatabaseProfileConfig

        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = DatabaseProfileConfig(
                name="gwas",
                display_name="GWAS Catalog",
                database_type="duckdb",
                data_path="databases/gwas",
                schema_path="databases/gwas/schema_description.yaml",
                context_file="gwas_context.md",
                sql_dialect="postgresql",
                description="GWAS Catalog description",
            )
            result = get_database_context_vars()

            assert result["DATABASE_NAME"] == "gwas"
            assert result["DATABASE_DISPLAY_NAME"] == "GWAS Catalog"
            assert result["DATABASE_TYPE"] == "duckdb"
            assert result["SQL_DIALECT"] == "PostgreSQL"
            assert "PostgreSQL" in result["SQL_DIALECT_NOTES"]

    def test_fallback_on_error(self):
        """Test that defaults are returned on error."""
        with patch(
            "src.config.database_registry.get_active_profile", side_effect=Exception("Test error")
        ):
            result = get_database_context_vars()

            assert result["DATABASE_NAME"] == "clinvar"
            assert result["DATABASE_DISPLAY_NAME"] == "ClinVar"


class TestGetSqlDialectNotes:
    """Tests for _get_sql_dialect_notes function."""

    def test_sqlite_notes(self):
        """Test SQLite dialect notes."""
        notes = _get_sql_dialect_notes("sqlite")
        assert "SQLite SQL Notes" in notes
        assert "SUBSTR" in notes
        assert "GROUP_CONCAT" in notes

    def test_postgresql_notes(self):
        """Test PostgreSQL dialect notes."""
        notes = _get_sql_dialect_notes("postgresql")
        assert "PostgreSQL" in notes
        assert "DISTINCT ON" in notes
        assert "ARRAY_AGG" in notes

    def test_unknown_dialect(self):
        """Test unknown dialect returns empty string."""
        notes = _get_sql_dialect_notes("unknown")
        assert notes == ""


class TestGetProcessedPromptWithDatabaseContext:
    """Tests for get_processed_prompt_with_database_context function."""

    def test_injects_database_context(self):
        """Test that database context is injected into prompts."""
        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = MagicMock(
                name="clinvar",
                display_name="ClinVar",
                database_type="sqlite",
                description="Test description",
                sql_dialect="sqlite",
            )

            with patch("src.prompts.template.get_prompt_template") as mock_template:
                mock_template.return_value = "Database: <<DATABASE_DISPLAY_NAME>>"

                result = get_processed_prompt_with_database_context("test_prompt")
                assert "ClinVar" in result

    def test_merges_with_custom_vars(self):
        """Test that custom vars are merged with database context."""
        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = MagicMock(
                name="clinvar",
                display_name="ClinVar",
                database_type="sqlite",
                description="Test description",
                sql_dialect="sqlite",
            )

            with patch("src.prompts.template.get_prompt_template") as mock_template:
                mock_template.return_value = "<<DATABASE_NAME>> and <<CUSTOM_VAR>>"

                result = get_processed_prompt_with_database_context(
                    "test_prompt",
                    template_vars={"CUSTOM_VAR": "custom_value"},
                )
                assert "clinvar" in result
                assert "custom_value" in result

    def test_custom_vars_override_database_context(self):
        """Test that custom vars can override database context."""
        with patch("src.config.database_registry.get_active_profile") as mock_profile:
            mock_profile.return_value = MagicMock(
                name="clinvar",
                display_name="ClinVar",
                database_type="sqlite",
                description="Test description",
                sql_dialect="sqlite",
            )

            with patch("src.prompts.template.get_prompt_template") as mock_template:
                mock_template.return_value = "Database: <<DATABASE_DISPLAY_NAME>>"

                result = get_processed_prompt_with_database_context(
                    "test_prompt",
                    template_vars={"DATABASE_DISPLAY_NAME": "Custom DB"},
                )
                assert "Custom DB" in result
                assert "ClinVar" not in result
