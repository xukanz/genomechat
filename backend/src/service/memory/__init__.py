"""Memory pipeline public API (Phase 0.5).

Import from `src.service.memory`, not sub-modules, so the surface stays stable
if we refactor internals. All callable entry points are exposed via `__getattr__`
so import-time doesn't require every sub-module to be present — avoids a
cascading failure if e.g. `langchain_core` is unavailable in a dev env that
only needs schema + redaction.
"""

from __future__ import annotations

from typing import Any

from src.service.memory.schema import (
    Memory,
    MemoryInsight,
    RetrievedMemory,
)

__all__ = [
    "Memory",
    "MemoryInsight",
    "RetrievedMemory",
    "ensure_indexes",
    "extract_memories_for_turn",
    "retrieve_memories",
    "run_consolidation",
]


def __getattr__(name: str) -> Any:
    if name == "ensure_indexes":
        from src.service.memory.indexes import ensure_indexes

        return ensure_indexes
    if name == "extract_memories_for_turn":
        from src.service.memory.extractor import extract_memories_for_turn

        return extract_memories_for_turn
    if name == "retrieve_memories":
        from src.service.memory.retriever import retrieve_memories

        return retrieve_memories
    if name == "run_consolidation":
        from src.service.memory.consolidator import run_consolidation

        return run_consolidation
    raise AttributeError(f"module 'src.service.memory' has no attribute {name!r}")
