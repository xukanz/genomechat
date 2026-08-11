---
name: debugging-performance
description: Debugging tools, performance profiling, monitoring, and optimization techniques. Use when debugging issues, profiling code, optimizing performance, or implementing observability.
---

# Debugging and Performance

## Debugging Tools

### Interactive Debugging with ipdb

```bash
# Install ipdb
uv add --dev ipdb

# Add breakpoint in code
import ipdb; ipdb.set_trace()
```

Common ipdb commands:
- `n` (next): Execute next line
- `s` (step): Step into function
- `c` (continue): Continue execution
- `p variable`: Print variable
- `l` (list): Show code context
- `w` (where): Show stack trace
- `q` (quit): Exit debugger

### Rich Traceback

```bash
# Install rich
uv add --dev rich

# In code
from rich.traceback import install
install()  # Beautiful, informative tracebacks
```

### Logging for Debugging

```python
import logging

# Configure verbose logging for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)

logger = logging.getLogger(__name__)

# Log with context
logger.debug("Processing item", extra={"item_id": item.id, "status": item.status})
```

## Performance Profiling

### CPU Profiling with cProfile

```bash
# Profile a script
uv run python -m cProfile -s cumulative script.py

# Profile with output to file
uv run python -m cProfile -o profile.stats script.py

# Analyze profile stats
uv run python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

### Line Profiling

```bash
# Install line profiler
uv add --dev line-profiler

# Add @profile decorator to functions
@profile
def slow_function():
    # Function code here
    pass

# Run profiler
uv run kernprof -l -v script.py
```

### Memory Profiling

```bash
# Install memory profiler
uv add --dev memory-profiler

# Profile memory usage
uv run python -m memory_profiler script.py

# In code, decorate functions
from memory_profiler import profile

@profile
def memory_intensive_function():
    # Function code here
    pass
```

### Advanced Profiling with py-spy

```bash
# Install py-spy
pip install py-spy

# Profile running process
py-spy top --pid <PID>

# Generate flame graph
py-spy record -o profile.svg -- python script.py
```

## Performance Optimization Patterns

### Caching Strategies

```python
from functools import lru_cache, cache
import asyncio

# LRU cache for expensive computations
@lru_cache(maxsize=1000)
def expensive_calculation(n: int) -> int:
    """Cache results of expensive calculations."""
    # Complex computation here
    return result

# Unlimited cache (Python 3.9+)
@cache
def fibonacci(n: int) -> int:
    """Calculate fibonacci with caching."""
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

# Async caching
from functools import wraps

def async_cache(func):
    """Simple async cache decorator."""
    cache_dict = {}

    @wraps(func)
    async def wrapper(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache_dict:
            cache_dict[key] = await func(*args, **kwargs)
        return cache_dict[key]
    return wrapper

@async_cache
async def fetch_data(url: str):
    """Fetch data with caching."""
    # Implementation
    pass
```

### Generator Patterns

```python
from typing import Iterator, AsyncIterator
import asyncio

# Memory-efficient data processing
def process_large_file(filepath: str) -> Iterator[dict]:
    """Process large file without loading into memory."""
    with open(filepath, 'r') as f:
        for line in f:
            yield process_line(line)

# Async generator for I/O-bound operations
async def fetch_items() -> AsyncIterator[dict]:
    """Fetch items asynchronously."""
    async with aiofiles.open('data.json', mode='r') as f:
        async for line in f:
            yield json.loads(line)
```

### Parallel Processing

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from multiprocessing import Pool
import asyncio

# Thread pool for I/O-bound tasks
def process_urls(urls: list[str]) -> list[dict]:
    """Process URLs in parallel using threads."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_url, urls)
    return list(results)

# Process pool for CPU-bound tasks
def process_data_parallel(data: list) -> list:
    """Process data in parallel using processes."""
    with ProcessPoolExecutor(max_workers=4) as executor:
        results = executor.map(cpu_intensive_task, data)
    return list(results)

# Async concurrency for I/O-bound tasks
async def fetch_all(urls: list[str]) -> list[dict]:
    """Fetch all URLs concurrently."""
    tasks = [fetch_url_async(url) for url in urls]
    return await asyncio.gather(*tasks)
```

## Monitoring and Observability

### Structured Logging with Context

```python
import structlog

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Log with rich context
logger.info(
    "payment_processed",
    user_id=user.id,
    amount=amount,
    currency="USD",
    processing_time=processing_time,
    transaction_id=tx_id
)
```

### Performance Metrics

```python
import time
from functools import wraps
from typing import Callable

def measure_time(func: Callable) -> Callable:
    """Decorator to measure function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        logger.info(
            f"{func.__name__} execution time",
            duration_seconds=end - start,
            function=func.__name__
        )
        return result
    return wrapper

@measure_time
def slow_function():
    """Function with timing measurement."""
    # Implementation
    pass
```

### Health Checks and Monitoring

```python
from fastapi import APIRouter, status
import psutil
import time

router = APIRouter()

@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": time.time()
    }

@router.get("/metrics")
async def metrics():
    """System metrics endpoint."""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "timestamp": time.time()
    }
```

## Optimization Guidelines

### Pre-Optimization Checklist

Before optimizing, always:
1. **Profile first**: Use cProfile or py-spy to identify bottlenecks
2. **Measure baseline**: Record current performance metrics
3. **Set targets**: Define acceptable performance thresholds
4. **Optimize**: Make targeted improvements
5. **Measure again**: Verify improvements with profiling
6. **Document**: Record optimization decisions and results

### Common Optimization Patterns

**Database Queries**:
- Use select_related() and prefetch_related()
- Add database indexes
- Use connection pooling
- Implement query result caching

**API Calls**:
- Use async/await for concurrent requests
- Implement request caching
- Use connection pooling
- Batch requests when possible

**Data Processing**:
- Use generators for large datasets
- Implement streaming for file processing
- Use pandas for vectorized operations
- Consider multiprocessing for CPU-bound tasks

**Memory Usage**:
- Use generators instead of lists for large datasets
- Implement pagination for large result sets
- Clear large objects when no longer needed
- Use memory profiler to identify leaks

## Debugging Checklist

When debugging issues:

1. **Reproduce**: Can you consistently reproduce the issue?
2. **Isolate**: Narrow down the problem to specific code
3. **Log**: Add strategic logging to understand flow
4. **Test**: Write a test that exposes the bug
5. **Fix**: Implement the fix
6. **Verify**: Ensure the test passes and issue is resolved
7. **Prevent**: Add guards or validation to prevent recurrence
