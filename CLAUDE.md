# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🧱 Code Structure & Modularity

### File and Function Limits
- **Never create a file longer than 500 lines of code**. Refactor by splitting into modules.
- **Python functions should be under 50 lines** with a single, clear responsibility.
- **TypeScript/React components should be under 200 lines**. Extract hooks and utilities.
- **Classes should be under 100 lines** and represent a single concept or entity.

### Project Architecture
- Follow strict vertical slice architecture — **tests live next to the code they test**, not in a
  separate top-level `tests/` tree.
- Use feature-based folder structure for React components.
- Keep AI agent logic modular and testable.

## 🐍 Python Development

- **Use UV for Python packages.** ***NEVER UPDATE `pyproject.toml` DIRECTLY*** — always use
  `uv add` / `uv add --dev` / `uv remove`.
- Run everything through the environment: `uv run pytest`, `uv run ruff check .`, `uv run mypy src/`.
- Use **Pydantic v2** for data validation and settings management.
- Always use type hints for function signatures and class attributes.

Formatting and line length are enforced by Ruff — see `[tool.ruff]` in `backend/pyproject.toml`.

## ⚛️ React/TypeScript Development

- **Zustand for global state** (deliberate choice over Redux), `useState` for local state.
  Stores live in `frontend/src/store/`.
- Extract business logic into custom hooks; keep components focused on presentation.
- Server-Sent Events (SSE) for streaming responses.

## 🐳 Deployment

Kubernetes, Vault, and runtime-config specifics live in `.claude/skills/deployment/SKILL.md`.

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

## 🎯 Agent Skills

Project skills live in `.claude/skills/` and activate automatically based on the task.

Skills are **living documentation** that capture team knowledge. Update them when you discover a
better practice, a more efficient tool, or a new pattern from code review.

---

_This document is a living guide. Update it as the project evolves and new patterns emerge._
