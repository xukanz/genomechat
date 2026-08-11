"""Tests for database registry configuration."""

import pytest
from unittest.mock import patch

from src.config.database_registry import (
    DatabaseProfile,
    DatabaseProfileConfig,
    DatabaseRegistrySettings,
    DATABASE_PROFILES,
    get_active_profile,
    get_enabled_profiles,
    get_profile_by_name,
    list_available_profiles,
    get_registry_settings,
    get_schema_path_for_active_profile,
    get_context_file_for_active_profile,
)


@pytest.fixture(autouse=True)
def _isolate_registry_settings(monkeypatch):
    """Isolate these tests from cached state and from the developer's .env.

    Two things bite otherwise:

    - ``get_registry_settings`` is ``lru_cache``d, so the first test to read
      settings would pin them for the whole session.
    - ``DatabaseRegistrySettings`` lists ``dotenv_settings`` first in
      ``settings_customise_sources``, which gives the on-disk ``.env`` higher
      priority than the process environment. A test that patches
      ``os.environ`` would therefore be silently overridden by whatever the
      developer happens to have in ``backend/.env``. Detaching the env_file
      makes the env-override tests actually test something.
    """
    monkeypatch.setitem(DatabaseRegistrySettings.model_config, "env_file", None)
    get_registry_settings.cache_clear()
    yield
    get_registry_settings.cache_clear()


class TestDatabaseProfile:
    """Tests for DatabaseProfile enum."""

    def test_profile_values(self):
        assert DatabaseProfile.CLINVAR.value == "clinvar"
        assert DatabaseProfile.GWAS.value == "gwas"
        assert DatabaseProfile.ENSEMBL.value == "ensembl"

    def test_profile_count(self):
        assert len(DatabaseProfile) == 3

    def test_every_enum_member_has_a_config(self):
        assert set(DATABASE_PROFILES) == set(DatabaseProfile)


class TestDatabaseProfileConfig:
    """Tests for the individual profile definitions."""

    def test_clinvar_profile(self):
        p = DATABASE_PROFILES[DatabaseProfile.CLINVAR]
        assert p.name == "clinvar"
        assert p.database_type == "sqlite"
        assert p.sql_dialect == "sqlite"
        assert p.data_path.endswith("clinvar.db")
        assert p.context_file == "clinvar_context.md"

    def test_gwas_profile(self):
        p = DATABASE_PROFILES[DatabaseProfile.GWAS]
        assert p.name == "gwas"
        assert p.database_type == "duckdb"
        # DuckDB speaks PostgreSQL syntax; the agent is told so via this field.
        assert p.sql_dialect == "postgresql"
        assert p.parquet_glob_pattern == "*.parquet"
        assert p.supports_s3 is True

    def test_ensembl_profile(self):
        p = DATABASE_PROFILES[DatabaseProfile.ENSEMBL]
        assert p.name == "ensembl"
        assert p.database_type == "mysql"
        assert p.sql_dialect == "mysql"
        # host:port/database — parsed by DatabaseSettings.from_profile
        assert ":" in p.data_path and "/" in p.data_path

    def test_ensembl_whitelists_tables(self):
        """The Ensembl core schema is ~75 tables; only a subset is exposed."""
        p = DATABASE_PROFILES[DatabaseProfile.ENSEMBL]
        assert p.allowed_tables
        assert "gene" in p.allowed_tables
        assert "transcript" in p.allowed_tables
        assert len(p.allowed_tables) < 30

    def test_local_profiles_expose_all_tables(self):
        for profile in (DatabaseProfile.CLINVAR, DatabaseProfile.GWAS):
            assert DATABASE_PROFILES[profile].allowed_tables is None

    def test_all_profiles_have_example_questions(self):
        for profile, config in DATABASE_PROFILES.items():
            assert config.example_questions, f"{profile.value} has no example questions"

    def test_all_profiles_declare_a_domain(self):
        for config in DATABASE_PROFILES.values():
            assert config.domain


class TestDatabaseRegistrySettings:
    """Tests for DatabaseRegistrySettings."""

    def test_default_active_database(self):
        with patch.dict("os.environ", {}, clear=True):
            assert DatabaseRegistrySettings().active_database == DatabaseProfile.CLINVAR

    def test_env_override(self):
        with patch.dict("os.environ", {"DB_REGISTRY_ACTIVE_DATABASE": "gwas"}, clear=True):
            assert DatabaseRegistrySettings().active_database == DatabaseProfile.GWAS

    def test_invalid_profile_rejected(self):
        with patch.dict("os.environ", {"DB_REGISTRY_ACTIVE_DATABASE": "nope"}, clear=True):
            with pytest.raises(Exception):
                DatabaseRegistrySettings()


class TestGetActiveProfile:
    """Tests for get_active_profile()."""

    def test_default_returns_clinvar(self):
        with patch.dict("os.environ", {}, clear=True):
            get_registry_settings.cache_clear()
            assert get_active_profile().name == "clinvar"

    def test_gwas_profile_with_env(self):
        with patch.dict("os.environ", {"DB_REGISTRY_ACTIVE_DATABASE": "gwas"}, clear=True):
            get_registry_settings.cache_clear()
            p = get_active_profile()
            assert p.name == "gwas"
            assert p.database_type == "duckdb"


class TestGetProfileByName:
    """Tests for get_profile_by_name()."""

    def test_get_clinvar(self):
        assert get_profile_by_name("clinvar").name == "clinvar"

    def test_get_gwas(self):
        assert get_profile_by_name("gwas").name == "gwas"

    def test_case_insensitive(self):
        assert get_profile_by_name("ClinVar").name == "clinvar"

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError):
            get_profile_by_name("does_not_exist")


class TestListAvailableProfiles:
    """Tests for list_available_profiles()."""

    def test_returns_list(self):
        profiles = list_available_profiles()
        assert isinstance(profiles, list)
        assert profiles

    def test_profile_structure(self):
        for entry in list_available_profiles():
            for key in ("name", "display_name", "database_type", "description", "domain"):
                assert key in entry, f"{key} missing from {entry.get('name')}"


class TestPathOverrides:
    """Tests for the deployment path-override settings."""

    def test_clinvar_path_override(self):
        with patch.dict(
            "os.environ",
            {
                "DB_REGISTRY_ACTIVE_DATABASE": "clinvar",
                "DB_REGISTRY_CLINVAR_DATA_PATH_OVERRIDE": "/data/clinvar/clinvar.db",
            },
            clear=True,
        ):
            get_registry_settings.cache_clear()
            assert get_active_profile().data_path == "/data/clinvar/clinvar.db"

    def test_gwas_s3_path_takes_priority_over_local(self):
        with patch.dict(
            "os.environ",
            {
                "DB_REGISTRY_ACTIVE_DATABASE": "gwas",
                "DB_REGISTRY_GWAS_DATA_PATH_OVERRIDE": "/data/gwas",
                "DB_REGISTRY_GWAS_S3_PATH": "s3://bucket/gwas/",
            },
            clear=True,
        ):
            get_registry_settings.cache_clear()
            assert get_active_profile().data_path == "s3://bucket/gwas/"


class TestEnsemblOverrides:
    """Tests for the Ensembl connection settings."""

    def test_host_and_database_compose_data_path(self):
        with patch.dict(
            "os.environ",
            {
                "DB_REGISTRY_ACTIVE_DATABASE": "ensembl",
                "DB_REGISTRY_ENSEMBL_ENABLED": "true",
                "DB_REGISTRY_ENSEMBL_HOST": "mirror.internal",
                "DB_REGISTRY_ENSEMBL_PORT": "3307",
                "DB_REGISTRY_ENSEMBL_DATABASE": "homo_sapiens_core_999_38",
            },
            clear=True,
        ):
            get_registry_settings.cache_clear()
            assert get_active_profile().data_path == (
                "mirror.internal:3307/homo_sapiens_core_999_38"
            )

    def test_allowed_tables_override(self):
        with patch.dict(
            "os.environ",
            {
                "DB_REGISTRY_ACTIVE_DATABASE": "ensembl",
                "DB_REGISTRY_ENSEMBL_ENABLED": "true",
                "DB_REGISTRY_ENSEMBL_ALLOWED_TABLES": "gene, Transcript ,exon",
            },
            clear=True,
        ):
            get_registry_settings.cache_clear()
            # Whitespace trimmed and lowercased.
            assert get_active_profile().allowed_tables == ["gene", "transcript", "exon"]


class TestSchemaAndContextPaths:
    """Tests for schema / context resolution."""

    def test_get_schema_path(self):
        with patch.dict("os.environ", {"DB_REGISTRY_ACTIVE_DATABASE": "clinvar"}, clear=True):
            get_registry_settings.cache_clear()
            path = get_schema_path_for_active_profile()
            assert path.name == "schema_description.yaml"
            assert "clinvar" in str(path)

    def test_get_context_file(self):
        with patch.dict("os.environ", {"DB_REGISTRY_ACTIVE_DATABASE": "clinvar"}, clear=True):
            get_registry_settings.cache_clear()
            assert get_context_file_for_active_profile() == "clinvar_context.md"


class TestGetEnabledProfiles:
    """Tests for the Ensembl feature flag."""

    def test_ensembl_disabled_by_default(self):
        """Off by default: many networks block outbound MySQL protocol."""
        with patch.dict("os.environ", {}, clear=True):
            get_registry_settings.cache_clear()
            enabled = get_enabled_profiles()
            assert DatabaseProfile.ENSEMBL not in enabled
            assert DatabaseProfile.CLINVAR in enabled
            assert DatabaseProfile.GWAS in enabled

    def test_ensembl_enabled_when_flag_true(self):
        with patch.dict(
            "os.environ", {"DB_REGISTRY_ENSEMBL_ENABLED": "true"}, clear=True
        ):
            get_registry_settings.cache_clear()
            assert DatabaseProfile.ENSEMBL in get_enabled_profiles()

    def test_enabled_profiles_subset_of_all_profiles(self):
        assert set(get_enabled_profiles()).issubset(set(DATABASE_PROFILES))
