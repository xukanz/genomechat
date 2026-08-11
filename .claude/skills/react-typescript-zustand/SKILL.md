---
name: react-typescript-zustand
description: React 18, TypeScript, and Zustand patterns for the GenomeChat frontend. SSE streaming, store organization, hooks, and component patterns. Use when building frontend features, creating stores, implementing streaming, or writing React components. Triggers on React, Zustand, frontend, store, SSE, streaming, TypeScript, component, hook.
---

# React + TypeScript + Zustand Patterns

## Project Structure

```
frontend/src/
├── components/       # React components by feature
│   ├── auth/        # Login/Register
│   ├── chat/        # Chat UI with streaming
│   ├── databases/   # Database switching
│   └── projects/    # Project management
├── store/           # Zustand state stores
├── hooks/           # Custom React hooks
├── types/           # TypeScript interfaces
└── services/        # API client
```

## Zustand Store Pattern

### Interface Definition

```typescript
import { create } from 'zustand'

interface DatabaseStore {
  // State
  databases: DatabaseInfo[]
  activeDatabase: string | null
  isLoading: boolean
  error: string | null
  lastFetched: number | null

  // Actions
  loadDatabases: () => Promise<void>
  connectToDatabase: (id: string) => Promise<boolean>
  clearError: () => void
}
```

### Store Implementation

```typescript
// Cache TTL: 5 minutes
const CACHE_TTL_MS = 5 * 60 * 1000

export const useDatabaseStore = create<DatabaseStore>((set, get) => ({
  // Initial state
  databases: [],
  activeDatabase: null,
  isLoading: false,
  error: null,
  lastFetched: null,

  loadDatabases: async () => {
    const { lastFetched, isLoading } = get()

    // Skip if already loading
    if (isLoading) return

    // Use cache if fresh
    if (lastFetched && Date.now() - lastFetched < CACHE_TTL_MS) {
      return
    }

    set({ isLoading: true, error: null })

    try {
      const response = await fetchDatabases()
      set({
        databases: response.databases,
        activeDatabase: response.active_database,
        isLoading: false,
        lastFetched: Date.now(),
      })
    } catch (error) {
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to load',
      })
    }
  },

  clearError: () => set({ error: null }),
}))
```

### Available Stores

| Store | Purpose |
|-------|---------|
| `conversationStore` | Chat history, messages, streaming state |
| `projectStore` | Project management and organization |
| `databaseStore` | Database profiles and switching |
| `authStore` | Authentication and user session |
| `artifactStore` | Generated code, files, visualizations |
| `feedbackStore` | User feedback state |
| `uiStore` | UI state (sidebar, modals) |

## Custom Hook Patterns

### useChat Hook (SSE Streaming)

```typescript
import { useState, useCallback, useRef } from 'react'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  thinking?: string
  plan?: Plan
  isStreaming?: boolean
  timestamp: Date
}

export function useChat(conversationId: string) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (content: string) => {
    // Cancel any existing request
    abortControllerRef.current?.abort()
    abortControllerRef.current = new AbortController()

    setIsLoading(true)

    try {
      const stream = await createChatStream(
        content,
        conversationId,
        abortControllerRef.current.signal
      )

      for await (const event of stream) {
        handleStreamEvent(event, setMessages)
      }
    } finally {
      setIsLoading(false)
    }
  }, [conversationId])

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort()
    setIsLoading(false)
  }, [])

  return { messages, isLoading, sendMessage, cancel }
}
```

### Hook Organization

- **State hooks**: `useState`, `useReducer` for local state
- **Effect hooks**: `useEffect`, `useLayoutEffect` for side effects
- **Ref hooks**: `useRef` for mutable values (AbortController, etc.)
- **Memoization**: `useMemo`, `useCallback` for expensive operations

## Component Patterns

### Functional Components with TypeScript

```typescript
interface ChatMessageProps {
  message: Message
  isLast: boolean
  onRetry?: () => void
}

export function ChatMessage({ message, isLast, onRetry }: ChatMessageProps) {
  return (
    <div className={cn('message', message.role)}>
      <MessageContent content={message.content} />
      {message.isStreaming && <StreamingIndicator />}
      {isLast && onRetry && (
        <button onClick={onRetry}>Retry</button>
      )}
    </div>
  )
}
```

### Component Guidelines

- **Size limit**: Keep components under 200 lines
- **Props**: Always define TypeScript interfaces
- **Logic**: Extract to custom hooks when complex
- **State**: Use Zustand for global, useState for local
- **Memoization**: Use `React.memo()` for expensive renders

## SSE Streaming

### Frontend Implementation

```typescript
async function* createChatStream(
  message: string,
  conversationId: string,
  signal: AbortSignal
): AsyncGenerator<StreamEvent> {
  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  })

  const reader = response.body!.getReader()
  const decoder = new TextDecoder()

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    const text = decoder.decode(value)
    for (const line of text.split('\n')) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6))
      }
    }
  }
}
```

## Best Practices

### 1. Type Safety
Always define explicit TypeScript interfaces for props, state, and API responses.

### 2. Error Boundaries
Wrap components in error boundaries to gracefully handle failures.

### 3. Loading States
Always show loading indicators during async operations.

### 4. Cancellation
Use AbortController for cancelable async operations.

### 5. Separation of Concerns
- Components: Presentation
- Hooks: Business logic
- Stores: Global state
- Services: API calls
