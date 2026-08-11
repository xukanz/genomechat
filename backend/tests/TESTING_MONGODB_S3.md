# Testing MongoDB and S3 Integration

This guide explains how to test the MongoDB and S3 integration.

## Test Structure

### Unit Tests (Mocked)
- `tests/test_service/test_mongodb_connection.py` - MongoDB connection tests
- `tests/test_service/test_user_service.py` - User service tests
- `tests/test_service/test_conversation_service.py` - Conversation service tests
- `tests/test_service/test_query_results_service.py` - Query results service tests
- `tests/test_tools/test_database_tool_s3.py` - Database tool S3 integration tests

### Integration Tests (Real MongoDB/S3)
- `tests/test_integration_mongodb_s3.py` - Full integration tests

### Quick Test Script
- `scripts/test_mongodb_s3_setup.py` - Quick verification script

## Running Tests

### 1. Unit Tests (No MongoDB/S3 Required)

Run unit tests with mocked dependencies:

```bash
cd backend
uv run pytest tests/test_service/ -v
uv run pytest tests/test_tools/test_database_tool_s3.py -v
```

### 2. Quick Verification Script

Run the quick test script to verify setup:

```bash
cd backend
python scripts/test_mongodb_s3_setup.py
```

**Required Environment Variables:**
- `MONGODB_URI` or `MONGODB_CONNECTION_STRING` - MongoDB connection string
- `AWS_DEFAULT_BUCKET` - S3 bucket name (optional, will skip S3 tests if not set)
- `AWS_ACCESS_KEY_ID` - AWS access key (if testing S3)
- `AWS_SECRET_ACCESS_KEY` - AWS secret key (if testing S3)

### 3. Integration Tests (Requires MongoDB and S3)

Run full integration tests:

```bash
cd backend
export MONGODB_URI="mongodb://localhost:27017"
export AWS_DEFAULT_BUCKET="your-bucket-name"
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"

uv run pytest tests/test_integration_mongodb_s3.py -v
```

**Note:** Integration tests will be skipped if MongoDB URI or AWS bucket is not configured.

## Test Coverage

### MongoDB Connection Tests
- Connection initialization
- Singleton pattern
- Database access
- Error handling

### User Service Tests
- Create user
- Get user by ID/email
- Update user
- Delete user
- Duplicate email handling

### Conversation Service Tests
- Create conversation
- List user conversations
- Get conversation (with authorization check)
- Update conversation
- Delete conversation
- Thread ID format (`{user_id}:{conversation_id}`)

### Query Results Service Tests
- Save query result to S3 and MongoDB
- Get query result by file_id
- List results by user
- List results by thread
- Delete query result and S3 file
- User authorization checks

### Database Tool Tests
- S3 save when bucket configured
- Local filesystem fallback when bucket not configured
- Empty result handling

## Manual Testing Steps

### 1. Test MongoDB Connection

```python
from src.service.database.connections.mongodb_connection import MongoDBConnection

conn = MongoDBConnection()
client = conn.connect()
db = conn.get_database()
print(f"Connected to database: {db.name}")
```

### 2. Test User Service

```python
from src.service.auth.user_service import UserService
from src.models.user import UserCreate

service = UserService()
user = service.create_user(UserCreate(
    email="test@example.com",
    name="Test User",
    password="password123"
))
print(f"Created user: {user.email}")
```

### 3. Test Conversation Service

```python
from src.service.storage.conversation_service import ConversationService

service = ConversationService()
conv = service.create_conversation(
    conversation_id="conv-123",
    user_id="user-456",
    title="Test Conversation"
)
print(f"Created conversation: {conv.title}")
print(f"Thread ID: {conv.id}")  # Should be user-456:conv-123 format
```

### 4. Test Query Results Service

```python
from src.service.storage.query_results_service import QueryResultsService
from src.models.query_result import QueryResultCreate
import pandas as pd

service = QueryResultsService()
df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

result_data = QueryResultCreate(
    user_id="user-123",
    thread_id="user-123:conv-456",
    query="SELECT * FROM test",
    s3_bucket="your-bucket",
    s3_key="users/user-123/query_results/test.csv",
    row_count=3,
    column_count=2,
    columns=["col1", "col2"]
)

result = service.save_query_result(result_data, df)
print(f"Saved to S3: s3://{result.s3_bucket}/{result.s3_key}")
```

### 5. Test Database Tool

```python
from src.tools.database import execute_sql_query_and_save

# This will save to S3 if AWS_DEFAULT_BUCKET is set
result = execute_sql_query_and_save.invoke({
    "query": "SELECT * FROM your_table LIMIT 10",
    "description": "Test query"
})
print(result)
```

## Troubleshooting

### MongoDB Connection Issues
- Verify `MONGODB_URI` is set correctly
- Check MongoDB is running and accessible
- Verify network connectivity

### S3 Connection Issues
- Verify AWS credentials are set (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- Check `AWS_DEFAULT_BUCKET` is set
- Verify bucket exists and you have write permissions
- Check AWS region matches bucket region

### Test Failures
- Check environment variables are set
- Verify MongoDB collections are created (indexes are auto-created)
- Check S3 bucket permissions
- Review test logs for specific error messages

## Next Steps

After verifying tests pass:
1. Test with real API requests
2. Verify checkpointer uses shared MongoDB client
3. Test multi-user scenarios
4. Test thread_id format in checkpoints
5. Verify S3 files are accessible from sandbox

