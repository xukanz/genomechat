"""Checkpointer factory for LangGraph state persistence.

Supports MongoDB (production) and SQLite (testing) with easy extension to Postgres.
"""

import logging
from typing import AsyncContextManager
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver

from src.config.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def create_checkpointer() -> AsyncContextManager[BaseCheckpointSaver]:
    """Create and return a checkpointer based on settings.

    Supports MongoDB (production) and SQLite (testing).
    The checkpointer is returned as an async context manager for proper resource cleanup.

    Yields:
        Checkpointer instance (async context manager)

    Usage:
        async with create_checkpointer() as checkpointer:
            agent = graph_builder.compile(checkpointer=checkpointer)
            result = await agent.ainvoke(input, config=config)

    Raises:
        ValueError: If checkpointer type is unknown or required settings are missing
    """
    checkpointer_type = getattr(settings, "checkpointer_type", "mongodb").lower()

    if checkpointer_type == "mongodb":
        from langgraph.checkpoint.mongodb import MongoDBSaver
        from src.service.database.connections.mongodb_connection import get_mongodb_client

        db_name = getattr(settings, "mongodb_db_name", "langgraph_checkpoints")

        logger.info(f"Creating MongoDB checkpointer: database={db_name}")
        # Use shared MongoDB client from service/database/connections
        client = get_mongodb_client()
        checkpointer = MongoDBSaver(client, db_name=db_name)

        # Yield checkpointer - client is singleton, don't close it here
        yield checkpointer

    elif checkpointer_type == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        from src.graph.builder import get_checkpointer_db_path

        db_path = get_checkpointer_db_path()
        logger.info(f"Creating SQLite checkpointer: {db_path}")

        async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
            yield checkpointer

    else:
        raise ValueError(
            f"Unknown checkpointer type: {checkpointer_type}. Supported types: 'mongodb', 'sqlite'"
        )
