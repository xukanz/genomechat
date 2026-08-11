"""Centralized path resolution for multi-environment deployments.

Provides consistent path resolution across local development, Docker,
and Kubernetes deployments.

Resolution order for all paths:
1. Environment variable override (if specified)
2. Absolute path (used as-is)
3. Relative path from application root

Application root resolution:
1. APP_ROOT environment variable
2. Current working directory (Docker-friendly)
"""

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@lru_cache
def get_app_root() -> Path:
    """Get application root directory.

    Resolution order:
    1. APP_ROOT env var (explicit override for any deployment)
    2. Current working directory (works for Docker with WORKDIR)

    Returns:
        Path to application root directory
    """
    if app_root := os.getenv("APP_ROOT"):
        resolved = Path(app_root)
        logger.debug(f"App root from APP_ROOT env: {resolved}")
        return resolved

    resolved = Path.cwd()
    logger.debug(f"App root from cwd: {resolved}")
    return resolved


def resolve_path(
    relative_path: str,
    env_override_var: Optional[str] = None,
    must_exist: bool = False,
) -> Path:
    """Resolve a path with optional environment variable override.

    Args:
        relative_path: Default path relative to app root
        env_override_var: Environment variable name for override (without prefix)
        must_exist: If True, raises FileNotFoundError if path doesn't exist

    Returns:
        Resolved absolute Path

    Raises:
        FileNotFoundError: If must_exist=True and path doesn't exist
    """
    paths_tried = []

    # 1. Check env override first
    if env_override_var:
        if override := os.getenv(env_override_var):
            path = Path(override)
            if path.is_absolute():
                resolved = path
            else:
                resolved = get_app_root() / path

            paths_tried.append(f"{env_override_var}={override} -> {resolved}")

            if not must_exist or resolved.exists():
                logger.debug(f"Path resolved via {env_override_var}: {resolved}")
                return resolved

    # 2. Try relative path from app root
    app_root = get_app_root()
    resolved = app_root / relative_path
    paths_tried.append(f"app_root/{relative_path} -> {resolved}")

    if must_exist and not resolved.exists():
        raise FileNotFoundError("Path not found. Tried:\n  " + "\n  ".join(paths_tried))

    logger.debug(f"Path resolved from app root: {resolved}")
    return resolved


def resolve_data_path(
    relative_path: str,
    env_override_var: Optional[str] = None,
) -> Path:
    """Resolve a data path (database files, parquet directories).

    Tries multiple resolution strategies for flexibility:
    1. Environment variable override
    2. Relative to app root (cwd)
    3. Relative to project root (fallback for local dev)

    Args:
        relative_path: Default path relative to app root
        env_override_var: Environment variable name for override

    Returns:
        Resolved absolute Path

    Raises:
        FileNotFoundError: If path cannot be resolved
    """
    paths_tried = []

    # 1. Check env override first
    if env_override_var:
        if override := os.getenv(env_override_var):
            # Check if it's an S3 path (don't validate existence)
            if override.startswith("s3://"):
                logger.debug(f"S3 path from {env_override_var}: {override}")
                return Path(override)  # Return as-is for S3

            path = Path(override)
            if path.is_absolute():
                resolved = path
            else:
                resolved = get_app_root() / path

            paths_tried.append(f"{env_override_var}={override} -> {resolved}")

            if resolved.exists():
                logger.debug(f"Data path resolved via {env_override_var}: {resolved}")
                return resolved

    # 2. Try relative to app root (cwd) - Docker friendly
    app_root = get_app_root()
    resolved = app_root / relative_path
    paths_tried.append(f"app_root/{relative_path} -> {resolved}")

    if resolved.exists():
        logger.debug(f"Data path resolved from app root: {resolved}")
        return resolved

    # 3. Fallback: relative to this file's project root (local dev)
    # Go up from src/config/paths.py to backend/
    project_root = Path(__file__).parent.parent.parent
    fallback = project_root / relative_path
    if fallback != resolved:  # Avoid duplicate check
        paths_tried.append(f"project_root/{relative_path} -> {fallback}")
        if fallback.exists():
            logger.debug(f"Data path resolved from project root: {fallback}")
            return fallback

    raise FileNotFoundError("Data path not found. Tried:\n  " + "\n  ".join(paths_tried))


def is_s3_path(path: str | Path) -> bool:
    """Check if a path is an S3 URI.

    Args:
        path: Path string or Path object

    Returns:
        True if path starts with s3://
    """
    path_str = str(path)
    return path_str.startswith("s3://")
