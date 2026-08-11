"""Query result data models.

DEPRECATED: These models are kept for backward compatibility only.
Use FileRecord and FileRecordCreate from src.models.file_storage instead.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class QueryResult(BaseModel):
    """Query result metadata model."""

    file_id: str
    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    s3_bucket: str
    s3_key: str
    query: str
    description: Optional[str] = None
    content_type: str
    row_count: int
    column_count: int
    columns: List[str]
    created_at: datetime


class QueryResultCreate(BaseModel):
    """Request model for creating a query result."""

    user_id: Optional[str] = None
    thread_id: Optional[str] = None
    query: str
    description: Optional[str] = None
    content_type: str = "data"
    row_count: int
    column_count: int
    columns: List[str]
    s3_bucket: str
    s3_key: str
