---
name: database-operations
description: Database naming standards, repository patterns, multi-database switching (ClinVar, GWAS Catalog, Ensembl), DuckDB/Parquet queries, and API route conventions. Use when working with databases, creating models, implementing repositories, switching database profiles, or designing API endpoints. Triggers on database, SQL, DuckDB, ClinVar, GWAS, Ensembl, repository, API routes, multi-database.
---

# Database Operations and Standards

## Entity-Specific Primary Keys

All database tables use entity-specific primary keys for clarity and consistency:

```sql
-- ✅ STANDARDIZED: Entity-specific primary keys
sessions.session_id UUID PRIMARY KEY
leads.lead_id UUID PRIMARY KEY
messages.message_id UUID PRIMARY KEY
daily_metrics.daily_metric_id UUID PRIMARY KEY
agencies.agency_id UUID PRIMARY KEY
```

## Field Naming Conventions

### Standard Patterns

```sql
-- Primary keys: {entity}_id
session_id, lead_id, message_id

-- Foreign keys: {referenced_entity}_id
session_id REFERENCES sessions(session_id)
agency_id REFERENCES agencies(agency_id)

-- Timestamps: {action}_at
created_at, updated_at, started_at, expires_at

-- Booleans: is_{state}
is_connected, is_active, is_qualified

-- Counts: {entity}_count
message_count, lead_count, notification_count

-- Durations: {property}_{unit}
duration_seconds, timeout_minutes
```

## Repository Pattern Auto-Derivation

The enhanced BaseRepository automatically derives table names and primary keys:

```python
# ✅ STANDARDIZED: Convention-based repositories
class LeadRepository(BaseRepository[Lead]):
    def __init__(self):
        super().__init__()  # Auto-derives "leads" and "lead_id"

class SessionRepository(BaseRepository[AvatarSession]):
    def __init__(self):
        super().__init__()  # Auto-derives "sessions" and "session_id"
```

**Benefits**:
- ✅ Self-documenting schema
- ✅ Clear foreign key relationships
- ✅ Eliminates repository method overrides
- ✅ Consistent with entity naming patterns

## Model-Database Alignment

Models mirror database fields exactly to eliminate field mapping complexity:

```python
# ✅ STANDARDIZED: Models mirror database exactly
class Lead(BaseModel):
    lead_id: UUID = Field(default_factory=uuid4)  # Matches database field
    session_id: UUID                               # Matches database field
    agency_id: str                                 # Matches database field
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        alias_generator=None  # Use exact field names
    )
```

## API Route Standards

### RESTful Conventions

```python
# ✅ STANDARDIZED: RESTful with consistent parameter naming
router = APIRouter(prefix="/api/v1/leads", tags=["leads"])

@router.get("/{lead_id}")           # GET /api/v1/leads/{lead_id}
@router.put("/{lead_id}")           # PUT /api/v1/leads/{lead_id}
@router.delete("/{lead_id}")        # DELETE /api/v1/leads/{lead_id}

# Sub-resources
@router.get("/{lead_id}/messages")  # GET /api/v1/leads/{lead_id}/messages
@router.get("/agency/{agency_id}")  # GET /api/v1/leads/agency/{agency_id}
```

## FastAPI Documentation

### Complete Endpoint Documentation

```python
from fastapi import APIRouter, HTTPException, status
from typing import List

router = APIRouter(prefix="/products", tags=["products"])

@router.get(
    "/",
    response_model=List[Product],
    summary="List all products",
    description="Retrieve a paginated list of all active products"
)
async def list_products(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None
) -> List[Product]:
    """
    Retrieve products with optional filtering.

    - **skip**: Number of products to skip (for pagination)
    - **limit**: Maximum number of products to return
    - **category**: Filter by product category
    """
    # Implementation here
```

## Database Connections

### Supported Databases

- **PostgreSQL**: Primary database option
- **MySQL**: Alternative database support
- **SQLite**: Local development database
- **MS SQL**: Enterprise database support
- **AWS Athena**: Cloud analytics database

### Configuration Pattern

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Database connection from environment
DATABASE_URL = settings.database_url

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

## Repository Best Practices

### Base Repository Pattern

```python
from typing import Generic, TypeVar, Type, Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session

T = TypeVar('T', bound=BaseModel)

class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""

    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, db: Session, id: int) -> Optional[T]:
        """Get entity by ID."""
        return db.query(self.model).filter(self.model.id == id).first()

    def list(self, db: Session, skip: int = 0, limit: int = 100) -> List[T]:
        """List entities with pagination."""
        return db.query(self.model).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: BaseModel) -> T:
        """Create new entity."""
        db_obj = self.model(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: T, obj_in: BaseModel) -> T:
        """Update existing entity."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int) -> bool:
        """Delete entity by ID."""
        obj = db.query(self.model).filter(self.model.id == id).first()
        if obj:
            db.delete(obj)
            db.commit()
            return True
        return False
```

## Multi-Database Switching

This platform supports runtime database profile switching:

### Available Profiles

| Profile | Engine | Use Case |
|---------|--------|----------|
| `clinvar` | SQLite | Variant–disease interpretation |
| `gwas` | DuckDB/Parquet | Genome-wide association statistics |
| `ensembl` | MySQL | Gene / transcript annotation (public mirror) |

### Backend Usage

```python
from backend.src.config.database_registry import (
    DatabaseProfile,
    get_active_profile,
    set_active_profile,
    get_database_connection
)

# Check current database
current = get_active_profile()

# Switch databases
set_active_profile(DatabaseProfile.GWAS)

# Get connection for queries
conn = get_database_connection()
```

### DuckDB/Parquet Queries

```python
import duckdb

# Query Parquet files directly
conn = duckdb.connect()
result = conn.execute("""
    SELECT cdr3_aa, frequency, sample_id
    FROM 'data/clonotypes/*.parquet'
    WHERE frequency > 0.01
    ORDER BY frequency DESC
""").fetchall()
```

For per-database query patterns, schema quirks and worked examples, see the
context files the agents themselves are given:
`backend/src/prompts/database_context/{clinvar,gwas,ensembl}_context.md`.

## Query Optimization

### Best Practices

1. **Use Select Loading**: Specify which relationships to load
2. **Index Foreign Keys**: Always index foreign key columns
3. **Avoid N+1 Queries**: Use `joinedload()` or `selectinload()`
4. **Pagination**: Always implement pagination for list endpoints
5. **Connection Pooling**: Configure appropriate pool sizes

### Example Optimized Query

```python
from sqlalchemy.orm import joinedload

# ✅ Good: Efficient with eager loading
def get_user_with_posts(db: Session, user_id: int):
    return db.query(User)\
        .options(joinedload(User.posts))\
        .filter(User.id == user_id)\
        .first()

# ❌ Bad: N+1 query problem
def get_user_with_posts_bad(db: Session, user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    posts = [post for post in user.posts]  # Causes N+1 queries
    return user
```
