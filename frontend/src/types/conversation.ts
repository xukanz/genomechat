/**
 * Conversation type definitions matching backend Pydantic models
 */

export interface Conversation {
  id: string
  user_id: string
  title: string
  project_id?: string | null
  created_at: string // ISO 8601 datetime string
  updated_at: string // ISO 8601 datetime string
}

export interface ConversationWithMessages extends Conversation {
  messages: Array<{
    type: string
    content: string
    [key: string]: any // Allow additional message properties
  }>
  token_usage?: TokenUsage | null
}

export interface ConversationList {
  conversations: Conversation[]
  count: number
}

export interface UpdateTitleRequest {
  title: string
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp?: string
}

export interface ChatRequest {
  message: string
  thread_id?: string | null
  project_id?: string | null
  research_mode?: 'standard' | 'deep_research'
  code_language?: 'python' | 'r' | 'auto'
  database_id?: string | null
  /**
   * Per-request coder backend override (Phase 2, Workstream A).
   * When set, takes precedence over the server's settings.coder_backend
   * for THIS request only. Omitted / null = server default.
   */
  coder_backend?: AgentBackend | null
  /**
   * Per-request orchestrator backend override (Phase 2, Workstream B).
   * Same semantics as coder_backend. The SDK orchestrator is a prototype —
   * enabling it routes the ENTIRE multi-worker plan through the Claude
   * Agent SDK's self-driving path instead of the LangGraph loop.
   */
  orchestrator_backend?: AgentBackend | null
}

export interface ChatResponse {
  message: string
  thread_id: string
}

export interface TokenUsage {
  estimated_tokens: number
  max_tokens: number
  usage_pct: number
}

/**
 * Agent backend runtime — populated on worker-node agent_start / agent_end
 * events (Coder, Orchestrator). 'sdk' means the turn ran
 * through claude-agent-sdk; 'langchain' or null means the default path.
 * Non-worker events (Coordinator, SQL Agent) always leave this null.
 */
export type AgentBackend = 'langchain' | 'sdk'

export interface StreamEvent {
  type: 'token' | 'plan' | 'agent_start' | 'agent_end' | 'thinking' | 'error' | 'end' | 'file'
  content: string
  thread_id?: string | null
  agent_name?: string
  agent_backend?: AgentBackend | null
  file_metadata?: {
    filename: string
    s3_bucket: string
    s3_key: string
    file_type: string
    content_type: string
    url: string
    is_image: boolean
  }
  token_usage?: TokenUsage | null
}

export interface AgentActivity {
  agent: string
  status: 'thinking' | 'working' | 'completed' | 'failed'
  content?: string
  startTime: Date
  endTime?: Date
  /** Backend runtime for this turn — 'sdk' surfaces a Claude Agent SDK badge. */
  backend?: AgentBackend | null
}

export interface PlanStep {
  title: string
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
  agent_name?: string
}

export interface Plan {
  title?: string
  thought?: string
  steps: PlanStep[]
}
