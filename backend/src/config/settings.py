"""Configuration management for the backend application.

Uses Pydantic Settings to load and validate configuration from environment variables.
Supports optional Vault Secrets via /secrets/secret.yaml.
"""

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Callable, TYPE_CHECKING

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

if TYPE_CHECKING:
    from src.config.database import DatabaseSettings

logger = logging.getLogger(__name__)

# The gateway settings have been renamed twice — first off the vendor name
# (`portkey_*`), then onto the conventional OpenAI shape. Env and dotenv accept
# every old name through each field's `AliasChoices`, but the vault source below
# builds a plain dict that is merged *before* alias resolution: a legacy vault
# key and a current env var would then both be present, and `AliasChoices` picks
# its first choice — silently letting env win over vault, inverting the
# documented Vault > Env precedence. Canonicalizing vault keys up front removes
# the ambiguity.
_LEGACY_SECRET_KEYS = {
    "portkey_base_url": "openai_base_url",
    "openai_gateway_base_url": "openai_base_url",
    "portkey_bedrock_api_key": "openai_api_key",
    "openai_bedrock_api_key": "openai_api_key",
    "portkey_bedrock_slug": "openai_slug",
    "openai_bedrock_slug": "openai_slug",
}

# Header the slug travelled in before it moved into `openai_extra_headers`.
# Only used to keep legacy `openai_slug` configuration working.
_LEGACY_SLUG_HEADER = "x-portkey-slug"


def load_vault_secrets() -> dict[str, Any]:
    """Load secrets from Vault Secrets YAML file.

    Returns:
        Dictionary of key-value pairs from secret.yaml, or empty dict if not available.

    Note:
        This function checks for USE_VAULT_SECRETS environment variable and
        /secrets/secret.yaml file. If either is missing, returns empty dict.
    """
    use_vault_secrets = os.getenv("USE_VAULT_SECRETS", "false").lower() == "true"

    if not use_vault_secrets:
        return {}

    secrets_path = Path("/secrets/secret.yaml")

    if not secrets_path.exists():
        logger.warning(
            "USE_VAULT_SECRETS=true but /secrets/secret.yaml not found. "
            "Falling back to environment variables only."
        )
        return {}

    if yaml is None:
        logger.warning(
            "PyYAML not installed. Cannot load vault secrets. "
            "Install pyyaml to use vault secrets feature."
        )
        return {}

    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = yaml.safe_load(f) or {}

        # Convert to flat dict if nested structure
        if isinstance(secrets, dict):
            # Handle both flat and nested structures
            flat_secrets = {}
            for key, value in secrets.items():
                if isinstance(value, dict):
                    # If nested, flatten with underscore separator
                    for nested_key, nested_value in value.items():
                        flat_secrets[f"{key}_{nested_key}".upper()] = nested_value
                else:
                    flat_secrets[key.upper()] = value

            logger.info(f"Loaded {len(flat_secrets)} secrets from Vault Secrets")
            logger.info(f"Vault secret keys: {sorted(flat_secrets.keys())}")
            return flat_secrets
        else:
            logger.warning("Vault secrets file is not in expected format (dict)")
            return {}
    except Exception as e:
        logger.warning(
            f"Failed to load vault secrets from /secrets/secret.yaml: {e}. "
            "Falling back to environment variables only."
        )
        return {}


class Settings(BaseSettings):
    """Application settings loaded from environment variables and optionally Vault Secrets.

    Precedence: Vault Secrets > Environment Variables
    """

    @staticmethod
    def vault_secrets_source() -> dict[str, Any]:
        """Custom settings source for Vault Secrets.

        This source runs after environment variables are loaded,
        allowing vault secrets to override env vars.

        Returns:
            Dictionary of vault secrets (empty if not enabled)
        """
        vault_secrets = load_vault_secrets()

        # Convert keys to lowercase with underscores to match Pydantic field names
        if vault_secrets:
            converted_secrets = {}
            for key, value in vault_secrets.items():
                pydantic_key = key.lower().replace("-", "_")
                pydantic_key = _LEGACY_SECRET_KEYS.get(pydantic_key, pydantic_key)
                converted_secrets[pydantic_key] = value
            # Log which AWS-related keys are available
            aws_keys = [k for k in converted_secrets.keys() if "aws" in k.lower()]
            logger.info(f"Vault secrets AWS keys after conversion: {aws_keys}")
            return converted_secrets

        return {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

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

        Returns sources in order: dotenv, env, vault_secrets
        This ensures vault secrets override environment variables.
        """
        return (
            dotenv_settings,
            env_settings,
            Settings.vault_secrets_source,
        )

    # OpenAI-compatible gateway configuration.
    #
    # Deliberately the conventional OpenAI names: every model is served by one
    # OpenAI-compatible endpoint, not by a vendor SDK, so the config reads the
    # way any OpenAI-compatible tool expects. Each field also accepts the names
    # it had before this rename, so deployed environments keep working without
    # a secret rotation.
    openai_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "openai_base_url", "openai_gateway_base_url", "portkey_base_url"
        ),
        description="Base URL of the OpenAI-compatible gateway",
    )
    openai_api_key: str = Field(
        ...,
        validation_alias=AliasChoices(
            "openai_api_key", "openai_bedrock_api_key", "portkey_bedrock_api_key"
        ),
        description="API key for the OpenAI-compatible gateway",
    )

    # Our gateway reads the key from a custom header rather than the standard
    # `Authorization` bearer, so the key is sent in both places: the bearer is
    # what the name promises, the header is what this gateway actually checks.
    # Set to "" for a gateway that only wants the bearer.
    openai_api_key_header: str = Field(
        default="x-portkey-api-key",
        description="Header to also carry the API key in ('' = bearer only)",
    )
    # Anything else the gateway needs on the wire — routing slugs, tenant ids.
    # JSON object in env: OPENAI_EXTRA_HEADERS={"x-portkey-slug":"bedrock"}
    #
    # `NoDecode` because pydantic-settings JSON-decodes complex fields inside the
    # env source, before any validator runs — an empty `OPENAI_EXTRA_HEADERS=`
    # would raise SettingsError there and no amount of validation could soften
    # it. Parsing here keeps the failure modes ours.
    openai_extra_headers: Annotated[dict[str, str], NoDecode] = Field(
        default_factory=dict,
        description="Extra headers sent to the gateway on every request (JSON object)",
    )

    @field_validator("openai_extra_headers", mode="before")
    @classmethod
    def _parse_extra_headers(cls, value: Any) -> Any:
        """Parse the JSON object, treating blank as 'no extra headers'.

        Orchestrators routinely inject `OPENAI_EXTRA_HEADERS=` when the value is
        absent; taking the service down at startup over a header nobody wanted
        is the wrong trade. Malformed JSON still fails, but says why.
        """
        if value is None:
            return {}
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"OPENAI_EXTRA_HEADERS must be a JSON object, got {value!r}: {exc}"
                ) from exc
        return value

    # Legacy: the slug used to be its own setting. Folded into
    # `openai_extra_headers` below so deployed PORTKEY_BEDROCK_SLUG values keep
    # routing. Prefer OPENAI_EXTRA_HEADERS for anything new.
    openai_slug: str | None = Field(
        default=None,
        validation_alias=AliasChoices("openai_slug", "openai_bedrock_slug", "portkey_bedrock_slug"),
        description="Deprecated — use OPENAI_EXTRA_HEADERS",
    )

    @model_validator(mode="after")
    def _fold_legacy_slug_into_headers(self) -> "Settings":
        """Carry a legacy slug setting into the extra headers.

        Without this, upgrading silently drops the routing header for every
        environment that still configures the slug the old way — the gateway
        then rejects requests at runtime rather than at startup.
        An explicit OPENAI_EXTRA_HEADERS entry always wins.
        """
        if self.openai_slug and _LEGACY_SLUG_HEADER not in self.openai_extra_headers:
            self.openai_extra_headers = {
                **self.openai_extra_headers,
                _LEGACY_SLUG_HEADER: self.openai_slug,
            }
        return self

    # Application Configuration
    environment: str = Field(default="development", description="Environment name")
    log_level: str = Field(default="info", description="Logging level")
    api_version: str = Field(default="1.0.0", description="API version")

    # JWT Configuration
    jwt_secret_key: str = Field(
        ...,
        description="Secret key for JWT token signing. "
        "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Access token expiration time in minutes (default: 30 minutes)",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="Refresh token expiration time in days (default: 7 days)",
    )

    # Per-agent models. Defaults are what the code shipped with, so an
    # environment that sets none of these behaves exactly as before.
    # src/config/agents.py maps agent names onto these fields.
    openai_model_coordinator: str = Field(
        default="us.anthropic.claude-sonnet-4-6",
        description="Model for the coordinator agent",
    )
    openai_model_orchestrator: str = Field(
        default="us.anthropic.claude-opus-5",
        description="Model for the orchestrator agent",
    )
    openai_model_coder: str = Field(
        default="us.anthropic.claude-sonnet-5",
        description="Model for the coder agent",
    )
    openai_model_sql_agent: str = Field(
        default="us.anthropic.claude-sonnet-5",
        description="Model for the SQL agent",
    )
    openai_model_researcher: str = Field(
        default="us.anthropic.claude-sonnet-5",
        description="Model for the researcher agent",
    )
    openai_model_summarizer: str = Field(
        default="us.anthropic.claude-sonnet-4-6",
        description="Model for the summarizer agent",
    )
    openai_model_title: str = Field(
        default="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        description="Model for conversation auto-titling",
    )

    # LLM Configuration
    #
    # `llm_provider` and `llm_model` used to live here, defaulting to the Azure
    # route and gpt-4o-mini. Nothing read them, and both named a route that no
    # longer exists.
    llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="LLM temperature",
    )
    llm_streaming: bool = Field(default=True, description="Enable LLM streaming")

    # Context Window Management
    context_model_max_tokens: int = Field(
        default=200_000,
        description="Max input tokens for the orchestrator model (200K for all Claude models via Bedrock)",
    )
    context_summary_trigger_fraction: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Fraction of context_model_max_tokens to trigger summarization (0.70 = 140K tokens)",
    )
    context_summary_keep_messages: int = Field(
        default=20,
        description="Number of recent messages to keep verbatim after summarization",
    )
    context_tool_clear_trigger: int = Field(
        default=140_000,
        description="Token threshold for clearing older tool outputs (should match summary trigger)",
    )
    context_tool_clear_keep: int = Field(
        default=3,
        description="Number of recent tool results to preserve when clearing",
    )

    # CORS Configuration
    cors_origins: str = Field(
        default="http://localhost:3100,http://localhost:5173,http://localhost:80",
        description="Comma-separated allowed CORS origins",
    )
    cors_origin_regex: str | None = Field(
        default=None,
        description="Optional regex of additional allowed origins, for deployments that "
        r"serve the frontend from a wildcard subdomain (e.g. https://.*\.example\.com). "
        "Unset means only the exact CORS_ORIGINS list is allowed.",
    )

    # Sandbox Configuration
    sandbox_url: str = Field(
        default="http://sandbox:8080",
        description="URL to sandbox code execution service",
    )
    sandbox_timeout: int = Field(
        default=60,
        ge=1,
        le=120,
        description="Sandbox request timeout in seconds",
    )

    # R Sandbox Configuration
    r_sandbox_url: str = Field(
        default="http://r-sandbox:8081",
        description="URL to R sandbox code execution service",
    )
    r_sandbox_timeout: int = Field(
        default=60,
        ge=1,
        le=120,
        description="R sandbox request timeout in seconds",
    )

    # AWS S3 Configuration
    aws_access_key_id: str | None = Field(
        None,
        description="AWS access key ID (optional - if not provided, uses IAM role credentials via default credential chain)",
    )
    aws_secret_access_key: str | None = Field(
        None,
        description="AWS secret access key (optional - if not provided, uses IAM role credentials via default credential chain)",
    )
    aws_session_token: str | None = Field(
        None,
        description="AWS session token (optional, for temporary credentials)",
    )
    aws_default_region: str = Field(
        default="us-east-1",
        description="AWS default region",
    )
    aws_default_bucket: str | None = Field(
        None,
        description="Default S3 bucket name (optional, for convenience)",
    )
    allowed_s3_buckets: str | None = Field(
        None,
        description="Comma-separated list of allowed S3 buckets (optional whitelist)",
    )
    aws_endpoint_url: str | None = Field(
        None,
        description="Custom S3 endpoint for S3-compatible storage, e.g. http://localhost:9000 "
        "for a local MinIO. Leave unset to talk to real AWS.",
    )
    aws_s3_addressing_style: str = Field(
        default="auto",
        description="S3 addressing style: 'auto', 'path', or 'virtual'. See "
        "s3_addressing_style_resolved for how 'auto' behaves.",
    )

    # SQL Query Results Configuration
    sql_always_save_to_s3: bool = Field(
        default=False,
        description="Always save SQL query results to S3, regardless of query type or size. "
        "When enabled, all executed queries will be saved as CSV files in S3 and tracked in MongoDB. "
        "Useful for comprehensive query tracking and audit trails.",
    )

    # LangGraph Checkpointer Configuration
    checkpointer_type: str = Field(
        default="mongodb",
        description="Checkpointer type: 'mongodb' (production) or 'sqlite' (testing)",
    )

    # MongoDB Checkpointer Settings
    mongodb_uri: str | None = Field(
        default=None,
        description="MongoDB connection URI for checkpointer. "
        "Also accepts MONGODB_CONNECTION_STRING env var.",
    )
    mongodb_connection_string: str | None = Field(
        default=None,
        description="MongoDB connection string (alternative to mongodb_uri). "
        "Used if mongodb_uri is not set.",
    )
    mongodb_db_name: str = Field(
        default="langgraph_checkpoints",
        description="MongoDB database name for checkpoints",
    )

    # SQLite Checkpointer Settings (for testing)
    checkpointer_db_path: str = Field(
        default="databases/checkpoints.db",
        description="Path to SQLite database for LangGraph checkpointer (testing only). "
        "Can be absolute or relative to working directory.",
    )

    # —— Literature search (Europe PMC) ——
    # Public REST API: no key, no registration, nothing to configure.
    # Docs: https://europepmc.org/RestfulWebService
    europepmc_api_url: str = Field(
        default="https://www.ebi.ac.uk/europepmc/webservices/rest",
        description="Europe PMC REST API base URL (no trailing slash)",
    )
    europepmc_timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Per-request timeout for Europe PMC calls",
    )

    # SSL Certificate Configuration
    ssl_cert_path: str | None = Field(
        None,
        description="Path to a custom CA bundle for outbound HTTPS calls. "
        "Set this when running behind a TLS-inspecting corporate proxy. "
        "Can be absolute or relative to working directory.",
    )
    disable_ssl_verify: bool = Field(
        default=False,
        description="Disable SSL verification (for development only). "
        "Set to true only in development environments.",
    )

    # —— OpenTelemetry & Traces (Phase 0) ——
    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry span export",
    )
    otel_service_name: str = Field(
        default="genomechat-backend",
        description="OTel service.name resource attribute",
    )
    trace_storage_enabled: bool = Field(
        default=False,
        description="Write spans to MongoDB traces collection",
    )
    trace_mongodb_collection: str = Field(
        default="traces",
        description="Collection name for trace spans",
    )
    trace_s3_archive_enabled: bool = Field(
        default=False,
        description="Daily mirror of traces to S3",
    )
    trace_s3_prefix: str = Field(
        default="traces/",
        description="S3 prefix for trace archive",
    )
    trace_sampling_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Span sampling rate",
    )
    trace_ttl_days: int = Field(
        default=90,
        ge=7,
        le=730,
        description="MongoDB TTL for traces collection (days)",
    )

    # —— Langfuse forward-compat (Phase 0 default OFF; Phase 2 decision gate) ——
    langfuse_enabled: bool = Field(
        default=False,
        description="Also export spans to a Langfuse OTLP endpoint",
    )
    langfuse_otlp_endpoint: str = Field(
        default="",
        description="Langfuse OTLP HTTP endpoint (e.g., https://langfuse.internal/api/public/otel)",
    )
    langfuse_auth_header: str = Field(
        default="",
        description="Base64(public_key:secret_key) for Langfuse Basic auth",
    )
    trace_capture_payloads: bool = Field(
        default=False,
        description=(
            "Attach node/tool/LLM inputs and outputs to spans "
            "(Langfuse Input/Output columns). Dev-only; payloads can be large and may "
            "contain sensitive data."
        ),
    )
    trace_payload_max_chars: int = Field(
        default=8000,
        ge=500,
        le=100_000,
        description="Per-attribute payload char cap when trace_capture_payloads=true",
    )

    # —— Internal observability access control ——
    internal_observability_enabled: bool = Field(
        default=True,
        description="Expose /internal/* observability routes",
    )
    internal_observability_rate_limit_per_hour: int = Field(
        default=1000,
        ge=1,
        description="Per-caller rate limit for /internal/* endpoints",
    )

    # —— Memory pipeline (Phase 0.5 — pilot-gated, default OFF) ——
    memory_extraction_enabled: bool = Field(
        default=False,
        description="Enable per-turn memory extraction (pilot only)",
    )
    memory_extraction_sampling_rate: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Fraction of turns to extract",
    )
    memory_extraction_agent: str = Field(
        default="summarizer",
        description="Agent key for extraction LLM (Haiku via the Bedrock route)",
    )
    memory_consolidation_enabled: bool = Field(
        default=False,
        description="Enable scheduled consolidation job",
    )
    memory_consolidation_interval_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="Consolidation cadence in minutes",
    )
    memory_embedding_provider: str = Field(
        default="openai-bedrock-titan",
        description="Embedding provider: openai-bedrock-titan",
    )
    memory_embedding_model: str = Field(
        default="amazon.titan-embed-text-v2:0",
        description="Embedding model identifier",
    )
    memory_embedding_dimensions: int = Field(
        default=1024,
        description="Embedding output dimensionality (Titan V2 supports 256/512/1024)",
    )
    memory_duplicate_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Cosine threshold above which new memories are treated as duplicates",
    )
    memory_pilot_user_ids: str = Field(
        default="",
        description="Comma-separated opt-in user IDs",
    )
    memory_atlas_vector_search_enabled: bool = Field(
        default=True,
        description="Use Atlas $vectorSearch; False falls back to brute-force cosine",
    )
    memory_embedding_concurrency: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Concurrent Bedrock-route embedding requests per instance",
    )
    memory_extraction_per_user_concurrency: int = Field(
        default=2,
        ge=1,
        le=10,
        description="Max concurrent extraction tasks per user",
    )
    memory_ttl_days: int = Field(
        default=180,
        ge=30,
        le=1095,
        description="MongoDB TTL for research_memories; pinned memories exempt",
    )

    # Database Configuration
    database_settings: "DatabaseSettings" = Field(
        default_factory=lambda: _get_database_settings(),
        description="Database connection settings",
    )

    @property
    def allowed_s3_buckets_list(self) -> list[str]:
        """Parse allowed S3 buckets string into list."""
        if self.allowed_s3_buckets:
            return [bucket.strip() for bucket in self.allowed_s3_buckets.split(",")]
        return []

    @property
    def s3_addressing_style_resolved(self) -> str:
        """Addressing style to hand boto3.

        'auto' means: path-style when a custom endpoint is configured, boto3's own
        'auto' otherwise. Self-hosted S3 servers (MinIO, Ceph, LocalStack) are
        reached by host:port and generally cannot serve virtual-host addressing,
        which would resolve bucket names as `http://my-bucket.localhost:9000`.
        Real AWS keeps boto3's default, since path-style is deprecated there.

        The sandbox repeats this rule in s3_helpers.get_s3_client; it runs as a
        separate service and cannot import these settings.

        The value is normalised before use. python-dotenv strips `# comment`
        from a value, but Docker Compose's own env_file parser does not
        necessarily, and botocore rejects anything it does not recognise with
        InvalidS3AddressingStyleError at client construction — which would take
        out every S3 call rather than just this setting.
        """
        configured = self.aws_s3_addressing_style.split("#")[0].strip().lower()

        if configured in {"path", "virtual"}:
            return configured
        if configured and configured != "auto":
            logger.warning(
                f"Ignoring unrecognised AWS_S3_ADDRESSING_STYLE "
                f"{self.aws_s3_addressing_style!r}; expected auto, path, or virtual"
            )
        return "path" if self.aws_endpoint_url else "auto"

    def validate_s3_bucket(self, bucket: str) -> bool:
        """Validate that a bucket is in the allowed list (if whitelist is configured).

        Args:
            bucket: Bucket name to validate

        Returns:
            True if bucket is allowed, False otherwise
        """
        if not self.allowed_s3_buckets_list:
            # No whitelist configured, allow all buckets
            return True
        return bucket in self.allowed_s3_buckets_list

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins string into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    def get_openai_headers(self) -> dict[str, str]:
        """Build the headers sent to the gateway on every request.

        The API key also travels as a standard `Authorization` bearer, set by
        the OpenAI client from `openai_api_key`; this covers the extra header
        our gateway reads instead.

        Returns:
            Dictionary of headers to attach to every gateway request
        """
        headers = dict(self.openai_extra_headers)
        if self.openai_api_key_header:
            headers[self.openai_api_key_header] = self.openai_api_key
        return headers


def _get_database_settings() -> "DatabaseSettings":
    """Get DatabaseSettings instance (lazy import to avoid circular dependency)."""
    from src.config.database import DatabaseSettings

    return DatabaseSettings()


# Import DatabaseSettings and rebuild Settings model to resolve forward reference
from src.config.database import DatabaseSettings

Settings.model_rebuild()

# Global settings instance
settings = Settings()
