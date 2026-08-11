---
name: documentation-standards
description: Documentation standards including Google-style docstrings, API documentation, module documentation, and code comments. Use when writing documentation, adding docstrings, or documenting APIs.
---

# Documentation Standards

## Google-Style Docstrings

### Function Documentation

```python
def calculate_discount(
    price: Decimal,
    discount_percent: float,
    min_amount: Decimal = Decimal("0.01")
) -> Decimal:
    """
    Calculate the discounted price for a product.

    Args:
        price: Original price of the product
        discount_percent: Discount percentage (0-100)
        min_amount: Minimum allowed final price

    Returns:
        Final price after applying discount

    Raises:
        ValueError: If discount_percent is not between 0 and 100
        ValueError: If final price would be below min_amount

    Example:
        >>> calculate_discount(Decimal("100"), 20)
        Decimal('80.00')
    """
```

### Class Documentation

```python
class UserRepository:
    """
    Repository for user data access operations.

    This class provides CRUD operations for User entities and handles
    all database interactions related to users.

    Attributes:
        db: Database session instance
        cache: Optional cache instance for query results

    Example:
        >>> repo = UserRepository(db_session)
        >>> user = repo.get(user_id=123)
        >>> repo.update(user, {"email": "new@example.com"})
    """

    def __init__(self, db: Session, cache: Optional[Cache] = None):
        """
        Initialize the user repository.

        Args:
            db: Database session instance
            cache: Optional cache instance for caching query results
        """
        self.db = db
        self.cache = cache
```

### Module Documentation

```python
"""
User management module.

This module provides functionality for user authentication, registration,
and profile management. It includes:

- User model definitions
- Authentication utilities
- Password hashing and verification
- Profile CRUD operations

Example:
    from src.users import authenticate_user, create_user

    user = create_user(email="user@example.com", password="secure_pass")
    authenticated = authenticate_user(email, password)
"""

from typing import Optional
from pydantic import BaseModel
# ... rest of module
```

## Code Comments

### Inline Comments

Use inline comments to explain **why**, not **what**:

```python
# ✅ Good: Explains why
# Reason: Use UTC to avoid timezone conversion issues in distributed systems
created_at = datetime.now(UTC)

# ❌ Bad: Explains what (obvious from code)
# Create a datetime object
created_at = datetime.now()
```

### Complex Logic Comments

```python
def calculate_compound_interest(principal: float, rate: float, years: int) -> float:
    """Calculate compound interest."""
    # Reason: Using continuous compounding formula (e^(rt))
    # because it provides more accurate results for daily compounding
    # compared to discrete formula
    from math import exp
    return principal * exp(rate * years)
```

### TODO Comments

```python
# TODO(username): Add retry logic for failed API calls
# Expected completion: 2024-01-15
def fetch_data(url: str):
    pass

# FIXME: Race condition when multiple workers access cache
# Issue: #123
def update_cache(key: str, value: Any):
    pass

# NOTE: This function is deprecated and will be removed in v2.0
# Use fetch_data_async() instead
def fetch_data_sync(url: str):
    pass
```

## API Documentation

### FastAPI Endpoint Documentation

```python
from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Optional

router = APIRouter(prefix="/users", tags=["users"])

@router.get(
    "/",
    response_model=List[User],
    status_code=status.HTTP_200_OK,
    summary="List all users",
    description="Retrieve a paginated list of users with optional filtering",
    responses={
        200: {
            "description": "List of users retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
                        {"id": 1, "email": "user1@example.com", "name": "User One"},
                        {"id": 2, "email": "user2@example.com", "name": "User Two"}
                    ]
                }
            }
        },
        401: {"description": "Unauthorized - Invalid or missing authentication"},
        500: {"description": "Internal server error"}
    }
)
async def list_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    active_only: bool = Query(True, description="Filter for active users only"),
    search: Optional[str] = Query(None, description="Search term for filtering by name or email")
) -> List[User]:
    """
    Retrieve a list of users with pagination and filtering.

    This endpoint supports:
    - Pagination using skip and limit parameters
    - Filtering by active status
    - Text search across name and email fields

    **Authentication**: Requires valid API key or JWT token

    **Rate Limiting**: 100 requests per minute per API key

    Args:
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return (1-1000)
        active_only: If True, only return active users
        search: Optional search term to filter by name or email

    Returns:
        List of User objects matching the criteria

    Raises:
        HTTPException: 401 if authentication fails
        HTTPException: 500 if database error occurs
    """
    # Implementation here
```

### Response Model Documentation

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class UserResponse(BaseModel):
    """
    User response model.

    This model represents a user in API responses, excluding sensitive
    information like password hashes.

    Attributes:
        id: Unique user identifier
        email: User's email address
        name: User's full name
        created_at: Account creation timestamp
        is_active: Whether the user account is active
    """

    id: int = Field(..., description="Unique user identifier", example=123)
    email: str = Field(..., description="User's email address", example="user@example.com")
    name: str = Field(..., description="User's full name", example="John Doe")
    created_at: datetime = Field(..., description="Account creation timestamp")
    is_active: bool = Field(True, description="Whether the user account is active")

    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "id": 123,
                "email": "john.doe@example.com",
                "name": "John Doe",
                "created_at": "2024-01-01T00:00:00Z",
                "is_active": True
            }
        }
```

## Project Documentation

### README.md Structure

```markdown
# Project Name

Brief description of what the project does.

## Features

- Feature 1
- Feature 2
- Feature 3

## Quick Start

\`\`\`bash
# Installation steps
uv sync

# Basic usage
uv run main.py
\`\`\`

## Documentation

- [Installation Guide](docs/installation.md)
- [API Reference](docs/api.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT License
```

### CHANGELOG.md Format

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New feature X for improved performance

### Changed
- Updated dependency Y to version 2.0

### Fixed
- Bug in feature Z causing crashes

## [1.0.0] - 2024-01-01

### Added
- Initial release
- Feature A
- Feature B

### Changed
- Refactored module C

### Deprecated
- Old API endpoint /v1/old

### Removed
- Legacy authentication method

### Fixed
- Critical security vulnerability

### Security
- Updated dependencies with security patches
```

## Documentation Best Practices

### Module-Level Documentation

Every Python module should start with a docstring:

```python
"""
Authentication and authorization module.

This module provides authentication mechanisms including:
- JWT token generation and validation
- Password hashing and verification
- Role-based access control (RBAC)
- API key management

Security considerations:
- All passwords are hashed using bcrypt
- JWT tokens expire after 24 hours
- API keys are stored with SHA-256 hashing

Example:
    from src.auth import authenticate_user, generate_token

    user = authenticate_user(email, password)
    token = generate_token(user)

See Also:
    - src.models.user: User model definitions
    - src.config.security: Security configuration
"""
```

### Complex Algorithm Documentation

```python
def calculate_tcr_similarity(seq1: str, seq2: str) -> float:
    """
    Calculate similarity between two TCR sequences using Levenshtein distance.

    This function uses the normalized Levenshtein distance to calculate
    similarity between T-cell receptor (TCR) sequences. The algorithm:

    1. Calculates edit distance (insertions, deletions, substitutions)
    2. Normalizes by the length of the longer sequence
    3. Returns similarity score (1 - normalized_distance)

    Time Complexity: O(n*m) where n and m are sequence lengths
    Space Complexity: O(n*m) for the dynamic programming matrix

    Args:
        seq1: First TCR amino acid sequence
        seq2: Second TCR amino acid sequence

    Returns:
        Similarity score between 0 and 1, where:
        - 1.0 = identical sequences
        - 0.0 = completely different sequences

    Example:
        >>> calculate_tcr_similarity("CASSLGQAYEQYF", "CASSLGQAYEQYF")
        1.0
        >>> calculate_tcr_similarity("CASSLGQAYEQYF", "CASSXGQAYEQYF")
        0.923

    References:
        Levenshtein, V. I. (1966). Binary codes capable of correcting
        deletions, insertions, and reversals. Soviet Physics Doklady, 10(8).
    """
```

### Architecture Documentation

For complex systems, include architecture documentation:

```markdown
# Architecture Overview

## System Components

\`\`\`
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Client    │────▶│   API Layer  │────▶│  Database   │
│ Application │     │   (FastAPI)  │     │ (Postgres)  │
└─────────────┘     └──────────────┘     └─────────────┘
                            │
                            ▼
                    ┌──────────────┐
                    │  Agent Layer │
                    │ (LangGraph)  │
                    └──────────────┘
\`\`\`

## Data Flow

1. Client sends request to API endpoint
2. API validates request and authenticates user
3. Agent layer processes complex operations
4. Results are stored in database
5. Response is returned to client

## Key Design Decisions

### Why FastAPI?
- Native async support for better performance
- Automatic API documentation generation
- Excellent type hint support with Pydantic

### Why LangGraph?
- Flexible agent orchestration
- Built-in state management
- Easy to test and debug
```

## Documentation Checklist

When creating or updating documentation:

- [ ] All public functions have complete docstrings
- [ ] Complex logic has explanatory comments with "Reason:" prefix
- [ ] API endpoints have full OpenAPI documentation
- [ ] README.md is up to date with latest features
- [ ] CHANGELOG.md reflects recent changes
- [ ] Module docstrings explain purpose and usage
- [ ] Examples are provided for complex functionality
- [ ] Cross-references to related modules are included
- [ ] Security considerations are documented
- [ ] Performance characteristics are noted
