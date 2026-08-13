# AGENTS.md

This file provides guidance to Cursor agents when working with code in this repository.

## 📦 Monorepo Structure

This is a full-stack platform monorepo with Python backends and React frontends:

```
genomechat/
├── backend/                     # Platform backend services (FastAPI + LangGraph)
│   ├── src/config/              # Settings, database registry, path resolution
│   └── databases/               # Built database artifacts (ClinVar SQLite, GWAS Parquet)
├── frontend/                    # Platform frontend (React + TypeScript + Vite)
│   └── src/components/databases/ # Database switching UI
├── sandbox/                     # Code execution sandbox environment
├── docker/                      # Docker Compose files (dev + prod)
├── docs/                        # Documentation (backend)
├── AGENTS.md                    # Agent development guide
└── CLAUDE.md                    # This file - development guidance
```

**Key Components:**
- **backend/**: Platform backend services (FastAPI + LangGraph)
- **frontend/**: Platform frontend services

## Core Development Philosophy

### KISS (Keep It Simple, Stupid)
Simplicity should be a key goal in design. Choose straightforward solutions over complex ones whenever possible.

### YAGNI (You Aren't Gonna Need It)
Avoid building functionality on speculation. Implement features only when they are needed.

### Design Principles
- **Dependency Inversion**: High-level modules should not depend on low-level modules. Both should depend on abstractions.
- **Open/Closed Principle**: Software entities should be open for extension but closed for modification.
- **Single Responsibility**: Each function, class, and module should have one clear purpose.
- **Fail Fast**: Check for potential errors early and raise exceptions immediately when issues occur.

## 🧱 Code Structure & Modularity

### File and Function Limits
- **Never create a file longer than 500 lines of code**. Refactor by splitting into modules.
- **Python functions should be under 50 lines** with a single, clear responsibility.
- **TypeScript/React components should be under 200 lines**. Extract hooks and utilities.
- **Classes should be under 100 lines** and represent a single concept or entity.
- **Line length: 100 characters** for Python (Ruff), default for TypeScript (ESLint).

### Project Architecture
- Follow strict vertical slice architecture with tests living next to the code they test
- Use feature-based folder structure for React components
- Keep AI agent logic modular and testable

## 🐍 Python Development

### UV Package Management

This project uses UV for blazing-fast Python package and environment management.

```bash
# Sync dependencies
uv sync

# Add a package ***NEVER UPDATE PYPROJECT.TOML DIRECTLY***
# ALWAYS USE UV ADD
uv add requests
uv add --dev pytest ruff mypy

# Remove a package
uv remove requests

# Run commands in the environment
uv run python script.py
uv run pytest
uv run ruff check .
```

### Python Development Commands

```bash
# Testing
uv run pytest                                    # Run all tests
uv run pytest tests/test_module.py -v           # Run specific tests
uv run pytest --cov=src --cov-report=html       # Tests with coverage

# Code Quality
uv run ruff format .                             # Format code
uv run ruff check .                              # Check linting
uv run ruff check --fix .                        # Fix linting issues
uv run mypy src/                                 # Type checking
```

### Python Style Guide
- **Follow PEP8**:
  - Line length: 100 characters (set by Ruff in pyproject.toml)
  - Use double quotes for strings
  - Use trailing commas in multi-line structures
- **Always use type hints** for function signatures and class attributes
- **Format with `ruff format`** (faster alternative to Black)
- **Use `pydantic` v2** for data validation and settings management

### Python Naming Conventions
- **Variables and functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private attributes/methods**: `_leading_underscore`
- **Type aliases**: `PascalCase`
- **Enum values**: `UPPER_SNAKE_CASE`

## ⚛️ React/TypeScript Development

### Frontend Development Commands

```bash
# Platform frontend (primary)
cd frontend

# Install dependencies
npm install

# Development server
npm run dev                    # Starts Vite dev server on http://localhost:5173

# Build
npm run build                  # TypeScript compile + Vite build

# Linting and Type Checking
npm run lint                   # ESLint
npm run type-check             # TypeScript type checking

# Preview production build
npm run preview
```

### React/TypeScript Conventions
- **Use TypeScript** for all new code (strict mode enabled)
- **Component structure**:
  - Functional components with hooks
  - Custom hooks in `hooks/` directory
  - State management with Zustand (lightweight alternative to Redux)
- **Naming conventions**:
  - Components: `PascalCase.tsx`
  - Hooks: `use*.ts` (e.g., `useChat.ts`)
  - Utilities: `camelCase.ts`
  - Constants: `UPPER_SNAKE_CASE`
- **Import order**: React → Third-party → Local components → Utilities → Types
- **Props**: Always define TypeScript interfaces for component props

### React Best Practices
- Extract business logic into custom hooks
- Keep components focused on presentation
- Use `React.memo()` for expensive components
- Leverage Server-Sent Events (SSE) for streaming responses
- Use Zustand for global state, useState for local state

### Frontend State Management (Zustand Stores)
- `authStore.ts` - Authentication state and user session
- `conversationStore.ts` - Chat conversations and messages
- `projectStore.ts` - Project management and organization
- `databaseStore.ts` - Database profiles and active database switching
- `artifactStore.ts` - Generated artifacts (code, files, visualizations)
- `feedbackStore.ts` - User feedback state and submissions
- `reportStore.ts` - Report generation and management
- `snippetStore.ts` - Code snippet management
- `uiStore.ts` - UI state (sidebar, modals, preferences)

## 🧪 Testing Strategy

### Python Testing
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_agent.py -v
```

### Test Organization
- **Unit tests**: Test individual functions/methods in isolation
- **Integration tests**: Test component interactions
- **End-to-end tests**: Test complete user workflows
- Keep test files next to the code they test (vertical slice)
- Use `conftest.py` for shared fixtures
- Aim for 80%+ code coverage, focus on critical paths

### Test-Driven Development (TDD)
1. **Write the test first** - Define expected behavior before implementation
2. **Watch it fail** - Ensure the test actually tests something
3. **Write minimal code** - Just enough to make the test pass
4. **Refactor** - Improve code while keeping tests green
5. **Repeat** - One test at a time

## 🐳 Docker & Deployment

### Docker Development

```bash
# Development mode (with hot-reload)
cd docker
docker-compose up -d

# Production mode
cd docker
docker-compose -f docker-compose.prod.yml up -d

# Build individual images
docker build -t genomechat-backend:v1 backend/
docker build -t genomechat-frontend:v1 frontend/
docker build -t genomechat-sandbox:v1 sandbox/
```

### Kubernetes Deployment

The application is container-ready for Kubernetes deployment:

1. **Backend Deployment**:
   - Directory: `backend/`
   - Environment variables use semicolon (`;`) separator
   - Required: `OPENAI_BEDROCK_API_KEY;OPENAI_BEDROCK_SLUG` (the pre-rename
     `PORTKEY_*` names are still accepted, so existing secrets keep working)
   - Automatic HTTPS/TLS via Kubernetes Ingress

2. **Frontend Deployment**:
   - Directory: `frontend/`
   - API URL supports **runtime injection** (build once, deploy anywhere)
   - Set `VITE_API_URL` at deployment time via environment variable or Vault Secrets

3. **Vault Secrets (Production)**:
   - Set `USE_VAULT_SECRETS=true` in environment variables
   - Secrets mounted at `/secrets/secret.yaml`
   - Secrets override environment variables when both present

**Key Features:**
- 🔒 Automatic HTTPS/TLS via Kubernetes Ingress
- 🔄 Auto-restart on failure
- 🏥 Health probes every ~15 seconds
- 🌐 Configurable CORS via CORS_ORIGINS and the optional CORS_ORIGIN_REGEX
- 🗄️ Vault Secrets support for secure credential management
- 🔄 Runtime API URL injection (no rebuild needed to change backend URL)


### API Route Standards
```python
# ✅ RESTful with consistent parameter naming
router = APIRouter(prefix="/api/v1/leads", tags=["leads"])

@router.get("/{lead_id}")           # GET /api/v1/leads/{lead_id}
@router.put("/{lead_id}")           # PUT /api/v1/leads/{lead_id}
@router.delete("/{lead_id}")        # DELETE /api/v1/leads/{lead_id}

# Sub-resources
@router.get("/{lead_id}/messages")  # GET /api/v1/leads/{lead_id}/messages
```

### Backend API Routes (`backend/src/api/routes/`)
- `health.py` - Health check endpoint
- `auth.py` - Authentication (login, register, session management)
- `chat.py` - Main chat/streaming endpoints (SSE)
- `conversations.py` - Conversation CRUD and history
- `projects.py` - Project management (create, update, delete, list)
- `databases.py` - Database profile listing and runtime switching
- `artifacts.py` - Artifact management (code, files, visualizations)
- `feedback.py` - User feedback collection and management
- `reports.py` - Report generation and management
- `users.py` - User profile management

## 🌐 API Patterns

### FastAPI with Server-Sent Events (SSE)

The platform uses SSE for real-time streaming responses:

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    """Stream LLM responses via Server-Sent Events."""
    async def event_generator():
        async for chunk in agent.astream(request.message):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### CORS Configuration
```python
# CORS: exact origins plus an optional wildcard regex
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,   # optional; unset by default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🔄 Git Workflow

### Branch Strategy
- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation updates
- `refactor/*` - Code refactoring
- `test/*` - Test additions or fixes

### Commit Message Format

Never include "claude code" or "written by claude code" in commit messages.

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, test, chore

Example:
```
feat(agent): add streaming response support

- Implement SSE for real-time chat streaming
- Add LangGraph checkpointing for state persistence
- Update frontend to handle streaming events

Closes #123
```

### Daily Workflow
1. `git checkout main && git pull origin main`
2. `git checkout -b feature/new-feature`
3. Make changes + tests
4. `git push origin feature/new-feature`
5. Create PR → Review → Merge to main

## ⚠️ Critical Rules

- **NEVER ASSUME OR GUESS** - When in doubt, ask for clarification
- **Always verify file paths and module names** before use
- **Test your code** - No feature is complete without tests
- **Never commit secrets** - Use environment variables (.env files)
- **Use UV for Python packages** - Never manually edit pyproject.toml

## 🔍 Search Command Requirements

**CRITICAL**: Always use `rg` (ripgrep) instead of traditional `grep` and `find` commands:

```bash
# ✅ Use rg instead of grep
rg "pattern"

# ✅ Use rg with file filtering instead of find
rg --files -g "*.py"
rg --files -g "*.tsx"
```

## 🎯 Agent Skills Management

This project uses Claude Code Agent Skills for modular, specialized knowledge. Skills activate automatically based on your task.

### Available Skills

Located in `.claude/skills/`:
- **python-development**: Testing, error handling, Pydantic, security
- **database-operations**: Naming standards, repositories, API routes
- **debugging-performance**: Profiling, optimization, monitoring
- **documentation-standards**: Docstrings, API docs, code comments
- **agent-development**: LangGraph, multi-agent patterns, workflows
- **subagent-creation**: Creating and managing Claude Code subagents
- **skill-authoring**: Creating effective Claude Code Agent Skills

### Updating Skills

**When to update a skill**:
- ✅ Discovered a better practice or pattern
- ✅ Found a more efficient tool or library
- ✅ Project conventions changed
- ✅ New pattern emerged from code reviews

Skills are **living documentation** that capture team knowledge. Update them when you learn something new.

---

_This document is a living guide. Update it as the project evolves and new patterns emerge._
