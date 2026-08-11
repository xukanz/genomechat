/**
 * Message feedback type definitions for AI response evaluation.
 */

export type FeedbackType = "positive" | "negative"

export interface MessageFeedback {
  id: string
  user_id: string
  conversation_id: string
  message_index: number
  feedback_type: FeedbackType
  note: string | null
  created_at: string
  updated_at: string
}

export interface MessageFeedbackCreate {
  conversation_id: string
  message_index: number
  feedback_type: FeedbackType
  note?: string
}

export interface ConversationFeedbackEntry {
  feedback_id: string
  message_index: number
  feedback_type: FeedbackType
}

export interface ConversationFeedbackList {
  feedback: ConversationFeedbackEntry[]
  count: number
}
