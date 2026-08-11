---
name: streaming-architecture
description: Server-Sent Events (SSE) streaming architecture between FastAPI backend and React frontend. Stream event types, LangGraph astream_events, real-time updates. Use when implementing streaming, handling SSE events, or debugging stream issues. Triggers on SSE, streaming, stream, astream_events, real-time, events.
---

# Streaming Architecture

## Overview

The platform uses Server-Sent Events (SSE) for real-time streaming between:
- **Backend**: FastAPI + LangGraph `astream_events` v2
- **Frontend**: React + fetch API for SSE

```
User Input → Frontend → POST /api/v1/chat/stream → Backend
                                                    ↓
                                              LangGraph Agent
                                                    ↓
                                            astream_events v2
                                                    ↓
                      Frontend ← SSE Events ← StreamingResponse
```

## Backend Streaming (FastAPI)

### StreamingResponse Setup

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import json

router = APIRouter()

@router.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    """Stream LLM responses via Server-Sent Events."""
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

async def event_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Generate SSE events from LangGraph."""
    try:
        async for event in agent.astream_events(
            {"message": request.message},
            version="v2"
        ):
            yield format_sse_event(event)
    except Exception as e:
        yield format_sse_event({"event": "error", "data": str(e)})
    finally:
        yield format_sse_event({"event": "done"})

def format_sse_event(data: dict) -> str:
    """Format data as SSE event."""
    return f"data: {json.dumps(data)}\n\n"
```

### LangGraph Event Processing

```python
async for event in app.astream_events(state, version="v2"):
    event_type = event["event"]

    if event_type == "on_chain_start":
        # Agent/node starting
        agent_name = event.get("metadata", {}).get("langgraph_node")
        yield {"event": "agent_start", "agent": agent_name}

    elif event_type == "on_chat_model_stream":
        # Token streaming
        chunk = event["data"]["chunk"]
        yield {"event": "token", "content": chunk.content}

    elif event_type == "on_chain_end":
        # Agent/node completed
        yield {"event": "agent_end"}

    elif event_type == "on_tool_start":
        # Tool invocation
        tool_name = event["name"]
        yield {"event": "tool_start", "tool": tool_name}
```

## Frontend Streaming (React)

### SSE Client Implementation

```typescript
async function* createChatStream(
  message: string,
  signal: AbortSignal
): AsyncGenerator<StreamEvent> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
  })

  if (!response.ok) {
    throw new Error(`Stream failed: ${response.status}`)
  }

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data !== '[DONE]') {
          yield JSON.parse(data)
        }
      }
    }
  }
}
```

### Event Handling in useChat

```typescript
const handleStreamEvent = (
  event: StreamEvent,
  setMessages: React.Dispatch<SetStateAction<Message[]>>
) => {
  switch (event.event) {
    case 'token':
      setMessages(prev => {
        const last = prev[prev.length - 1]
        return [
          ...prev.slice(0, -1),
          { ...last, content: last.content + event.content }
        ]
      })
      break

    case 'agent_start':
      // Show agent activity indicator
      break

    case 'plan':
      // Display execution plan
      setMessages(prev => {
        const last = prev[prev.length - 1]
        return [
          ...prev.slice(0, -1),
          { ...last, plan: event.plan }
        ]
      })
      break

    case 'done':
      // Mark streaming complete
      setMessages(prev => {
        const last = prev[prev.length - 1]
        return [
          ...prev.slice(0, -1),
          { ...last, isStreaming: false }
        ]
      })
      break
  }
}
```

## Event Types

| Event | Direction | Data | Purpose |
|-------|-----------|------|---------|
| `token` | Backend→Frontend | `{ content: string }` | Streaming text chunk |
| `agent_start` | Backend→Frontend | `{ agent: string }` | Agent execution started |
| `agent_end` | Backend→Frontend | `{}` | Agent execution completed |
| `tool_start` | Backend→Frontend | `{ tool: string }` | Tool invocation |
| `plan` | Backend→Frontend | `{ plan: Plan }` | Execution plan update |
| `thinking` | Backend→Frontend | `{ content: string }` | Agent reasoning |
| `error` | Backend→Frontend | `{ message: string }` | Error occurred |
| `done` | Backend→Frontend | `{}` | Stream complete |

## Error Handling

### Backend

```python
async def event_generator(request):
    try:
        async for event in agent.astream_events(...):
            yield format_sse_event(event)
    except asyncio.CancelledError:
        # Client disconnected
        pass
    except Exception as e:
        yield format_sse_event({
            "event": "error",
            "message": str(e)
        })
    finally:
        yield format_sse_event({"event": "done"})
```

### Frontend

```typescript
const sendMessage = async (content: string) => {
  abortRef.current = new AbortController()

  try {
    const stream = createChatStream(content, abortRef.current.signal)
    for await (const event of stream) {
      handleStreamEvent(event)
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      // User cancelled - expected
      return
    }
    // Show error to user
    setError(error.message)
  }
}

// Cancel handler
const cancel = () => {
  abortRef.current?.abort()
}
```

## Debugging Tips

### Check SSE Connection
```bash
# Test streaming endpoint
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection drops | Missing keep-alive | Add `Connection: keep-alive` header |
| Events not parsing | Buffer not flushed | Use `stream: true` in decoder |
| Stuck streaming | Missing done event | Always emit done event in finally |
| CORS errors | Missing headers | Configure CORS middleware |
