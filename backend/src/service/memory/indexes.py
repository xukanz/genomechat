"""Create MongoDB collections + indexes for the memory pipeline.

Called once from the FastAPI lifespan. Every operation is idempotent; repeated
startup is harmless.

Atlas Search (`$vectorSearch`) is entitlement-gated — on Community Edition the
`createSearchIndexes` command returns `CommandNotFound`. We catch this and
continue so dev/CI environments don't fail startup; retrieval falls back to
brute-force cosine when the index is missing (see `retriever.py`).
"""

from __future__ import annotations

import logging

from pymongo.errors import OperationFailure

from src.config.settings import settings
from src.service.database.connections.mongodb_connection import get_mongodb_client
from src.service.memory.schema import memory_index_specs, vector_search_index_spec

logger = logging.getLogger(__name__)


async def ensure_indexes() -> None:
    """Create/verify indexes for the memory collections. Safe to call repeatedly."""
    client = get_mongodb_client()
    db = client[settings.mongodb_db_name]

    specs = memory_index_specs(
        dimensions=settings.memory_embedding_dimensions,
        ttl_days=settings.memory_ttl_days,
    )

    for collection_name, index_list in specs.items():
        coll = db[collection_name]
        for spec in index_list:
            kwargs = {k: v for k, v in spec.items() if k != "keys"}
            try:
                coll.create_index(spec["keys"], **kwargs)
            except OperationFailure:
                logger.debug(
                    "ensure_indexes: non-fatal failure on %s.%s",
                    collection_name,
                    spec.get("name", "?"),
                    exc_info=True,
                )

    if settings.memory_atlas_vector_search_enabled:
        vector_spec = vector_search_index_spec(settings.memory_embedding_dimensions)
        try:
            db.command(
                {
                    "createSearchIndexes": "research_memories",
                    "indexes": [vector_spec],
                }
            )
            logger.info("ensure_indexes: Atlas vector-search index ready")
        except OperationFailure as exc:
            # CommandNotFound on Community Edition or duplicate-name on rerun
            msg = str(exc).lower()
            if "commandnotfound" in msg or "not supported" in msg:
                logger.warning(
                    "ensure_indexes: Atlas $vectorSearch unavailable — "
                    "falling back to brute-force cosine retrieval"
                )
            else:
                logger.debug("ensure_indexes: createSearchIndexes raised", exc_info=True)
        except Exception:
            logger.debug("ensure_indexes: createSearchIndexes unexpected error", exc_info=True)
