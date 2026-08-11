/**
 * Feedback store using Zustand
 * Manages message feedback state (thumbs up/down)
 */

import { create } from 'zustand'
import type { FeedbackType, MessageFeedbackCreate } from '../types/feedback'
import {
  createFeedback as apiCreateFeedback,
  deleteFeedbackByMessage as apiDeleteFeedbackByMessage,
  fetchConversationFeedback,
} from '../services/api'

// Helper to create feedback key
const makeFeedbackKey = (conversationId: string, messageIndex: number) =>
  `${conversationId}:${messageIndex}`

interface FeedbackEntry {
  feedbackId: string
  feedbackType: FeedbackType
}

interface FeedbackState {
  // State: key = "conversationId:messageIndex", value = { feedbackId, feedbackType }
  feedbackMap: Record<string, FeedbackEntry>
  loadingConversationId: string | null
  isSaving: boolean
  error: string | null

  // Actions
  loadFeedbackForConversation: (conversationId: string) => Promise<void>
  submitFeedback: (data: MessageFeedbackCreate) => Promise<void>
  removeFeedback: (conversationId: string, messageIndex: number) => Promise<void>
  getFeedback: (conversationId: string, messageIndex: number) => FeedbackType | null
  getFeedbackId: (conversationId: string, messageIndex: number) => string | null
  clearFeedback: () => void
  clearError: () => void
  reset: () => void
}

const initialState = {
  feedbackMap: {} as Record<string, FeedbackEntry>,
  loadingConversationId: null as string | null,
  isSaving: false,
  error: null as string | null,
}

export const useFeedbackStore = create<FeedbackState>((set, get) => ({
  ...initialState,

  // Load all feedback for a conversation (batch loading for efficiency)
  loadFeedbackForConversation: async (conversationId: string) => {
    const { loadingConversationId } = get()

    // Skip if already loading this conversation
    if (loadingConversationId === conversationId) {
      return
    }

    set({ loadingConversationId: conversationId })

    try {
      const result = await fetchConversationFeedback(conversationId)
      const { feedbackMap } = get()

      // Build new feedback map
      const newFeedbackMap: Record<string, FeedbackEntry> = { ...feedbackMap }
      for (const entry of result.feedback) {
        const key = makeFeedbackKey(conversationId, entry.message_index)
        newFeedbackMap[key] = {
          feedbackId: entry.feedback_id,
          feedbackType: entry.feedback_type,
        }
      }

      set({
        feedbackMap: newFeedbackMap,
        loadingConversationId: null,
      })
    } catch (error) {
      console.error('Failed to load feedback for conversation:', error)
      set({ loadingConversationId: null })
    }
  },

  // Submit feedback for a message (creates or updates)
  submitFeedback: async (data: MessageFeedbackCreate) => {
    const { feedbackMap } = get()
    const key = makeFeedbackKey(data.conversation_id, data.message_index)

    // Optimistic update
    const previousFeedbackMap = feedbackMap
    set({
      isSaving: true,
      error: null,
      feedbackMap: {
        ...feedbackMap,
        [key]: {
          feedbackId: 'pending', // Temporary ID until API responds
          feedbackType: data.feedback_type,
        },
      },
    })

    try {
      const feedback = await apiCreateFeedback(data)

      // Update with real feedback ID
      set({
        isSaving: false,
        feedbackMap: {
          ...get().feedbackMap,
          [key]: {
            feedbackId: feedback.id,
            feedbackType: feedback.feedback_type,
          },
        },
      })
    } catch (error) {
      // Rollback on error
      const errorMessage = error instanceof Error ? error.message : 'Failed to save feedback'
      set({
        feedbackMap: previousFeedbackMap,
        isSaving: false,
        error: errorMessage,
      })
      console.error('Failed to submit feedback:', error)
      throw error
    }
  },

  // Remove feedback for a message (toggle off)
  removeFeedback: async (conversationId: string, messageIndex: number) => {
    const { feedbackMap } = get()
    const key = makeFeedbackKey(conversationId, messageIndex)

    // Check if feedback exists
    if (!feedbackMap[key]) {
      return
    }

    // Optimistic update
    const previousFeedbackMap = feedbackMap
    const updatedFeedbackMap = { ...feedbackMap }
    delete updatedFeedbackMap[key]

    set({
      isSaving: true,
      error: null,
      feedbackMap: updatedFeedbackMap,
    })

    try {
      await apiDeleteFeedbackByMessage(conversationId, messageIndex)
      set({ isSaving: false })
    } catch (error) {
      // Rollback on error
      const errorMessage = error instanceof Error ? error.message : 'Failed to remove feedback'
      set({
        feedbackMap: previousFeedbackMap,
        isSaving: false,
        error: errorMessage,
      })
      console.error('Failed to remove feedback:', error)
      throw error
    }
  },

  // Get feedback type for a message (null if no feedback)
  getFeedback: (conversationId: string, messageIndex: number) => {
    const { feedbackMap } = get()
    const key = makeFeedbackKey(conversationId, messageIndex)
    return feedbackMap[key]?.feedbackType || null
  },

  // Get feedback ID for a message (null if no feedback)
  getFeedbackId: (conversationId: string, messageIndex: number) => {
    const { feedbackMap } = get()
    const key = makeFeedbackKey(conversationId, messageIndex)
    return feedbackMap[key]?.feedbackId || null
  },

  // Clear all feedback (useful when logging out)
  clearFeedback: () => {
    set({ feedbackMap: {} })
  },

  // Clear error message
  clearError: () => {
    set({ error: null })
  },

  // Reset store to initial state
  reset: () => {
    set(initialState)
  },
}))
