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
    // Passthrough for the rest of the LangGraph checkpoint message. `unknown`
    // would force a narrowing cast at every read site for no safety gain.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    [key: string]: any
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

export interface ChatRequest {
  message: string
  thread_id?: string | null
  project_id?: string | null
  research_mode?: 'standard' | 'deep_research'
  code_language?: 'python' | 'r' | 'auto'
  database_id?: string | null
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

export interface StreamEvent {
  type: 'token' | 'plan' | 'agent_start' | 'agent_end' | 'thinking' | 'error' | 'end' | 'file'
  content: string
  thread_id?: string | null
  agent_name?: string
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
