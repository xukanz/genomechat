"""Snippet data models for project-scoped code examples."""

from datetime import datetime
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, Field


SnippetCategory = Literal[
    "visualization",  # Plotting patterns
    "data_processing",  # Data cleaning, transformation
    "statistics",  # Statistical analysis patterns
    "file_operations",  # S3, file handling patterns
    "domain_specific",  # TCR analysis, immunology pipelines
    "custom",  # User-defined
]


class Snippet(BaseModel):
    """Code snippet model stored within project document."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100)
    category: SnippetCategory = "custom"
    description: Optional[str] = Field(None, max_length=500)
    code: str = Field(..., min_length=1, max_length=10000)  # 10KB limit
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SnippetCreate(BaseModel):
    """Request model for creating a snippet."""

    name: str = Field(..., min_length=1, max_length=100)
    category: SnippetCategory = "custom"
    description: str = Field(..., min_length=1, max_length=500)
    code: str = Field(..., min_length=1, max_length=10000)
    enabled: bool = True


class SnippetUpdate(BaseModel):
    """Request model for updating a snippet."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[SnippetCategory] = None
    description: Optional[str] = Field(None, max_length=500)
    code: Optional[str] = Field(None, min_length=1, max_length=10000)
    enabled: Optional[bool] = None


class SnippetList(BaseModel):
    """Response model for listing snippets."""

    snippets: list[Snippet]
    count: int
