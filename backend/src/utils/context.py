"""Context variables for runtime context management.

Provides thread-local context variables that can be accessed by tools
without requiring explicit parameter passing. This allows tools to access
runtime context like thread_id without modifying tool signatures.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

# Context variable for thread_id (conversation thread identifier)
# Format: user_id:conversation_id (e.g., "anonymous:abc123")
thread_id_context: ContextVar[Optional[str]] = ContextVar("thread_id", default=None)

# Context variable for database_id (active database profile)
# Format: lowercase profile name (e.g., "clinvar", "gwas")
database_id_context: ContextVar[Optional[str]] = ContextVar("database_id", default=None)
