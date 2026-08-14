/**
 * Fake backend for the demo build (`demo.html`).
 *
 * Installs a `window.fetch` override that answers every request the real UI
 * makes (auth, conversations, databases, streaming chat, artifacts, reports,
 * feedback, projects) with in-memory mock data — no network access, no
 * backend. Every store and hook in the app (`authStore`, `conversationStore`,
 * `useChat`, ...) keeps calling the same `services/api.ts` and
 * `services/authApi.ts` functions unmodified; only the transport underneath is
 * swapped.
 */

import type { DatabaseInfo, DatabaseListResponse, ActiveDatabaseResponse, ConnectDatabaseResponse } from '../types/database'
import type { Conversation, ConversationList, ConversationWithMessages, StreamEvent } from '../types/conversation'
import type { ProjectList } from '../types/project'
import type { Report, ReportList } from '../types/report'
import type { MessageFeedback, ConversationFeedbackList, FeedbackType } from '../types/feedback'
import type { TokenResponse } from '../types/auth'
import type { ArtifactListResponse, BatchDownloadUrlResponse, DownloadUrlResponse } from '../services/api'
import {
  DEMO_USER,
  DEMO_PROJECT,
  DEMO_DATABASES,
  DEMO_CONVERSATIONS,
  pickScenario,
  type DemoRawMessage,
  type DemoStep,
} from './mockData'

function resolveApiBaseUrl(): string {
  return (
    (typeof window !== 'undefined' && window.__API_URL__) ||
    import.meta.env.VITE_API_URL ||
    'http://localhost:8000'
  )
}

const AGENT_KEY_MAP: Record<string, string> = {
  'SQL Agent': 'sql_agent',
  Coder: 'coder',
  Orchestrator: 'orchestrator',
  Coordinator: 'coordinator',
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

interface DemoArtifact {
  file_id: string
  user_id: string | null
  thread_id: string | null
  conversation_id: string | null
  conversation_title: string | null
  file_type: 'query_result' | 'coder_output' | 'analysis' | 'other'
  s3_bucket: string
  s3_key: string
  content_type: string
  size_bytes: number
  metadata: Record<string, unknown>
  created_at: string
}

interface DemoState {
  conversations: Conversation[]
  histories: Map<string, ConversationWithMessages>
  activeDatabaseId: string
  projects: (typeof DEMO_PROJECT)[]
  artifacts: DemoArtifact[]
  reports: Report[]
  feedback: Map<string, MessageFeedback>
}

let state: DemoState = createInitialState()
let originalFetch: typeof window.fetch | null = null

function createInitialState(): DemoState {
  const histories = new Map<string, ConversationWithMessages>()
  const artifacts: DemoArtifact[] = []
  const conversations: Conversation[] = DEMO_CONVERSATIONS.map((conv) => {
    histories.set(conv.id, {
      id: conv.id,
      user_id: conv.user_id,
      title: conv.title,
      project_id: conv.project_id,
      created_at: conv.created_at,
      updated_at: conv.updated_at,
      messages: conv.messages,
      token_usage: { estimated_tokens: 2800, max_tokens: 128000, usage_pct: 2.2 },
    })

    for (const msg of conv.messages) {
      for (const file of msg.files || []) {
        artifacts.push({
          file_id: file.id,
          user_id: conv.user_id,
          thread_id: conv.id,
          conversation_id: conv.id,
          conversation_title: conv.title,
          file_type: 'coder_output',
          s3_bucket: 'demo',
          s3_key: file.url,
          content_type: file.contentType,
          size_bytes: 8192,
          metadata: {},
          created_at: conv.updated_at,
        })
      }
    }

    return {
      id: conv.id,
      user_id: conv.user_id,
      title: conv.title,
      project_id: conv.project_id,
      created_at: conv.created_at,
      updated_at: conv.updated_at,
    }
  })

  return {
    conversations,
    histories,
    activeDatabaseId: 'clinvar',
    projects: [DEMO_PROJECT],
    artifacts,
    reports: [],
    feedback: new Map(),
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function databaseInfoFor(id: string): DatabaseInfo | undefined {
  const db = DEMO_DATABASES.find((d) => d.id === id)
  if (!db) return undefined
  return {
    ...db,
    is_active: db.id === state.activeDatabaseId,
    status: db.id === state.activeDatabaseId ? 'connected' : 'available',
  }
}

function chunkAnswer(text: string): string[] {
  return text.match(/\S+\s*|\s+/g) || [text]
}

function stepDelay(step: DemoStep): number {
  switch (step.type) {
    case 'plan':
      return 300
    case 'agent_start':
      return 500
    case 'thinking':
      return 450
    case 'agent_end':
      return 800
    case 'file':
      return 600
    case 'answer':
      return 400
    default:
      return 300
  }
}

function persistConversation(threadId: string, userMessage: string, rawMessages: DemoRawMessage[]) {
  const now = new Date().toISOString()
  const existing = state.histories.get(threadId)

  if (existing) {
    existing.messages = [...existing.messages, ...rawMessages]
    existing.updated_at = now
    const conv = state.conversations.find((c) => c.id === threadId)
    if (conv) conv.updated_at = now
    return
  }

  const title = userMessage.length > 60 ? `${userMessage.slice(0, 57)}...` : userMessage
  state.histories.set(threadId, {
    id: threadId,
    user_id: DEMO_USER.id,
    title,
    project_id: DEMO_PROJECT.id,
    created_at: now,
    updated_at: now,
    messages: rawMessages,
    token_usage: { estimated_tokens: 3200, max_tokens: 128000, usage_pct: 2.5 },
  })
  state.conversations.push({
    id: threadId,
    user_id: DEMO_USER.id,
    title,
    project_id: DEMO_PROJECT.id,
    created_at: now,
    updated_at: now,
  })
}

function registerArtifact(threadId: string, conversationTitle: string, file: NonNullable<DemoStep['file']>) {
  state.artifacts.unshift({
    file_id: crypto.randomUUID(),
    user_id: DEMO_USER.id,
    thread_id: threadId,
    conversation_id: threadId,
    conversation_title: conversationTitle,
    file_type: 'coder_output',
    s3_bucket: 'demo',
    s3_key: file.url,
    content_type: file.contentType,
    size_bytes: 8192,
    metadata: {},
    created_at: new Date().toISOString(),
  })
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- parsed request JSON, shape varies by route
function handleChatStream(body: any, signal: AbortSignal | undefined): Response {
  const message: string = body?.message || ''
  const threadId: string = body?.thread_id || crypto.randomUUID()
  const scenario = pickScenario(message)
  const encoder = new TextEncoder()
  let cancelled = false

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const onAbort = () => {
        cancelled = true
      }
      signal?.addEventListener('abort', onAbort)

      const send = (event: StreamEvent) => {
        if (cancelled) return
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      }

      const rawMessages: DemoRawMessage[] = [{ type: 'human', content: message }]
      let finalAnswer = ''

      for (const step of scenario.steps) {
        if (cancelled) break
        await delay(stepDelay(step))
        if (cancelled) break

        if (step.type === 'plan' && step.plan) {
          send({ type: 'plan', content: JSON.stringify(step.plan) })
        } else if (step.type === 'agent_start') {
          send({ type: 'agent_start', content: step.content || '', agent_name: step.agentName })
          rawMessages.push({
            type: 'system',
            name: AGENT_KEY_MAP[step.agentName || ''] || step.agentName,
            content: step.content || '',
          })
        } else if (step.type === 'thinking') {
          send({ type: 'thinking', content: step.content || '', agent_name: step.agentName })
        } else if (step.type === 'agent_end') {
          send({ type: 'agent_end', content: step.content || '', agent_name: step.agentName })
          rawMessages.push({
            type: 'human',
            name: AGENT_KEY_MAP[step.agentName || ''] || step.agentName,
            content: step.content || '',
          })
        } else if (step.type === 'file' && step.file) {
          send({
            type: 'file',
            content: '',
            agent_name: step.agentName,
            file_metadata: {
              filename: step.file.filename,
              s3_bucket: 'demo',
              s3_key: step.file.url,
              file_type: step.file.fileType,
              content_type: step.file.contentType,
              url: step.file.url,
              is_image: step.file.isImage,
            },
          })
          rawMessages.push({
            type: 'ai',
            content: '',
            files: [
              {
                id: crypto.randomUUID(),
                filename: step.file.filename,
                url: step.file.url,
                fileType: step.file.fileType,
                contentType: step.file.contentType,
                isImage: step.file.isImage,
              },
            ],
          })
          registerArtifact(threadId, state.histories.get(threadId)?.title || message, step.file)
        } else if (step.type === 'answer' && step.answer) {
          finalAnswer = step.answer
          for (const chunk of chunkAnswer(step.answer)) {
            if (cancelled) break
            send({ type: 'token', content: chunk })
            await delay(20)
          }
        }
      }

      if (!cancelled) {
        rawMessages.push({ type: 'ai', content: finalAnswer })
        persistConversation(threadId, message, rawMessages)
        send({
          type: 'end',
          content: '',
          thread_id: threadId,
          token_usage: { estimated_tokens: 3200, max_tokens: 128000, usage_pct: 2.5 },
        })
      }

      signal?.removeEventListener('abort', onAbort)
      controller.close()
    },
    cancel() {
      cancelled = true
    },
  })

  return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

function demoTokenResponse(): TokenResponse {
  return {
    access_token: 'demo-access-token',
    refresh_token: 'demo-refresh-token',
    token_type: 'bearer',
    expires_in: 3600,
    user: DEMO_USER,
  }
}

async function routeRequest(
  method: string,
  pathname: string,
  search: URLSearchParams,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- parsed request JSON, shape varies by route
  body: any,
  signal: AbortSignal | undefined,
): Promise<Response> {
  // Auth — any non-empty credentials are accepted; this is a demo.
  if (method === 'POST' && pathname === '/auth/login') {
    if (!body?.username || !body?.password) {
      return json({ detail: 'Email and password are required' }, 401)
    }
    return json(demoTokenResponse())
  }
  if (method === 'POST' && pathname === '/auth/register') {
    return json(demoTokenResponse())
  }
  if (method === 'POST' && pathname === '/auth/refresh') {
    return json(demoTokenResponse())
  }
  if (method === 'GET' && pathname === '/auth/me') {
    return json(DEMO_USER)
  }
  if (method === 'POST' && pathname === '/auth/logout') {
    return json({ message: 'Logged out' })
  }
  if (method === 'PATCH' && pathname === '/users/me') {
    return json({ ...DEMO_USER, name: body?.name || DEMO_USER.name })
  }

  // Databases
  if (method === 'GET' && pathname === '/databases') {
    const response: DatabaseListResponse = {
      databases: DEMO_DATABASES.map((d) => databaseInfoFor(d.id)!),
      active_database: state.activeDatabaseId,
    }
    return json(response)
  }
  if (method === 'GET' && pathname === '/databases/active') {
    const db = databaseInfoFor(state.activeDatabaseId)!
    const response: ActiveDatabaseResponse = {
      id: db.id,
      name: db.name,
      display_name: db.display_name,
      database_type: db.database_type,
      sql_dialect: db.sql_dialect,
      description: db.description,
      domain: db.domain,
    }
    return json(response)
  }
  const connectMatch = pathname.match(/^\/databases\/([^/]+)\/connect$/)
  if (method === 'POST' && connectMatch) {
    const db = databaseInfoFor(decodeURIComponent(connectMatch[1]))
    if (!db) return json({ detail: 'Database not found' }, 404)
    state.activeDatabaseId = db.id
    const response: ConnectDatabaseResponse = {
      success: true,
      database: databaseInfoFor(db.id)!,
      message: `Connected to ${db.display_name}`,
    }
    return json(response)
  }
  const singleDbMatch = pathname.match(/^\/databases\/([^/]+)$/)
  if (method === 'GET' && singleDbMatch) {
    const db = databaseInfoFor(decodeURIComponent(singleDbMatch[1]))
    if (!db) return json({ detail: 'Database not found' }, 404)
    return json(db)
  }

  // Conversations
  if (method === 'GET' && pathname === '/conversations') {
    const projectId = search.get('project_id')
    const conversations = projectId
      ? state.conversations.filter((c) => c.project_id === projectId)
      : state.conversations
    const response: ConversationList = { conversations, count: conversations.length }
    return json(response)
  }
  const historyMatch = pathname.match(/^\/conversations\/([^/]+)\/history$/)
  if (method === 'GET' && historyMatch) {
    const history = state.histories.get(decodeURIComponent(historyMatch[1]))
    if (!history) return json({ detail: 'Resource not found' }, 404)
    return json(history)
  }
  const conversationMatch = pathname.match(/^\/conversations\/([^/]+)$/)
  if (conversationMatch) {
    const id = decodeURIComponent(conversationMatch[1])
    if (method === 'GET') {
      const conv = state.conversations.find((c) => c.id === id)
      if (!conv) return json({ detail: 'Resource not found' }, 404)
      return json(conv)
    }
    if (method === 'PATCH') {
      const conv = state.conversations.find((c) => c.id === id)
      if (!conv) return json({ detail: 'Resource not found' }, 404)
      conv.title = body?.title ?? conv.title
      conv.updated_at = new Date().toISOString()
      const history = state.histories.get(id)
      if (history) history.title = conv.title
      return json(conv)
    }
    if (method === 'DELETE') {
      state.conversations = state.conversations.filter((c) => c.id !== id)
      state.histories.delete(id)
      return new Response(null, { status: 204 })
    }
  }

  // Chat streaming
  if (method === 'POST' && pathname === '/chat/stream') {
    return handleChatStream(body, signal)
  }

  // Projects
  if (method === 'GET' && pathname === '/projects') {
    const response: ProjectList = { projects: state.projects, count: state.projects.length }
    return json(response)
  }
  const snippetsMatch = pathname.match(/^\/projects\/([^/]+)\/snippets$/)
  if (method === 'GET' && snippetsMatch) {
    return json({ snippets: [], count: 0 })
  }

  // Artifacts
  if (method === 'GET' && pathname === '/artifacts') {
    const limit = Number(search.get('limit') || '20')
    const offset = Number(search.get('offset') || '0')
    const page = state.artifacts.slice(offset, offset + limit)
    const response: ArtifactListResponse = { artifacts: page, count: state.artifacts.length }
    return json(response)
  }
  if (method === 'POST' && pathname === '/artifacts/batch-download-urls') {
    const fileIds: string[] = body?.file_ids || []
    const response: BatchDownloadUrlResponse = {
      urls: fileIds.map((fileId) => {
        const artifact = state.artifacts.find((a) => a.file_id === fileId)
        return { file_id: fileId, download_url: artifact?.s3_key || null }
      }),
      expires_in: 3600,
    }
    return json(response)
  }
  const downloadMatch = pathname.match(/^\/artifacts\/([^/]+)\/download$/)
  if (method === 'GET' && downloadMatch) {
    const artifact = state.artifacts.find((a) => a.file_id === decodeURIComponent(downloadMatch[1]))
    const response: DownloadUrlResponse = { download_url: artifact?.s3_key || '', expires_in: 3600 }
    return json(response)
  }

  // Reports
  if (pathname === '/reports') {
    if (method === 'GET') {
      const projectId = search.get('project_id')
      const reports = projectId ? state.reports.filter((r) => r.project_id === projectId) : state.reports
      const response: ReportList = { reports, count: reports.length }
      return json(response)
    }
    if (method === 'POST') {
      const conv = state.conversations.find((c) => c.id === body?.conversation_id)
      const report: Report = {
        id: crypto.randomUUID(),
        user_id: DEMO_USER.id,
        conversation_id: body?.conversation_id,
        conversation_title: conv?.title || 'Demo conversation',
        project_id: DEMO_PROJECT.id,
        title: body?.title || 'Untitled report',
        content: body?.content || '',
        message_index: body?.message_index ?? 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      state.reports.unshift(report)
      return json(report)
    }
  }
  if (method === 'GET' && pathname === '/reports/check') {
    const conversationId = search.get('conversation_id')
    const messageIndex = Number(search.get('message_index'))
    const report = state.reports.find(
      (r) => r.conversation_id === conversationId && r.message_index === messageIndex,
    )
    return json({ exists: Boolean(report), report_id: report?.id ?? null })
  }
  const reportsForConvMatch = pathname.match(/^\/reports\/conversation\/([^/]+)$/)
  if (method === 'GET' && reportsForConvMatch) {
    const conversationId = decodeURIComponent(reportsForConvMatch[1])
    const entries = state.reports
      .filter((r) => r.conversation_id === conversationId)
      .map((r) => ({ report_id: r.id, message_index: r.message_index }))
    return json(entries)
  }
  const reportMatch = pathname.match(/^\/reports\/([^/]+)$/)
  if (reportMatch) {
    const id = decodeURIComponent(reportMatch[1])
    if (method === 'PATCH') {
      const report = state.reports.find((r) => r.id === id)
      if (!report) return json({ detail: 'Resource not found' }, 404)
      report.title = body?.title ?? report.title
      report.updated_at = new Date().toISOString()
      return json(report)
    }
    if (method === 'DELETE') {
      state.reports = state.reports.filter((r) => r.id !== id)
      return new Response(null, { status: 204 })
    }
  }

  // Feedback
  if (method === 'POST' && pathname === '/feedback') {
    const key = `${body?.conversation_id}:${body?.message_index}`
    const feedback: MessageFeedback = {
      id: state.feedback.get(key)?.id || crypto.randomUUID(),
      user_id: DEMO_USER.id,
      conversation_id: body?.conversation_id,
      message_index: body?.message_index,
      feedback_type: body?.feedback_type as FeedbackType,
      note: body?.note ?? null,
      created_at: state.feedback.get(key)?.created_at || new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
    state.feedback.set(key, feedback)
    return json(feedback)
  }
  const feedbackForConvMatch = pathname.match(/^\/feedback\/conversation\/([^/]+)$/)
  if (method === 'GET' && feedbackForConvMatch) {
    const conversationId = decodeURIComponent(feedbackForConvMatch[1])
    const entries = Array.from(state.feedback.values())
      .filter((f) => f.conversation_id === conversationId)
      .map((f) => ({ feedback_id: f.id, message_index: f.message_index, feedback_type: f.feedback_type }))
    const response: ConversationFeedbackList = { feedback: entries, count: entries.length }
    return json(response)
  }
  if (method === 'GET' && pathname === '/feedback/message') {
    const key = `${search.get('conversation_id')}:${search.get('message_index')}`
    return json(state.feedback.get(key) ?? null)
  }
  const feedbackByMessageMatch = pathname.match(/^\/feedback\/message\/([^/]+)\/([^/]+)$/)
  if (method === 'DELETE' && feedbackByMessageMatch) {
    state.feedback.delete(
      `${decodeURIComponent(feedbackByMessageMatch[1])}:${decodeURIComponent(feedbackByMessageMatch[2])}`,
    )
    return new Response(null, { status: 204 })
  }
  const feedbackMatch = pathname.match(/^\/feedback\/([^/]+)$/)
  if (method === 'DELETE' && feedbackMatch) {
    const id = decodeURIComponent(feedbackMatch[1])
    for (const [key, value] of state.feedback.entries()) {
      if (value.id === id) state.feedback.delete(key)
    }
    return new Response(null, { status: 204 })
  }

  console.warn(`[demo] Unhandled request in demo mode: ${method} ${pathname}`)
  return json({ detail: 'Not found (demo mode)' }, 404)
}

/**
 * Parse a request body into a plain object. `authApi.loginUser` sends
 * form-urlencoded (OAuth2 password flow); everything else sends JSON.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- returns arbitrary decoded JSON or form data
function parseBody(init: RequestInit | undefined): any {
  if (!init?.body || typeof init.body !== 'string') return undefined
  const contentType = new Headers(init.headers).get('Content-Type') || ''
  if (contentType.includes('application/x-www-form-urlencoded')) {
    return Object.fromEntries(new URLSearchParams(init.body))
  }
  try {
    return JSON.parse(init.body)
  } catch {
    return undefined
  }
}

export function installDemoBackend() {
  if (originalFetch) return // already installed
  state = createInitialState()
  originalFetch = window.fetch.bind(window)
  const apiBaseUrl = resolveApiBaseUrl()
  const realFetch = originalFetch

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
    if (!url.startsWith(apiBaseUrl)) {
      return realFetch(input, init)
    }

    const parsed = new URL(url)
    const method = (init?.method || 'GET').toUpperCase()
    const body = parseBody(init)

    if (method !== 'POST' || parsed.pathname !== '/chat/stream') {
      await delay(150 + Math.floor(Math.random() * 200))
    }

    return routeRequest(method, parsed.pathname, parsed.searchParams, body, init?.signal ?? undefined)
  }
}
