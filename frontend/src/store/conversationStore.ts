/**
 * Conversation store using Zustand
 * Manages conversation list state and operations
 */

import { create } from 'zustand'
import type { Conversation, TokenUsage } from '../types/conversation'
import {
  fetchConversations,
  deleteConversation as apiDeleteConversation,
  updateConversationTitle as apiUpdateConversationTitle,
} from '../services/api'

interface ConversationState {
  // State
  conversations: Conversation[]
  currentConversationId: string | null
  isLoading: boolean
  error: string | null

  // Streaming state - tracks active streams for confirmation dialog
  isStreaming: boolean
  isDeepResearch: boolean
  streamStartTime: number | null
  pendingSwitchId: string | null // Conversation ID user wants to switch to (null = new chat)
  showSwitchConfirmation: boolean

  // Context usage state
  contextUsage: TokenUsage | null

  // Actions
  loadConversations: (projectId?: string | null) => Promise<void>
  setCurrentConversation: (id: string | null) => void
  deleteConversation: (id: string) => Promise<void>
  updateConversationTitle: (id: string, title: string) => Promise<void>
  startNewChat: () => void
  addConversation: (conversation: Conversation) => void
  clearError: () => void
  reset: () => void

  // Context usage actions
  setContextUsage: (usage: TokenUsage | null) => void

  // Streaming actions
  setStreamingState: (isStreaming: boolean, isDeepResearch?: boolean) => void
  requestConversationSwitch: (targetId: string | null) => void
  confirmSwitch: () => void
  cancelSwitch: () => void
}

// Threshold for showing confirmation dialog (2 seconds)
// Reduced from 10s to catch orchestrator routing scenarios where no tokens are emitted
const STREAM_CONFIRMATION_THRESHOLD_MS = 2000

export const useConversationStore = create<ConversationState>((set, get) => ({
  // Initial state
  conversations: [],
  currentConversationId: null,
  isLoading: false,
  error: null,

  // Streaming state
  isStreaming: false,
  isDeepResearch: false,
  streamStartTime: null,
  pendingSwitchId: null,
  showSwitchConfirmation: false,

  // Context usage state
  contextUsage: null,

  // Load all conversations from API (optionally filtered by project)
  loadConversations: async (projectId?: string | null) => {
    set({ isLoading: true, error: null })

    try {
      const result = await fetchConversations(projectId || undefined)
      set({
        conversations: result.conversations,
        isLoading: false,
      })
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load conversations'
      set({
        error: errorMessage,
        isLoading: false,
      })
      console.error('Failed to load conversations:', error)
    }
  },

  // Set current active conversation
  setCurrentConversation: (id: string | null) => {
    set({ currentConversationId: id })
  },

  // Delete conversation with optimistic update
  deleteConversation: async (id: string) => {
    const { conversations, currentConversationId } = get()

    // Optimistic update: remove from UI immediately
    const previousConversations = conversations
    const updatedConversations = conversations.filter((conv) => conv.id !== id)
    set({ conversations: updatedConversations })

    // Clear current conversation if it was deleted
    if (currentConversationId === id) {
      set({ currentConversationId: null })
    }

    try {
      await apiDeleteConversation(id)
    } catch (error) {
      // Rollback on error
      set({
        conversations: previousConversations,
        error: error instanceof Error ? error.message : 'Failed to delete conversation',
      })
      console.error('Failed to delete conversation:', error)
    }
  },

  // Update conversation title with optimistic update
  updateConversationTitle: async (id: string, title: string) => {
    const { conversations } = get()

    // Optimistic update: update in UI immediately
    const previousConversations = conversations
    const updatedConversations = conversations.map((conv) =>
      conv.id === id ? { ...conv, title, updated_at: new Date().toISOString() } : conv
    )
    set({ conversations: updatedConversations })

    try {
      const updated = await apiUpdateConversationTitle(id, title)
      // Update with server response
      set({
        conversations: conversations.map((conv) => (conv.id === id ? updated : conv)),
      })
    } catch (error) {
      // Rollback on error
      set({
        conversations: previousConversations,
        error: error instanceof Error ? error.message : 'Failed to update conversation title',
      })
      console.error('Failed to update conversation title:', error)
    }
  },

  // Start a new chat (clear current conversation)
  startNewChat: () => {
    set({ currentConversationId: null })
  },

  // Add a new conversation to the list (called after first message creates conversation)
  addConversation: (conversation: Conversation) => {
    const { conversations } = get()
    // Check if conversation already exists
    const exists = conversations.some((conv) => conv.id === conversation.id)
    if (!exists) {
      set({
        conversations: [conversation, ...conversations], // Add to beginning (most recent)
      })
    }
  },

  // Clear error message
  clearError: () => {
    set({ error: null })
  },

  // Reset store to initial state (called on logout)
  reset: () => {
    set({
      conversations: [],
      currentConversationId: null,
      isLoading: false,
      error: null,
      isStreaming: false,
      isDeepResearch: false,
      streamStartTime: null,
      pendingSwitchId: null,
      showSwitchConfirmation: false,
      contextUsage: null,
    })
  },

  // Set context usage (called by useChat hook on end event)
  setContextUsage: (usage) => set({ contextUsage: usage }),

  // Set streaming state (called by useChat hook)
  setStreamingState: (isStreaming: boolean, isDeepResearch?: boolean) => {
    if (isStreaming) {
      set({
        isStreaming: true,
        isDeepResearch: isDeepResearch ?? false,
        streamStartTime: Date.now(),
      })
    } else {
      set({
        isStreaming: false,
        isDeepResearch: false,
        streamStartTime: null,
      })
    }
  },

  // Request to switch conversation - shows confirmation if needed
  requestConversationSwitch: (targetId: string | null) => {
    const { isStreaming, isDeepResearch, streamStartTime, currentConversationId } = get()

    // If not streaming, switch immediately
    if (!isStreaming) {
      set({ currentConversationId: targetId })
      return
    }

    // If switching to the same existing conversation, ignore
    // Note: null === null should NOT be ignored - user wants to start a fresh new chat
    if (targetId !== null && targetId === currentConversationId) {
      return
    }

    // Calculate how long the stream has been running
    const streamDuration = streamStartTime ? Date.now() - streamStartTime : 0
    const isLongRunning = streamDuration > STREAM_CONFIRMATION_THRESHOLD_MS

    // Show confirmation for deep research OR long-running streams
    if (isDeepResearch || isLongRunning) {
      set({
        pendingSwitchId: targetId,
        showSwitchConfirmation: true,
      })
    } else {
      // Short stream - switch immediately (will be cancelled by useChat)
      set({ currentConversationId: targetId })
    }
  },

  // Confirm the pending switch (user clicked "Stop & Switch")
  confirmSwitch: () => {
    const { pendingSwitchId } = get()
    set({
      currentConversationId: pendingSwitchId,
      pendingSwitchId: null,
      showSwitchConfirmation: false,
    })
  },

  // Cancel the pending switch (user clicked "Continue")
  cancelSwitch: () => {
    set({
      pendingSwitchId: null,
      showSwitchConfirmation: false,
    })
  },
}))
