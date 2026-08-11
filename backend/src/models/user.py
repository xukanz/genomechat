"""User data models."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator

from src.service.auth.password import validate_password_strength


class UserCreate(BaseModel):
    """Request model for user registration."""

    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        is_valid, error_message = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_message)
        return v


class UserLogin(BaseModel):
    """Request model for user login (OAuth2 uses form, but this is for docs)."""

    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Request model for updating user profile."""

    name: str | None = Field(None, min_length=1, max_length=100)


class User(BaseModel):
    """User model (no sensitive data)."""

    id: str
    email: EmailStr
    name: str
    role: str = "user"
    created_at: datetime


class UserInDB(User):
    """User model with hashed password (for internal use only)."""

    hashed_password: str


class UserResponse(BaseModel):
    """Response model for user operations."""

    user: User
    message: str = "Success"


class TokenResponse(BaseModel):
    """Response model for authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    user: User


class RefreshTokenRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str


class UserSummary(BaseModel):
    """Minimal user info for sharing UI and search results."""

    id: str
    email: EmailStr
    name: str


class UserSearchResult(BaseModel):
    """Response model for user search."""

    users: list[UserSummary]
    count: int
