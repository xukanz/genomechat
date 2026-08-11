"""Report data models for bookmarked AI responses."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Report(BaseModel):
    """Report metadata model - a bookmarked AI response."""

    id: str
    user_id: str
    conversation_id: str
    conversation_title: str
    project_id: Optional[str] = None
    title: str
    content: str
    message_index: int
    created_at: datetime
    updated_at: datetime


class ReportCreate(BaseModel):
    """Request model for creating a report."""

    conversation_id: str = Field(..., description="ID of the source conversation")
    title: str = Field(..., min_length=1, max_length=200, description="Report title")
    content: str = Field(..., min_length=1, description="The AI response content to save")
    message_index: int = Field(..., ge=0, description="Index of the message in conversation")


class ReportUpdate(BaseModel):
    """Request model for updating a report."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)


class ReportList(BaseModel):
    """Response model for listing reports."""

    reports: list[Report]
    count: int
