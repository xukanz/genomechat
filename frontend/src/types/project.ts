/**
 * Project type definitions matching backend Pydantic models
 */

export interface ProjectShare {
  user_id: string
  user_email: string
  user_name: string | null
  shared_by: string
  shared_at: string
}

export interface Project {
  id: string
  user_id: string
  name: string
  description: string | null
  color: string | null
  created_at: string
  updated_at: string
  is_default: boolean
  conversation_count: number
  artifact_count: number
  report_count: number
  last_conversation_at: string | null
  // Sharing fields
  shares: ProjectShare[]
  is_owner: boolean
  is_shared: boolean
}

export interface UserSummary {
  id: string
  email: string
  name: string
}

export interface UserSearchResult {
  users: UserSummary[]
  count: number
}

export interface ProjectCreate {
  name: string
  description?: string
  color?: string
}

export interface ProjectUpdate {
  name?: string
  description?: string | null
  color?: string | null
}

export interface ProjectList {
  projects: Project[]
  count: number
}

// ============================================================================
// Snippet Types
// ============================================================================

export type SnippetCategory =
  | 'visualization'
  | 'data_processing'
  | 'statistics'
  | 'file_operations'
  | 'domain_specific'
  | 'custom'

export interface Snippet {
  id: string
  name: string
  category: SnippetCategory
  description: string | null
  code: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface SnippetCreate {
  name: string
  category?: SnippetCategory
  description: string
  code: string
  enabled?: boolean
}

export interface SnippetUpdate {
  name?: string
  category?: SnippetCategory
  description?: string | null
  code?: string
  enabled?: boolean
}

export interface SnippetList {
  snippets: Snippet[]
  count: number
}
