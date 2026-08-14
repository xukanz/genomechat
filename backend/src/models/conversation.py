"""Conversation data models."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class Conversation(BaseModel):
    """Conversation metadata model."""

    id: str
    user_id: str
    title: str
    project_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversationWithMessages(Conversation):
    """Conversation model with message history."""

    messages: List[dict] = []  # List of message dictionaries from LangGraph checkpointer
    token_usage: dict | None = None  # Token usage: {estimated_tokens, max_tokens, usage_pct}


class ConversationList(BaseModel):
    """Response model for listing conversations."""

    conversations: List[Conversation]
    count: int
