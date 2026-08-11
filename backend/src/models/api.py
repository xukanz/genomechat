"""Pydantic models for API request/response validation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.config.code_language import CodeLanguageType
from src.config.research_mode import ResearchModeType


class ChatMessage(BaseModel):
    """Single chat message.

    Represents a message in the conversation with role, content, and timestamp.
    """

    role: Literal["user", "assistant", "system"] = Field(
        ...,
        description="Role of the message sender",
    )
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Message timestamp",
    )


class ChatRequest(BaseModel):
    """Request to chat endpoint.

    Contains the user's message, optional thread ID for conversation continuity,
    and research mode for controlling research depth.
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="User message",
    )
    thread_id: str | None = Field(
        None,
        description="Optional thread ID for conversation context",
    )
    project_id: str | None = Field(
        None,
        description="Optional project ID to associate conversation with",
    )
    research_mode: ResearchModeType = Field(
        default="standard",
        description=(
            "Research mode: 'standard' for efficient direct responses, "
            "'deep_research' for comprehensive multi-faceted analysis"
        ),
    )
    code_language: CodeLanguageType = Field(
        default="python",
        description=(
            "Code language preference: 'python' for Python execution, "
            "'r' for R execution, 'auto' to let the agent decide"
        ),
    )
    database_id: str | None = Field(
        None,
        description="Database profile ID to use for this request (e.g., 'clinvar', 'gwas')",
    )


class ChatResponse(BaseModel):
    """Response from chat endpoint.

    Contains the assistant's response, thread ID, and timestamp.
    """

    message: str = Field(..., description="Assistant response")
    thread_id: str = Field(..., description="Thread ID for conversation context")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Response timestamp",
    )


class HealthResponse(BaseModel):
    """Health check response.

    Indicates the health status of the service.
    """

    status: Literal["healthy", "unhealthy"] = Field(
        ...,
        description="Service health status",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Health check timestamp",
    )
    version: str = Field(default="1.0.0", description="API version")


class StreamEvent(BaseModel):
    """Streaming event for SSE responses.

    Represents a single event in the Server-Sent Events stream.
    """

    type: Literal[
        "token", "message", "error", "end", "plan", "thinking", "agent_start", "agent_end", "file"
    ] = Field(
        ...,
        description="Event type",
    )
    content: str = Field(..., description="Event content")
    thread_id: str | None = Field(None, description="Thread ID if applicable")
    agent_name: str | None = Field(None, description="Name of the agent generating the event")
    file_metadata: dict | None = Field(None, description="File metadata for file events")
    token_usage: dict | None = Field(
        None,
        description="Token usage metadata: {estimated_tokens, max_tokens, usage_pct}",
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Event timestamp",
    )


class ErrorResponse(BaseModel):
    """Error response model.

    Used for structured error responses.
    """

    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Detailed error information")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Error timestamp",
    )
