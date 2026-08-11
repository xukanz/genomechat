/**
 * Report type definitions matching backend Pydantic models
 */

export interface Report {
  id: string
  user_id: string
  conversation_id: string
  conversation_title: string
  project_id: string | null
  title: string
  content: string
  message_index: number
  created_at: string
  updated_at: string
}

export interface ReportCreate {
  conversation_id: string
  title: string
  content: string
  message_index: number
}

export interface ReportUpdate {
  title?: string
}

export interface ReportList {
  reports: Report[]
  count: number
}
