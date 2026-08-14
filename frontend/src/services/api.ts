/**
 * API service for backend communication
 */

import type {
  Conversation,
  ConversationList,
  ConversationWithMessages,
  UpdateTitleRequest,
  ChatRequest,
  ChatResponse,
} from '../types/conversation'
import type {
  Project,
  ProjectCreate,
  ProjectUpdate,
  ProjectList,
  ProjectShare,
  Snippet,
  SnippetCreate,
  SnippetList,
  SnippetUpdate,
  UserSearchResult,
} from '../types/project'
import type { Report, ReportCreate, ReportUpdate, ReportList } from '../types/report'
import { useAuthStore } from '../store/authStore'
import { refreshAccessToken } from './authApi'

// API base URL priority:
// 1. Runtime injection via window.__API_URL__ (set by inject-config.js from Vault Secrets)
// 2. Build-time via import.meta.env.VITE_API_URL
// 3. Default to localhost for development
declare global {
  interface Window {
    __API_URL__?: string
  }
}

const API_BASE_URL =
  (typeof window !== 'undefined' && window.__API_URL__) ||
  import.meta.env.VITE_API_URL ||
  'http://localhost:8000'

/**
 * Get authentication token from auth store
 */
function getAuthToken(): string | null {
  return useAuthStore.getState().accessToken
}

/**
 * Create request headers with authentication
 */
function getHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  }

  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  return headers
}

/**
 * Handle API response errors with automatic token refresh
 */
async function handleResponse<T>(response: Response, retryRequest?: () => Promise<Response>): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) {
      // Unauthorized - try to refresh token
      const { refreshToken } = useAuthStore.getState()
      
      if (refreshToken && retryRequest) {
        try {
          // Attempt token refresh
          const newTokens = await refreshAccessToken(refreshToken)
          useAuthStore.getState().setTokens(newTokens.access_token, newTokens.refresh_token, newTokens.user)
          
          // Retry original request with new token
          const retryResponse = await retryRequest()
          return handleResponse<T>(retryResponse) // Recursive call without retry to prevent infinite loop
        } catch (error) {
          // Refresh failed - logout and redirect
          useAuthStore.getState().logout()
          window.location.href = '/login'
          throw new Error('Session expired - please login again')
        }
      } else {
        // No refresh token or retry function - logout
        useAuthStore.getState().logout()
        window.location.href = '/login'
        throw new Error('Unauthorized - please login again')
      }
    }

    if (response.status === 404) {
      throw new Error('Resource not found')
    }

    if (response.status === 500) {
      throw new Error('Server error - please try again later')
    }

    // Try to get error detail from response
    try {
      const error = await response.json()
      throw new Error(error.detail || `Request failed with status ${response.status}`)
    } catch {
      throw new Error(`Request failed with status ${response.status}`)
    }
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

/**
 * Fetch all conversations for the current user
 * @param projectId - Optional project ID to filter conversations
 */
export async function fetchConversations(projectId?: string): Promise<ConversationList> {
  const url = projectId 
    ? `${API_BASE_URL}/conversations?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE_URL}/conversations`
  
  const makeRequest = () => fetch(url, {
    method: 'GET',
    headers: getHeaders(),
  })
  
  const response = await makeRequest()
  return handleResponse<ConversationList>(response, makeRequest)
}

/**
 * Fetch conversation with full message history
 */
export async function fetchConversationHistory(
  conversationId: string
): Promise<ConversationWithMessages> {
  const makeRequest = () => fetch(`${API_BASE_URL}/conversations/${conversationId}/history`, {
    method: 'GET',
    headers: getHeaders(),
  })
  
  const response = await makeRequest()
  return handleResponse<ConversationWithMessages>(response, makeRequest)
}

/**
 * Update conversation title
 */
export async function updateConversationTitle(
  conversationId: string,
  title: string
): Promise<Conversation> {
  const body: UpdateTitleRequest = { title }

  const makeRequest = () => fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: getHeaders(),
    body: JSON.stringify(body),
  })
  
  const response = await makeRequest()
  return handleResponse<Conversation>(response, makeRequest)
}

/**
 * Delete a conversation
 */
export async function deleteConversation(conversationId: string): Promise<void> {
  const makeRequest = () => fetch(`${API_BASE_URL}/conversations/${conversationId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })
  
  const response = await makeRequest()
  return handleResponse<void>(response, makeRequest)
}

/**
 * Send a chat message (non-streaming)
 */
export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  const makeRequest = () => fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(request),
  })
  
  const response = await makeRequest()
  return handleResponse<ChatResponse>(response, makeRequest)
}

/**
 * Create streaming connection using fetch API
 * This allows POST method and custom headers (including Authorization)
 * @param request - Chat request parameters
 * @param onEvent - Callback for each SSE event
 * @param onError - Callback for errors (AbortError is handled gracefully)
 * @param onEnd - Callback when stream ends
 * @param signal - Optional AbortSignal for cancellation
 */
export async function createChatStreamWithFetch(
  request: ChatRequest,
  onEvent: (event: any) => void,
  onError: (error: Error) => void,
  onEnd: () => void,
  signal?: AbortSignal
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(request),
      signal, // Pass AbortSignal to fetch
    })

    if (!response.ok) {
      throw new Error(`Stream failed with status ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        // Check if aborted before reading
        if (signal?.aborted) {
          break
        }

        const { done, value } = await reader.read()

        if (done) {
          onEnd()
          break
        }

        // Check if aborted after reading
        if (signal?.aborted) {
          break
        }

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE messages
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              // Only process event if not aborted
              if (!signal?.aborted) {
                onEvent(data)
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e)
            }
          }
        }
      }
    } finally {
      // Always cleanup the reader
      reader.cancel().catch(() => {
        // Ignore cancel errors
      })
    }
  } catch (error) {
    // Handle AbortError gracefully - don't treat as real error
    if (error instanceof Error && error.name === 'AbortError') {
      console.log('[api] Stream cancelled by user')
      onEnd()
      return
    }
    onError(error instanceof Error ? error : new Error('Stream failed'))
  }
}

/**
 * Artifacts API
 */

export interface ArtifactListResponse {
  artifacts: Array<{
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
    metadata: Record<string, any>
    created_at: string
  }>
  count: number
}

export interface DownloadUrlResponse {
  download_url: string
  expires_in: number
}

/**
 * List user's artifacts with optional filtering and pagination
 */
export async function listArtifacts(
  threadId?: string,
  projectId?: string,
  fileType?: string,
  limit: number = 20,
  offset: number = 0
): Promise<ArtifactListResponse> {
  const params = new URLSearchParams()
  if (threadId) params.append('thread_id', threadId)
  if (projectId) params.append('project_id', projectId)
  if (fileType) params.append('file_type', fileType)
  // Request only images by filtering on content type
  params.append('content_type_pattern', 'png|jpg|jpeg|gif|svg|webp')
  params.append('limit', limit.toString())
  params.append('offset', offset.toString())

  const url = `${API_BASE_URL}/artifacts?${params.toString()}`
  
  const makeRequest = () => fetch(url, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<ArtifactListResponse>(response, makeRequest)
}

/**
 * Get presigned download URL for an artifact
 */
export async function getDownloadUrl(fileId: string, expiresIn: number = 3600): Promise<DownloadUrlResponse> {
  const params = new URLSearchParams()
  params.append('expires_in', expiresIn.toString())

  const url = `${API_BASE_URL}/artifacts/${fileId}/download?${params.toString()}`
  
  const makeRequest = () => fetch(url, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<DownloadUrlResponse>(response, makeRequest)
}

export interface BatchDownloadUrlItem {
  file_id: string
  download_url: string | null
}

export interface BatchDownloadUrlResponse {
  urls: BatchDownloadUrlItem[]
  expires_in: number
}

/**
 * Get presigned download URLs for multiple artifacts in batch
 * More efficient than calling getDownloadUrl for each file individually
 */
export async function getBatchDownloadUrls(
  fileIds: string[],
  expiresIn: number = 3600
): Promise<BatchDownloadUrlResponse> {
  const url = `${API_BASE_URL}/artifacts/batch-download-urls`

  const makeRequest = () => fetch(url, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({
      file_ids: fileIds,
      expires_in: expiresIn,
    }),
  })

  const response = await makeRequest()
  return handleResponse<BatchDownloadUrlResponse>(response, makeRequest)
}

// ============================================================================
// Project API Functions
// ============================================================================

/**
 * Fetch all projects for the current user
 */
export async function fetchProjects(): Promise<ProjectList> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects`, {
    method: 'GET',
    headers: getHeaders(),
  })
  
  const response = await makeRequest()
  return handleResponse<ProjectList>(response, makeRequest)
}

/**
 * Create a new project
 */
export async function createProject(data: ProjectCreate): Promise<Project> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })
  
  const response = await makeRequest()
  return handleResponse<Project>(response, makeRequest)
}

/**
 * Update project metadata
 */
export async function updateProject(
  projectId: string,
  updates: ProjectUpdate
): Promise<Project> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}`, {
    method: 'PATCH',
    headers: getHeaders(),
    body: JSON.stringify(updates),
  })
  
  const response = await makeRequest()
  return handleResponse<Project>(response, makeRequest)
}

/**
 * Delete a project
 */
export async function deleteProject(projectId: string): Promise<void> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })
  
  const response = await makeRequest()
  
  // 204 No Content - nothing to return
  if (response.status === 204) {
    return
  }
  
  return handleResponse<void>(response, makeRequest)
}

/**
 * Move conversation to a different project
 */
export async function moveConversationToProject(
  conversationId: string,
  projectId: string
): Promise<void> {
  const makeRequest = () => fetch(
    `${API_BASE_URL}/projects/${projectId}/conversations/${conversationId}/move`,
    {
      method: 'POST',
      headers: getHeaders(),
    }
  )

  const response = await makeRequest()

  // 204 No Content - nothing to return
  if (response.status === 204) {
    return
  }

  return handleResponse<void>(response, makeRequest)
}

// ============================================================================
// Project Sharing API Functions
// ============================================================================

/**
 * Search users by email or name for sharing
 */
export async function searchUsers(
  query: string,
  limit: number = 10
): Promise<UserSearchResult> {
  const params = new URLSearchParams({
    q: query,
    limit: limit.toString(),
  })

  const makeRequest = () => fetch(`${API_BASE_URL}/users/search?${params.toString()}`, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<UserSearchResult>(response, makeRequest)
}

/**
 * Share a project with another user
 */
export async function shareProject(
  projectId: string,
  userId: string
): Promise<ProjectShare> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/shares`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify({ user_id: userId }),
  })

  const response = await makeRequest()
  return handleResponse<ProjectShare>(response, makeRequest)
}

/**
 * Remove a user's access to a shared project
 */
export async function removeShare(
  projectId: string,
  userId: string
): Promise<void> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/shares/${userId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })

  const response = await makeRequest()

  if (response.status === 204) {
    return
  }

  return handleResponse<void>(response, makeRequest)
}

// ============================================================================
// Snippet API Functions
// ============================================================================

/**
 * Fetch all snippets for a project
 */
export async function fetchSnippets(projectId: string): Promise<SnippetList> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/snippets`, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<SnippetList>(response, makeRequest)
}

/**
 * Create a new snippet in a project
 */
export async function createSnippet(
  projectId: string,
  data: SnippetCreate
): Promise<Snippet> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/snippets`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })

  const response = await makeRequest()
  return handleResponse<Snippet>(response, makeRequest)
}

/**
 * Update a snippet in a project
 */
export async function updateSnippet(
  projectId: string,
  snippetId: string,
  updates: SnippetUpdate
): Promise<Snippet> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/snippets/${snippetId}`, {
    method: 'PUT',
    headers: getHeaders(),
    body: JSON.stringify(updates),
  })

  const response = await makeRequest()
  return handleResponse<Snippet>(response, makeRequest)
}

/**
 * Delete a snippet from a project
 */
export async function deleteSnippet(
  projectId: string,
  snippetId: string
): Promise<void> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/snippets/${snippetId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })

  const response = await makeRequest()

  if (response.status === 204) {
    return
  }

  return handleResponse<void>(response, makeRequest)
}

/**
 * Toggle a snippet's enabled status
 */
export async function toggleSnippet(
  projectId: string,
  snippetId: string
): Promise<Snippet> {
  const makeRequest = () => fetch(`${API_BASE_URL}/projects/${projectId}/snippets/${snippetId}/toggle`, {
    method: 'PATCH',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<Snippet>(response, makeRequest)
}

// ============================================================================
// Report API Functions
// ============================================================================

/**
 * Fetch all reports for the current user
 * @param projectId - Optional project ID to filter reports
 */
export async function fetchReports(projectId?: string): Promise<ReportList> {
  const url = projectId
    ? `${API_BASE_URL}/reports?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE_URL}/reports`

  const makeRequest = () => fetch(url, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<ReportList>(response, makeRequest)
}

/**
 * Create a new report from a bookmarked AI response
 */
export async function createReport(data: ReportCreate): Promise<Report> {
  const makeRequest = () => fetch(`${API_BASE_URL}/reports`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })

  const response = await makeRequest()
  return handleResponse<Report>(response, makeRequest)
}

/**
 * Update report title
 */
export async function updateReport(
  reportId: string,
  updates: ReportUpdate
): Promise<Report> {
  const makeRequest = () => fetch(`${API_BASE_URL}/reports/${reportId}`, {
    method: 'PATCH',
    headers: getHeaders(),
    body: JSON.stringify(updates),
  })

  const response = await makeRequest()
  return handleResponse<Report>(response, makeRequest)
}

/**
 * Delete a report
 */
export async function deleteReport(reportId: string): Promise<void> {
  const makeRequest = () => fetch(`${API_BASE_URL}/reports/${reportId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  })

  const response = await makeRequest()

  if (response.status === 204) {
    return
  }

  return handleResponse<void>(response, makeRequest)
}

/**
 * List all reports for a specific conversation (for batch loading bookmark states)
 */
export interface ConversationReportEntry {
  report_id: string
  message_index: number
}

export async function fetchConversationReports(
  conversationId: string
): Promise<ConversationReportEntry[]> {
  const url = `${API_BASE_URL}/reports/conversation/${encodeURIComponent(conversationId)}`

  const makeRequest = () => fetch(url, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<ConversationReportEntry[]>(response, makeRequest)
}

// ============================================================================
// Feedback API Functions
// ============================================================================

import type {
  MessageFeedback,
  MessageFeedbackCreate,
  ConversationFeedbackList,
} from '../types/feedback'

/**
 * Create or update feedback for a message (upsert behavior)
 */
export async function createFeedback(data: MessageFeedbackCreate): Promise<MessageFeedback> {
  const makeRequest = () => fetch(`${API_BASE_URL}/feedback`, {
    method: 'POST',
    headers: getHeaders(),
    body: JSON.stringify(data),
  })

  const response = await makeRequest()
  return handleResponse<MessageFeedback>(response, makeRequest)
}

/**
 * List all feedback for a specific conversation (batch loading)
 */
export async function fetchConversationFeedback(
  conversationId: string
): Promise<ConversationFeedbackList> {
  const url = `${API_BASE_URL}/feedback/conversation/${encodeURIComponent(conversationId)}`

  const makeRequest = () => fetch(url, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<ConversationFeedbackList>(response, makeRequest)
}

/**
 * Delete feedback for a specific message
 */
export async function deleteFeedbackByMessage(
  conversationId: string,
  messageIndex: number
): Promise<void> {
  const makeRequest = () => fetch(
    `${API_BASE_URL}/feedback/message/${encodeURIComponent(conversationId)}/${messageIndex}`,
    {
      method: 'DELETE',
      headers: getHeaders(),
    }
  )

  const response = await makeRequest()

  if (response.status === 204) {
    return
  }

  return handleResponse<void>(response, makeRequest)
}

// ============================================================================
// Database API
// ============================================================================

import type {
  DatabaseListResponse,
  ConnectDatabaseResponse,
} from '../types/database'

/**
 * Fetch all available databases
 */
export async function fetchDatabases(): Promise<DatabaseListResponse> {
  const makeRequest = () => fetch(`${API_BASE_URL}/databases`, {
    method: 'GET',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<DatabaseListResponse>(response, makeRequest)
}

/**
 * Connect to a specific database
 * Validates connection and sets it as active for the session
 */
export async function connectToDatabase(
  databaseId: string,
): Promise<ConnectDatabaseResponse> {
  const makeRequest = () => fetch(`${API_BASE_URL}/databases/${encodeURIComponent(databaseId)}/connect`, {
    method: 'POST',
    headers: getHeaders(),
  })

  const response = await makeRequest()
  return handleResponse<ConnectDatabaseResponse>(response, makeRequest)
}

