# Backend Dockerfile
# Production-ready FastAPI + LangGraph multi-agent platform

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install UV for fast dependency management
RUN pip install --no-cache-dir uv

# Suppress UV hardlink warnings in containerized environments
ENV UV_LINK_MODE=copy

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install Python dependencies with UV (production only)
# --no-dev: Skip development dependencies (mypy, ruff, pytest, etc.)
# --frozen: Use exact lock file versions
RUN uv sync --no-dev --frozen

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Production: Use Gunicorn with Uvicorn workers for better memory management
# --workers 8: Sized for an 8Gi memory allocation (adjust to your platform)
# --worker-class uvicorn.workers.UvicornWorker: Use async workers
# --timeout 120: Allow time for LangGraph agent processing
# --bind 0.0.0.0:8000: Listen on all interfaces
CMD ["uv", "run", "gunicorn", "main:app", \
     "--workers", "8", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--bind", "0.0.0.0:8000"]
