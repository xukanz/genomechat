"""Main entry point for the FastAPI application."""

from src.api.app import app
from src.api.routes import (
    auth,
    chat,
    databases,
    health,
    conversations,
    artifacts,
    projects,
    reports,
    feedback,
    users,
)
from src.config.settings import settings

# Register routes
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(databases.router)
app.include_router(conversations.router)
app.include_router(artifacts.router)
app.include_router(projects.router)
app.include_router(reports.router)
app.include_router(feedback.router)
app.include_router(users.router)

# Phase 0: internal observability endpoints (default-on; gate via settings)
if settings.internal_observability_enabled:
    from src.api.routes import internal_memory, internal_traces

    app.include_router(internal_traces.router)
    app.include_router(internal_memory.router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    from src.config.settings import settings

    return {
        "name": "GenomeChat Platform API",
        "version": settings.api_version,
        "endpoints": {
            "health": "/health",
            "auth": {
                "register": "/auth/register",
                "login": "/auth/login",
                "refresh": "/auth/refresh",
                "me": "/auth/me",
                "logout": "/auth/logout",
            },
            "chat": "/chat",
            "stream": "/chat/stream",
            "conversations": {
                "list": "/conversations",
                "get": "/conversations/{id}",
                "history": "/conversations/{id}/history",
                "update": "/conversations/{id}",
                "delete": "/conversations/{id}",
            },
            "artifacts": {
                "list": "/artifacts",
                "download": "/artifacts/{file_id}/download",
            },
            "projects": {
                "list": "/projects",
                "create": "/projects",
                "get": "/projects/{id}",
                "update": "/projects/{id}",
                "delete": "/projects/{id}",
                "move_conversation": "/projects/{id}/conversations/{conversation_id}/move",
            },
            "reports": {
                "list": "/reports",
                "create": "/reports",
                "get": "/reports/{id}",
                "update": "/reports/{id}",
                "delete": "/reports/{id}",
            },
            "feedback": {
                "create_or_update": "/feedback",
                "list_conversation": "/feedback/conversation/{id}",
                "get_message": "/feedback/message",
                "delete": "/feedback/{id}",
                "delete_by_message": "/feedback/message/{conversation_id}/{message_index}",
            },
            "users": {
                "search": "/users/search?q={query}",
            },
        },
    }


if __name__ == "__main__":
    import uvicorn
    from src.config.settings import settings

    # Suppress uvicorn access logs in development (too verbose)
    log_config = None
    if settings.environment == "development":
        # Custom log config: only show errors and warnings from uvicorn
        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "uvicorn": {"level": "INFO", "handlers": ["default"], "propagate": False},
                "uvicorn.error": {"level": "INFO", "handlers": ["default"], "propagate": False},
                "uvicorn.access": {"level": "WARNING", "handlers": ["default"], "propagate": False},
            },
            "root": {"level": settings.log_level.upper(), "handlers": ["default"]},
        }

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_config=log_config,
    )
