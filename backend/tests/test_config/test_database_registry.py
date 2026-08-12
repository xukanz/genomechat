"""Tests for database registry configuration."""

import pytest
from unittest.mock import patch

from src.config.database_registry import (
    DatabaseProfile,
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
        assert p.database_type == "duckdb"
        assert p.sql_dialect == "postgresql"
        assert p.data_path == "databases/ensembl"
        assert p.parquet_glob_pattern == "*.parquet"
        assert p.hive_partitioning is False
        assert p.supports_s3 is False

    def test_local_profiles_expose_all_tables(self):
        """All three are built locally, so there is no schema to hide."""
        for profile in DatabaseProfile:
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
    """Path overrides for the Ensembl Parquet dataset."""

    def test_data_path_override(self):
        with patch.dict(
            "os.environ",
            {
                "DB_REGISTRY_ACTIVE_DATABASE": "ensembl",
                "DB_REGISTRY_ENSEMBL_DATA_PATH_OVERRIDE": "/data/ensembl",
            },
            clear=True,
        ):
            get_registry_settings.cache_clear()
            assert get_active_profile().data_path == "/data/ensembl"

    def test_schema_path_override(self):
        with patch.dict(
            "os.environ",
            {
                "DB_REGISTRY_ACTIVE_DATABASE": "ensembl",
                "DB_REGISTRY_ENSEMBL_SCHEMA_PATH_OVERRIDE": "/data/ensembl/schema.yaml",
            },
            clear=True,
        ):
            get_registry_settings.cache_clear()
            assert get_active_profile().schema_path == "/data/ensembl/schema.yaml"


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
    """No profile is feature-flagged — all three are built locally."""

    def test_every_profile_is_enabled(self):
        with patch.dict("os.environ", {}, clear=True):
            get_registry_settings.cache_clear()
            assert set(get_enabled_profiles()) == set(DATABASE_PROFILES)

    def test_ensembl_is_offered_without_a_flag(self):
        """It used to be hidden behind DB_REGISTRY_ENSEMBL_ENABLED because it
        needed outbound MySQL. It is a local Parquet build now."""
        with patch.dict("os.environ", {}, clear=True):
            get_registry_settings.cache_clear()
            assert DatabaseProfile.ENSEMBL in get_enabled_profiles()

    def test_no_feature_flags_remain(self):
        """Pins the decision so a flag cannot creep back for one profile."""
        flags = [f for f in DatabaseRegistrySettings.model_fields if f.endswith("_enabled")]
        assert not flags, f"unexpected feature flags: {flags}"

    def test_enabled_matches_list_available(self):
        """The two enumeration paths must not drift apart."""
        with patch.dict("os.environ", {}, clear=True):
            get_registry_settings.cache_clear()
            assert {p["name"] for p in list_available_profiles()} == {
                c.name for c in get_enabled_profiles().values()
            }


class TestSchemaDescriptionsAreUsable:
    """Every profile's schema YAML must survive load_schema_description().

    That loader indexes `table_info["columns"]` without a guard, so a table
    missing the key raises KeyError — and only at agent runtime, when the model
    calls get_database_schema. Cheap to catch here.
    """

    @pytest.mark.parametrize("profile", list(DatabaseProfile))
    def test_schema_yaml_loads_and_is_well_formed(self, profile):
        import yaml

        from src.config.paths import resolve_path

        config = DATABASE_PROFILES[profile]
        path = resolve_path(config.schema_path, must_exist=True)
        data = yaml.safe_load(path.read_text())

        tables = data["schema"]["tables"]
        assert tables, f"{profile.value} declares no tables"

        for table_name, table_info in tables.items():
            assert "columns" in table_info, (
                f"{profile.value}.{table_name} has no 'columns' key — "
                "load_schema_description would raise KeyError"
            )
            assert table_info["columns"], f"{profile.value}.{table_name} has no columns"
            for column in table_info["columns"]:
                assert "name" in column and "type" in column, (
                    f"{profile.value}.{table_name} has a column missing name/type"
                )

    @pytest.mark.parametrize("profile", list(DatabaseProfile))
    def test_whitelisted_tables_exist_in_the_schema(self, profile):
        """A whitelist naming a table the YAML lacks silently hides it."""
        import yaml

        from src.config.paths import resolve_path

        config = DATABASE_PROFILES[profile]
        if not config.allowed_tables:
            pytest.skip(f"{profile.value} exposes all tables")

        data = yaml.safe_load(resolve_path(config.schema_path, must_exist=True).read_text())
        documented = {t.lower() for t in data["schema"]["tables"]}
        missing = {t.lower() for t in config.allowed_tables} - documented
        assert not missing, f"{profile.value} whitelists undocumented tables: {missing}"
