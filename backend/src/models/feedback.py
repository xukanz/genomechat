"""Message feedback data models for AI response evaluation."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    """Feedback type enumeration."""

    POSITIVE = "positive"  # thumbs up
    NEGATIVE = "negative"  # thumbs down


class MessageFeedback(BaseModel):
    """Message feedback model - user rating on AI responses."""

    id: str
    user_id: str
    conversation_id: str
    message_index: int
    feedback_type: FeedbackType
    note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class MessageFeedbackCreate(BaseModel):
    """Request model for creating message feedback."""

    conversation_id: str = Field(..., description="ID of the conversation")
    message_index: int = Field(..., ge=0, description="Index of the message in conversation")
    feedback_type: FeedbackType = Field(..., description="Positive or negative feedback")
    note: Optional[str] = Field(None, max_length=1000, description="Optional note/comment")


class ConversationFeedbackEntry(BaseModel):
    """Lightweight feedback entry for batch loading."""

    feedback_id: str
    message_index: int
    feedback_type: FeedbackType


class ConversationFeedbackList(BaseModel):
    """Response model for listing feedback entries."""

    feedback: list[ConversationFeedbackEntry]
    count: int
