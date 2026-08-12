"""Database registry for managing multiple database profiles.

Provides a centralized configuration system for switching between different
databases (ClinVar, GWAS Catalog, Ensembl) with profile-specific settings.

All three registered profiles are built from public genomics sources:

  clinvar  — NCBI ClinVar, public domain. Built locally into SQLite by
             ``scripts/build_genomics_databases.py``.
  gwas     — EMBL-EBI GWAS Catalog, CC BY 4.0. Built locally into Parquet
             and queried through DuckDB.
  ensembl  — EMBL-EBI Ensembl GRCh38 gene annotation. Built locally into
             Parquet from the release GTF and queried through DuckDB.
"""

import logging
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from src.config.paths import resolve_path

logger = logging.getLogger(__name__)


class DatabaseProfile(str, Enum):
    """Registered database profiles."""

    CLINVAR = "clinvar"
    GWAS = "gwas"
    ENSEMBL = "ensembl"


class QuestionComplexity(str, Enum):
    """Complexity level for example questions."""

    BASIC = "basic"
    MEDIUM = "medium"
    ADVANCED = "advanced"


class ExampleQuestion(BaseModel):
    """An example question for onboarding users to a database."""

    label: str  # Short theme displayed as chip (e.g., "Species Distribution")
    text: str  # Full query text populated on click
    complexity: QuestionComplexity = QuestionComplexity.BASIC


class DatabaseProfileConfig(BaseModel):
    """Configuration for a specific database profile."""

    name: str
    display_name: str
    database_type: str  # "sqlite" or "duckdb"

    # Path configuration
    data_path: str  # Path to data (SQLite file or Parquet directory)
    schema_path: str  # Path to schema_description.yaml

    # Prompt context
    context_file: str  # Filename for database-specific prompt context

    # Query configuration
    sql_dialect: str = "sqlite"  # "sqlite" or "postgresql" (DuckDB uses PostgreSQL syntax)
    supports_s3: bool = False
    parquet_glob_pattern: Optional[str] = None  # For Parquet: "**/*.parquet"
    hive_partitioning: bool = True

    # Domain context
    description: str = ""
    domain: str = "genomics"

    # Table/schema whitelisting (for large multi-schema databases)
    allowed_schemas: list[str] | None = Field(
        default=None,
        description="When set, only these schemas are exposed to the SQL agent.",
    )
    allowed_tables: list[str] | None = Field(
        default=None,
        description="When set, only these tables are exposed to the SQL agent.",
    )

    # Example questions for onboarding
    example_questions: list[ExampleQuestion] = Field(default_factory=list)


# Database profile configurations
DATABASE_PROFILES: dict[DatabaseProfile, DatabaseProfileConfig] = {
    DatabaseProfile.CLINVAR: DatabaseProfileConfig(
        name="clinvar",
        display_name="ClinVar",
        database_type="sqlite",
        data_path="databases/clinvar/clinvar.db",
        schema_path="databases/clinvar/schema_description.yaml",
        context_file="clinvar_context.md",
        sql_dialect="sqlite",
        supports_s3=False,
        description=(
            "NCBI ClinVar: a public archive of reported relationships between human "
            "genetic variants and phenotypes, with supporting evidence. One row per "
            "variant/condition assertion, carrying clinical significance "
            "(Pathogenic / Likely pathogenic / Uncertain significance / Benign), the "
            "ACMG-style review status, submitter count, gene symbol, dbSNP rsID, and "
            "GRCh38 coordinates. Built locally into SQLite from the weekly "
            "variant_summary release; GRCh38 rows only unless rebuilt with "
            "--clinvar-full. Public domain (US Government work)."
        ),
        domain="clinical genetics",
        example_questions=[
            ExampleQuestion(
                label="Clinical Significance Mix",
                text=(
                    "How many variants are in ClinVar for each clinical significance "
                    "category? Show the top 10 as a bar chart."
                ),
                complexity=QuestionComplexity.BASIC,
            ),
            ExampleQuestion(
                label="Variants in a Gene",
                text=(
                    "How many pathogenic and likely pathogenic variants are reported "
                    "in BRCA1? Break them down by variant type."
                ),
                complexity=QuestionComplexity.BASIC,
            ),
            ExampleQuestion(
                label="Review Confidence",
                text=(
                    "Compare the review status distribution between pathogenic and "
                    "benign variants. Are pathogenic calls better supported?"
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Most-Studied Genes",
                text=(
                    "Which 20 genes have the most submitted variants? For each, show "
                    "the fraction that are variants of uncertain significance (VUS)."
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Chromosomal Density",
                text=(
                    "Plot the density of pathogenic variants along each chromosome "
                    "using 10 Mb bins. Which regions are most enriched?"
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="VUS Burden Analysis",
                text=(
                    "Conduct a comprehensive analysis of the variant-of-uncertain-"
                    "significance burden in hereditary cancer genes. Quantify VUS rates "
                    "per gene, compare against submitter counts and review status, and "
                    "review the literature on VUS reclassification."
                ),
                complexity=QuestionComplexity.ADVANCED,
            ),
        ],
    ),
    DatabaseProfile.GWAS: DatabaseProfileConfig(
        name="gwas",
        display_name="GWAS Catalog",
        database_type="duckdb",
        data_path="databases/gwas",
        schema_path="databases/gwas/schema_description.yaml",
        context_file="gwas_context.md",
        # DuckDB speaks PostgreSQL syntax.
        sql_dialect="postgresql",
        supports_s3=True,
        parquet_glob_pattern="*.parquet",
        hive_partitioning=False,
        description=(
            "The NHGRI-EBI GWAS Catalog: curated SNP-trait associations from published "
            "genome-wide association studies. Two tables. `associations` holds one row "
            "per reported association with p-value, effect size (OR or beta), risk "
            "allele and frequency, mapped gene, and an EFO ontology term for the trait. "
            "`studies` holds study-level metadata including PubMed ID, sample sizes, "
            "ancestry description, and genotyping platform. Joinable on PUBMEDID / "
            "STUDY ACCESSION, which also makes this dataset a natural bridge to the "
            "literature-search tools. Licensed CC BY 4.0 by EMBL-EBI."
        ),
        domain="statistical genetics",
        example_questions=[
            ExampleQuestion(
                label="Most-Studied Traits",
                text=(
                    "What are the 20 most frequently studied traits in the GWAS "
                    "Catalog by number of reported associations?"
                ),
                complexity=QuestionComplexity.BASIC,
            ),
            ExampleQuestion(
                label="Associations for a Trait",
                text=(
                    "Find genome-wide significant associations (p < 5e-8) for type 2 "
                    "diabetes. Show the strongest 25 with their mapped genes."
                ),
                complexity=QuestionComplexity.BASIC,
            ),
            ExampleQuestion(
                label="Pleiotropic Variants",
                text=(
                    "Which SNPs are associated with the largest number of distinct "
                    "traits? Show the top 15 and list their traits."
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Effect Size vs Frequency",
                text=(
                    "Plot effect size against risk allele frequency for genome-wide "
                    "significant associations. Does the expected inverse relationship "
                    "hold?"
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Study Ancestry Diversity",
                text=(
                    "Join associations to studies and analyse how sample ancestry has "
                    "changed over time. What fraction of studies are still "
                    "European-only?"
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Trait Architecture Review",
                text=(
                    "Conduct a comprehensive analysis of the genetic architecture of "
                    "coronary artery disease. Summarise the significant loci and their "
                    "genes, examine effect-size distribution and study sample sizes, "
                    "and review the recent literature on polygenic risk for this trait."
                ),
                complexity=QuestionComplexity.ADVANCED,
            ),
        ],
    ),
    DatabaseProfile.ENSEMBL: DatabaseProfileConfig(
        name="ensembl",
        display_name="Ensembl GRCh38",
        database_type="duckdb",
        data_path="databases/ensembl",
        schema_path="databases/ensembl/schema_description.yaml",
        context_file="ensembl_context.md",
        # DuckDB speaks PostgreSQL syntax.
        sql_dialect="postgresql",
        supports_s3=False,
        parquet_glob_pattern="*.parquet",
        hive_partitioning=False,
        # No allowed_tables: unlike the old MySQL core schema's ~75 tables,
        # this dataset is four tables we chose, so there is nothing to hide.
        description=(
            "Ensembl GRCh38 release 116 gene annotation, built locally into "
            "Parquet from the public GTF and queried through DuckDB. Four "
            "tables: genes, transcripts, exons and chromosomes, covering gene "
            "structure, biotypes, genomic coordinates, transcript isoforms, "
            "coding sequence lengths and canonical/MANE transcript flags. "
            "Gene symbols are HGNC. Does not include gene description text or "
            "RefSeq/UniProt cross-references, which the GTF does not carry."
        ),
        domain="genome annotation",
        example_questions=[
            ExampleQuestion(
                label="Gene Biotypes",
                text=(
                    "How many genes are annotated per biotype (protein_coding, "
                    "lncRNA, pseudogene, etc.)? Show the top 15 as a bar chart."
                ),
                complexity=QuestionComplexity.BASIC,
            ),
            ExampleQuestion(
                label="Look Up a Gene",
                text=(
                    "Find the gene TP53: its Ensembl ID, chromosome, "
                    "coordinates, strand, biotype, and its MANE Select "
                    "transcript."
                ),
                complexity=QuestionComplexity.BASIC,
            ),
            ExampleQuestion(
                label="Transcripts per Gene",
                text=(
                    "Which 20 protein-coding genes have the most annotated "
                    "transcripts?"
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Exon Structure",
                text=(
                    "For the canonical transcript of BRCA2, list its exons in "
                    "transcription order with coordinates and lengths, then "
                    "plot the exon length distribution."
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Gene Density",
                text=(
                    "Count protein-coding genes per chromosome, join to "
                    "chromosome length, and plot genes per megabase."
                ),
                complexity=QuestionComplexity.MEDIUM,
            ),
            ExampleQuestion(
                label="Isoform Complexity",
                text=(
                    "Analyse how transcript and exon complexity varies across "
                    "gene biotypes: transcripts per gene, exons per "
                    "transcript, and CDS length versus spliced length. "
                    "Compare MANE Select transcripts against the rest."
                ),
                complexity=QuestionComplexity.ADVANCED,
            ),
        ],
    ),
}

def _load_db_registry_vault_secrets() -> dict[str, Any]:
    """Load database registry secrets from Vault Secrets.

    Returns:
        Dictionary of DB_REGISTRY_* secrets with prefix stripped.
    """
    # Import here to avoid circular dependency
    from src.config.settings import load_vault_secrets

    vault_secrets = load_vault_secrets()
    if not vault_secrets:
        return {}

    # Filter for DB_REGISTRY_* keys and strip prefix
    prefix = "DB_REGISTRY_"
    filtered = {}
    for key, value in vault_secrets.items():
        upper_key = key.upper()
        if upper_key.startswith(prefix):
            # Strip prefix and convert to lowercase for Pydantic field matching
            field_name = upper_key[len(prefix) :].lower()
            filtered[field_name] = value

    if filtered:
        logger.info(f"Loaded {len(filtered)} database registry secrets from Vault")

    return filtered


class DatabaseRegistrySettings(BaseSettings):
    """Settings for database registry - which database is active.

    Supports loading from environment variables and Vault Secrets.
    """

    active_database: DatabaseProfile = Field(
        default=DatabaseProfile.CLINVAR,
        description="Currently active database profile",
    )

    # === Data path overrides (for Docker/Kubernetes deployments) ===
    clinvar_data_path_override: Optional[str] = Field(
        default=None,
        description="Override path for the ClinVar SQLite file (e.g., /data/clinvar/clinvar.db)",
    )

    gwas_data_path_override: Optional[str] = Field(
        default=None,
        description="Override path for the GWAS Parquet directory (e.g., /data/gwas)",
    )

    gwas_s3_path: Optional[str] = Field(
        default=None,
        description="S3 path for GWAS Parquet data; takes priority over the local path "
        "(e.g., s3://bucket/gwas/)",
    )

    # === Schema path overrides (usually not needed, schemas bundled with app) ===
    clinvar_schema_path_override: Optional[str] = Field(
        default=None,
        description="Override path for the ClinVar schema YAML",
    )

    gwas_schema_path_override: Optional[str] = Field(
        default=None,
        description="Override path for the GWAS schema YAML",
    )

    ensembl_schema_path_override: Optional[str] = Field(
        default=None,
        description="Override path for the Ensembl schema YAML",
    )

    ensembl_data_path_override: Optional[str] = Field(
        default=None,
        description="Override path for the Ensembl Parquet directory (e.g., /data/ensembl)",
    )

    model_config = {
        "env_prefix": "DB_REGISTRY_",
        "env_file": ".env",
        "extra": "ignore",
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Callable,
        env_settings: Callable,
        dotenv_settings: Callable,
        file_secret_settings: Callable,
    ) -> tuple[Callable, ...]:
        """Customize settings sources to include vault secrets.

        Order: dotenv -> env -> vault_secrets (vault has highest priority)
        """
        return (
            dotenv_settings,
            env_settings,
            _load_db_registry_vault_secrets,
        )


@lru_cache
def get_registry_settings() -> DatabaseRegistrySettings:
    """Get cached database registry settings."""
    return DatabaseRegistrySettings()


def get_enabled_profiles() -> dict[DatabaseProfile, "DatabaseProfileConfig"]:
    """Every registered profile. None are feature-flagged.

    All three are built locally by scripts/build_genomics_databases.py, so an
    unbuilt profile fails loudly at connect time rather than being hidden from
    the picker. Kept as a distinct function from DATABASE_PROFILES because it
    is the natural place to reintroduce gating if a profile ever needs it.
    """
    return dict(DATABASE_PROFILES)


# Runtime state for session-based database switching
# This is not persistent and resets on server restart
_runtime_active_database: Optional[DatabaseProfile] = None


def get_runtime_active_database() -> DatabaseProfile:
    """Get the runtime active database, falling back to registry settings.

    Returns:
        The currently active database profile enum.
    """
    global _runtime_active_database
    if _runtime_active_database is None:
        return get_registry_settings().active_database
    return _runtime_active_database


def set_runtime_active_database(profile: DatabaseProfile) -> None:
    """Set the runtime active database.

    Args:
        profile: The database profile to set as active.
    """
    global _runtime_active_database
    _runtime_active_database = profile
    logger.info(f"Runtime active database set to: {profile.value}")


def get_active_profile() -> DatabaseProfileConfig:
    """Get the currently active database profile configuration.

    Uses runtime state if set, otherwise falls back to registry settings.

    Returns:
        DatabaseProfileConfig for the active database

    Raises:
        ValueError: If active database profile is not found
    """
    active_db = get_runtime_active_database()
    profile = DATABASE_PROFILES.get(active_db)

    if profile is None:
        raise ValueError(f"Unknown database profile: {active_db}")

    # Apply path overrides for production
    settings = get_registry_settings()
    profile = _apply_path_overrides(profile, settings)

    return profile


def get_active_profile_from_context() -> DatabaseProfileConfig:
    """Get active database profile, preferring request context over global state.

    This function provides request-scoped database selection by checking the
    database_id_context ContextVar first. This ensures correct database selection
    in multi-instance deployments where global state is not shared across pods.

    Priority order:
    1. database_id_context (request-scoped, set per chat request)
    2. _runtime_active_database (global runtime state)
    3. registry settings default (environment config)

    Returns:
        DatabaseProfileConfig for the active database

    Raises:
        ValueError: If database profile is not found
    """
    from src.utils.context import database_id_context

    # First try context variable (request-scoped)
    context_db_id = database_id_context.get()
    if context_db_id:
        try:
            profile_enum = DatabaseProfile(context_db_id.lower())
            return get_profile_with_overrides(profile_enum)
        except ValueError:
            logger.warning(f"Invalid database_id in context: {context_db_id}, falling back")

    # Fall back to existing behavior (runtime state or settings default)
    return get_active_profile()


def _apply_path_overrides(
    profile: DatabaseProfileConfig,
    settings: DatabaseRegistrySettings,
) -> DatabaseProfileConfig:
    """Apply production path overrides to profile configuration.

    Args:
        profile: Base profile configuration
        settings: Registry settings with potential overrides

    Returns:
        Profile with overridden paths if applicable
    """
    # Create a copy to avoid mutating the original
    profile_dict = profile.model_dump()

    if profile.name == "clinvar":
        if settings.clinvar_data_path_override:
            profile_dict["data_path"] = settings.clinvar_data_path_override
        if settings.clinvar_schema_path_override:
            profile_dict["schema_path"] = settings.clinvar_schema_path_override

    if profile.name == "gwas":
        # Data path: S3 takes priority, then local override
        if settings.gwas_s3_path:
            profile_dict["data_path"] = settings.gwas_s3_path
        elif settings.gwas_data_path_override:
            profile_dict["data_path"] = settings.gwas_data_path_override
        # Schema path override
        if settings.gwas_schema_path_override:
            profile_dict["schema_path"] = settings.gwas_schema_path_override

    if profile.name == "ensembl":
        if settings.ensembl_data_path_override:
            profile_dict["data_path"] = settings.ensembl_data_path_override
        if settings.ensembl_schema_path_override:
            profile_dict["schema_path"] = settings.ensembl_schema_path_override

    return DatabaseProfileConfig(**profile_dict)


def get_profile_with_overrides(profile: DatabaseProfile) -> DatabaseProfileConfig:
    """Get database profile with production path overrides applied.

    Args:
        profile: The database profile enum

    Returns:
        DatabaseProfileConfig with any configured path overrides applied
    """
    base_config = DATABASE_PROFILES[profile]
    settings = get_registry_settings()
    return _apply_path_overrides(base_config, settings)


def get_profile_by_name(name: str) -> DatabaseProfileConfig:
    """Get database profile by name string.

    Args:
        name: Profile name (e.g., "clinvar", "gwas")

    Returns:
        DatabaseProfileConfig for the specified profile

    Raises:
        ValueError: If profile name is not found
    """
    try:
        profile_enum = DatabaseProfile(name.lower())
        return DATABASE_PROFILES[profile_enum]
    except ValueError as e:
        available = ", ".join(p.value for p in DatabaseProfile)
        raise ValueError(f"Unknown profile '{name}'. Available: {available}") from e


def list_available_profiles() -> list[dict]:
    """List all available database profiles with their metadata.

    Returns:
        List of profile information dictionaries
    """
    return [
        {
            "name": profile.name,
            "display_name": profile.display_name,
            "database_type": profile.database_type,
            "description": profile.description,
            "domain": profile.domain,
        }
        for profile in DATABASE_PROFILES.values()
    ]


def get_schema_path_for_active_profile() -> Path:
    """Get the schema description path for the active profile.

    Uses centralized path resolution for consistent behavior across
    local development, Docker, and Kubernetes deployments.

    Returns:
        Path to schema_description.yaml for active database

    Raises:
        FileNotFoundError: If schema file cannot be found
    """
    profile = get_active_profile()
    settings = get_registry_settings()

    # Determine which env var to check for override
    env_override_var = None
    if profile.name == "clinvar" and settings.clinvar_schema_path_override:
        env_override_var = "DB_REGISTRY_CLINVAR_SCHEMA_PATH_OVERRIDE"
    elif profile.name == "gwas" and settings.gwas_schema_path_override:
        env_override_var = "DB_REGISTRY_GWAS_SCHEMA_PATH_OVERRIDE"
    elif profile.name == "ensembl" and settings.ensembl_schema_path_override:
        env_override_var = "DB_REGISTRY_ENSEMBL_SCHEMA_PATH_OVERRIDE"

    try:
        resolved = resolve_path(
            profile.schema_path,
            env_override_var=env_override_var,
            must_exist=True,
        )
        logger.info(f"Schema path resolved: {resolved}")
        return resolved
    except FileNotFoundError as e:
        logger.error(f"Schema file not found for profile '{profile.name}': {e}")
        raise


def get_context_file_for_active_profile() -> str:
    """Get the context file name for the active profile.

    Returns:
        Context file name (e.g., "clinvar_context.md")
    """
    profile = get_active_profile()
    return profile.context_file
