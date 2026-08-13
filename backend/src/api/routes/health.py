"""Health check endpoint."""

import logging
from typing import Any

from fastapi import APIRouter

from src.config.settings import settings
from src.models.api import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns:
        Health status of the service
    """
    return HealthResponse(status="healthy", version=settings.api_version)


@router.get("/detailed")
async def detailed_health_check() -> dict[str, Any]:
    """Detailed health check with service connectivity status.

    Returns:
        Detailed health status including MongoDB, Sandbox, etc.
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "version": settings.api_version,
        "services": {},
    }

    # Check MongoDB
    try:
        from src.service.database.connections.mongodb_connection import MongoDBConnection

        mongo = MongoDBConnection()
        client = mongo.connect()
        # Ping the server to verify connection
        client.admin.command("ping")
        db = mongo.get_database()
        collections = db.list_collection_names()
        health_status["services"]["mongodb"] = {
            "status": "connected",
            "database": mongo.db_name,
            "collections": collections[:10],  # Show first 10 collections
            "collection_count": len(collections),
        }
    except Exception as e:
        health_status["services"]["mongodb"] = {
            "status": "error",
            "error": str(e),
        }
        health_status["status"] = "degraded"
        logger.error(f"MongoDB health check failed: {e}")

    # Check Sandbox connectivity
    try:
        import httpx

        sandbox_url = getattr(settings, "sandbox_url", None)
        if sandbox_url:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{sandbox_url.rstrip('/')}/health")
                if response.status_code == 200:
                    health_status["services"]["sandbox"] = {
                        "status": "connected",
                        "url": sandbox_url,
                    }
                else:
                    health_status["services"]["sandbox"] = {
                        "status": "error",
                        "url": sandbox_url,
                        "http_status": response.status_code,
                    }
                    health_status["status"] = "degraded"
        else:
            health_status["services"]["sandbox"] = {"status": "not_configured"}
    except Exception as e:
        health_status["services"]["sandbox"] = {
            "status": "error",
            "error": str(e),
        }
        health_status["status"] = "degraded"
        logger.error(f"Sandbox health check failed: {e}")

    # Show configuration (redacted)
    health_status["config"] = {
        "environment": getattr(settings, "environment", "unknown"),
        "mongodb_configured": bool(
            getattr(settings, "mongodb_uri", None)
            or getattr(settings, "mongodb_connection_string", None)
        ),
        "sandbox_configured": bool(getattr(settings, "sandbox_url", None)),
        "openai_configured": bool(getattr(settings, "openai_api_key", None)),
    }

    return health_status
