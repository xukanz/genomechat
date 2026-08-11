"""CLI authentication utilities and token storage."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


class TokenStorage:
    """Manages authentication token storage for CLI."""

    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize token storage.

        Args:
            storage_dir: Directory to store tokens (defaults to ~/.genomechat)
        """
        if storage_dir is None:
            # Use home directory for persistent storage
            home = Path.home()
            self.storage_dir = home / ".genomechat"
        else:
            self.storage_dir = Path(storage_dir)

        self.token_file = self.storage_dir / "tokens.json"
        self._ensure_storage_dir()

    def _ensure_storage_dir(self) -> None:
        """Create storage directory if it doesn't exist."""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            # Set directory permissions to 700 (owner only)
            os.chmod(self.storage_dir, 0o700)
        except Exception as e:
            logger.warning(f"Failed to create storage directory: {e}")

    def save_tokens(
        self, access_token: str, refresh_token: str, user_email: Optional[str] = None
    ) -> None:
        """Save authentication tokens to file.

        Args:
            access_token: JWT access token
            refresh_token: JWT refresh token
            user_email: Optional user email for reference
        """
        try:
            token_data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user_email": user_email,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }

            # Write to file atomically
            temp_file = self.token_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(token_data, f, indent=2)

            # Move temp file to final location
            temp_file.replace(self.token_file)

            # Set file permissions to 600 (read/write owner only)
            os.chmod(self.token_file, 0o600)

            logger.debug(f"Tokens saved to {self.token_file}")

        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")
            raise

    def load_tokens(self) -> Tuple[Optional[str], Optional[str]]:
        """Load authentication tokens from file.

        Returns:
            Tuple of (access_token, refresh_token) or (None, None) if not found
        """
        try:
            if not self.token_file.exists():
                return None, None

            with open(self.token_file, "r") as f:
                token_data = json.load(f)

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")

            return access_token, refresh_token

        except Exception as e:
            logger.warning(f"Failed to load tokens: {e}")
            return None, None

    def clear_tokens(self) -> None:
        """Clear stored tokens."""
        try:
            if self.token_file.exists():
                self.token_file.unlink()
                logger.debug("Tokens cleared")
        except Exception as e:
            logger.warning(f"Failed to clear tokens: {e}")

    def get_token_file_path(self) -> Path:
        """Get the path to the token file.

        Returns:
            Path to token file
        """
        return self.token_file


async def login(api_url: str, email: str, password: str) -> Tuple[bool, str, Optional[dict]]:
    """Login and get authentication tokens.

    Args:
        api_url: Base URL of the API server
        password: User password

    Returns:
        Tuple of (success, message, token_response_dict)
        token_response_dict contains tokens and user info on success
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/auth/login",
                data={"username": email, "password": password},
            )

            if response.status_code == 200:
                data = response.json()
                return True, "Login successful", data
            else:
                error_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_msg = error_data.get("detail", f"Login failed: {response.status_code}")
                return False, error_msg, None

    except httpx.RequestError as e:
        return False, f"Connection error: {e}", None
    except Exception as e:
        return False, f"Unexpected error: {e}", None


async def register(
    api_url: str, email: str, name: str, password: str
) -> Tuple[bool, str, Optional[dict]]:
    """Register a new user and get authentication tokens.

    Args:
        api_url: Base URL of the API server
        email: User email
        name: User name
        password: User password

    Returns:
        Tuple of (success, message, token_response_dict)
        token_response_dict contains tokens and user info on success
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/auth/register",
                json={"email": email, "name": name, "password": password},
            )

            if response.status_code == 201:
                data = response.json()
                return True, "Registration successful", data
            else:
                error_data = (
                    response.json()
                    if response.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                error_msg = error_data.get("detail", f"Registration failed: {response.status_code}")
                return False, error_msg, None

    except httpx.RequestError as e:
        return False, f"Connection error: {e}", None
    except Exception as e:
        return False, f"Unexpected error: {e}", None


async def get_current_user(api_url: str, access_token: str) -> Optional[dict]:
    """Get current user information.

    Args:
        api_url: Base URL of the API server
        access_token: JWT access token

    Returns:
        User info dict or None if request fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{api_url.rstrip('/')}/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code == 200:
                return response.json()
            return None

    except Exception:
        return None


async def refresh_access_token(api_url: str, refresh_token: str) -> Optional[dict]:
    """Refresh access token using refresh token.

    Args:
        api_url: Base URL of the API server
        refresh_token: JWT refresh token

    Returns:
        Token response dict with new tokens or None if refresh fails
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{api_url.rstrip('/')}/auth/refresh",
                json={"refresh_token": refresh_token},
            )

            if response.status_code == 200:
                return response.json()
            return None

    except Exception:
        return None
