"""Project data models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.models.snippet import Snippet


class ProjectShare(BaseModel):
    """Model representing a single share record."""

    user_id: str
    user_email: str
    user_name: Optional[str] = None
    shared_by: str
    shared_at: datetime


class ProjectShareCreate(BaseModel):
    """Request model for sharing a project."""

    user_id: str = Field(..., description="ID of user to share with")


class ProjectShareList(BaseModel):
    """Response model for listing project shares."""

    shares: list[ProjectShare]
    count: int


class Project(BaseModel):
    """Project metadata model."""

    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_default: bool = False
    conversation_count: int = 0
    artifact_count: int = 0
    report_count: int = 0
    last_conversation_at: Optional[datetime] = None
    # Sharing fields
    shares: list[ProjectShare] = []
    is_owner: bool = True
    is_shared: bool = False  # True if user has shared access (not owner)
    # Code snippets field (embedded documents)
    snippets: list[Snippet] = []


class ProjectCreate(BaseModel):
    """Request model for creating a project."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ProjectUpdate(BaseModel):
    """Request model for updating a project."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class ProjectList(BaseModel):
    """Response model for listing projects."""

    projects: list[Project]
    count: int
