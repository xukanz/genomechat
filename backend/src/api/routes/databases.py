"""Database management endpoints.

Provides API endpoints for listing available databases, getting current database,
and switching between database profiles.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config.database_registry import (
    DATABASE_PROFILES,
    DatabaseProfile,
    DatabaseProfileConfig,
    get_enabled_profiles,
    get_profile_with_overrides,
    get_runtime_active_database,
    set_runtime_active_database,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/databases", tags=["databases"])


class ExampleQuestionInfo(BaseModel):
    """Example question for API response."""

    label: str  # Short theme displayed as chip
    text: str  # Full query text
    complexity: str  # "basic", "medium", "advanced"


class DatabaseInfo(BaseModel):
    """Database information for API response."""

    id: str
    name: str
    display_name: str
    database_type: str
    sql_dialect: str
    description: str
    domain: str
    is_active: bool
    status: str  # "connected" or "available"
    example_questions: list[ExampleQuestionInfo] = []


class DatabaseListResponse(BaseModel):
    """Response for listing all databases."""

    databases: list[DatabaseInfo]
    active_database: str


class ActiveDatabaseResponse(BaseModel):
    """Response for getting/setting active database."""

    id: str
    name: str
    display_name: str
    database_type: str
    sql_dialect: str
    description: str
    domain: str


class ConnectDatabaseResponse(BaseModel):
    """Response after attempting database connection."""

    success: bool
    database: DatabaseInfo
    message: str


def _profile_to_info(
    profile: DatabaseProfile,
    config: DatabaseProfileConfig,
    active_profile: DatabaseProfile,
) -> DatabaseInfo:
    """Convert a database profile to API response format."""
    is_active = profile == active_profile
    return DatabaseInfo(
        id=profile.value,
        name=config.name,
        display_name=config.display_name,
        database_type=config.database_type,
        sql_dialect=config.sql_dialect,
        description=config.description,
        domain=config.domain,
        is_active=is_active,
        status="connected" if is_active else "available",
        example_questions=[
            ExampleQuestionInfo(
                label=q.label,
                text=q.text,
                complexity=q.complexity.value,
            )
            for q in config.example_questions
        ],
    )


@router.get("", response_model=DatabaseListResponse)
async def list_databases() -> DatabaseListResponse:
    """List all available databases.

    Returns:
        List of all registered database profiles with their status.
    """
    active_db = get_runtime_active_database()

    databases = [
        _profile_to_info(profile, config, active_db)
        for profile, config in get_enabled_profiles().items()
    ]

    return DatabaseListResponse(
        databases=databases,
        active_database=active_db.value,
    )


@router.get("/active", response_model=ActiveDatabaseResponse)
async def get_active_database() -> ActiveDatabaseResponse:
    """Get the currently active database.

    Returns:
        Current active database profile information.
    """
    active_profile = get_runtime_active_database()
    config = DATABASE_PROFILES[active_profile]

    return ActiveDatabaseResponse(
        id=active_profile.value,
        name=config.name,
        display_name=config.display_name,
        database_type=config.database_type,
        sql_dialect=config.sql_dialect,
        description=config.description,
        domain=config.domain,
    )


@router.get("/{database_id}", response_model=DatabaseInfo)
async def get_database(database_id: str) -> DatabaseInfo:
    """Get information about a specific database.

    Args:
        database_id: Database profile ID (e.g., "clinvar", "gwas")

    Returns:
        Database profile information.

    Raises:
        HTTPException: If database not found.
    """
    try:
        profile = DatabaseProfile(database_id.lower())
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Database '{database_id}' not found. Available: {[p.value for p in DatabaseProfile]}",
        )

    config = DATABASE_PROFILES[profile]
    active_db = get_runtime_active_database()

    return _profile_to_info(profile, config, active_db)


@router.post("/{database_id}/connect", response_model=ConnectDatabaseResponse)
async def connect_to_database(database_id: str) -> ConnectDatabaseResponse:
    """Connect to a specific database.

    Validates the connection and sets it as the active database for this session.

    Args:
        database_id: Database profile ID (e.g., "clinvar", "gwas")

    Returns:
        Connection result with database info.

    Raises:
        HTTPException: If database not found or connection fails.
    """
    # Validate database_id exists
    try:
        profile = DatabaseProfile(database_id.lower())
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Database '{database_id}' not found.",
        )

    # Reject connection to disabled profiles
    enabled = get_enabled_profiles()
    if profile not in enabled:
        raise HTTPException(
            status_code=403,
            detail=f"Database '{database_id}' is not enabled.",
        )

    # Get config with path overrides (S3 paths, production mounts, etc.)
    config = get_profile_with_overrides(profile)

    # Test database connection
    try:
        from src.config.database import DatabaseSettings
        from src.service.database import DatabaseManager
        from src.tools.database import reset_database_manager

        # Create temporary manager to test connection
        settings = DatabaseSettings.from_profile(config)
        test_manager = DatabaseManager(settings)

        # Test with connection (lazy connection triggers on .conn access)
        _ = test_manager.conn  # This triggers lazy connection

        # Connection successful - close test manager
        test_manager.close()

        # Set as active database for runtime
        set_runtime_active_database(profile)

        # Reset the global database manager to pick up new profile
        reset_database_manager()

        logger.info(f"Successfully connected to database: {profile.value}")

        return ConnectDatabaseResponse(
            success=True,
            database=_profile_to_info(profile, config, profile),
            message=f"Successfully connected to {config.display_name}",
        )

    except Exception as e:
        logger.error(f"Failed to connect to database {database_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to {config.display_name}: {str(e)}",
        )
