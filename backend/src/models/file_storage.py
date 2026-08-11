"""Unified file storage data models.

Tracks all S3 files created by the system (SQL query results, coder outputs, analyses, etc.)
in a single MongoDB collection with consistent metadata structure.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class FileType(str, Enum):
    """File type classification for tracking purposes."""

    QUERY_RESULT = "query_result"  # SQL query results
    CODER_OUTPUT = "coder_output"  # Files created by coder agent
    ANALYSIS = "analysis"  # Analysis results, visualizations, reports
    OTHER = "other"  # Any other file types


class FileRecord(BaseModel):
    """File record metadata model for MongoDB storage."""

    file_id: str = Field(..., description="Short UUID identifier for the file")
    user_id: Optional[str] = Field(None, description="User ID who owns the file")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    file_type: FileType = Field(..., description="Type of file (query_result, coder_output, etc.)")
    s3_bucket: str = Field(..., description="S3 bucket name")
    s3_key: str = Field(..., description="S3 object key (file path)")
    content_type: str = Field(..., description="File content type (csv, json, png, py, etc.)")
    size_bytes: int = Field(..., description="File size in bytes")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Type-specific metadata")
    created_at: datetime = Field(..., description="File creation timestamp")


class FileRecordCreate(BaseModel):
    """Request model for creating a file record."""

    user_id: Optional[str] = Field(None, description="User ID who owns the file")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    file_type: FileType = Field(..., description="Type of file")
    s3_bucket: str = Field(..., description="S3 bucket name")
    s3_key: str = Field(..., description="S3 object key (file path)")
    content_type: str = Field(..., description="File content type")
    size_bytes: int = Field(..., description="File size in bytes")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Type-specific metadata")


class ArtifactResponse(BaseModel):
    """Response model for artifact with conversation metadata."""

    file_id: str = Field(..., description="Short UUID identifier for the file")
    user_id: Optional[str] = Field(None, description="User ID who owns the file")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID extracted from thread_id"
    )
    conversation_title: Optional[str] = Field(None, description="Title of the conversation")
    file_type: FileType = Field(..., description="Type of file (query_result, coder_output, etc.)")
    s3_bucket: str = Field(..., description="S3 bucket name")
    s3_key: str = Field(..., description="S3 object key (file path)")
    content_type: str = Field(..., description="File content type (csv, json, png, py, etc.)")
    size_bytes: int = Field(..., description="File size in bytes")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Type-specific metadata")
    created_at: datetime = Field(..., description="File creation timestamp")


class ArtifactListResponse(BaseModel):
    """Response model for listing artifacts."""

    artifacts: list[ArtifactResponse] = Field(..., description="List of artifacts")
    count: int = Field(..., description="Total count of artifacts")


class DownloadUrlResponse(BaseModel):
    """Response model for presigned download URL."""

    download_url: str = Field(..., description="Presigned S3 URL for downloading the file")
    expires_in: int = Field(..., description="URL expiration time in seconds")


class BatchDownloadUrlRequest(BaseModel):
    """Request model for batch presigned URL generation."""

    file_ids: list[str] = Field(
        ...,
        description="List of file IDs to generate download URLs for",
        min_length=1,
        max_length=100,
    )
    expires_in: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="URL expiration time in seconds (1 min to 24 hours)",
    )


class BatchDownloadUrlItem(BaseModel):
    """Single item in batch download URL response."""

    file_id: str = Field(..., description="File ID")
    download_url: Optional[str] = Field(
        None, description="Presigned URL (null if not found/authorized)"
    )


class BatchDownloadUrlResponse(BaseModel):
    """Response model for batch presigned URL generation."""

    urls: list[BatchDownloadUrlItem] = Field(
        ..., description="List of file IDs with their download URLs"
    )
    expires_in: int = Field(..., description="URL expiration time in seconds")
