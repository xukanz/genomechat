/**
 * Report store using Zustand
 * Manages bookmarked AI responses (reports)
 */

import { create } from 'zustand'
import type { Report, ReportCreate } from '../types/report'
import {
  fetchReports,
  createReport as apiCreateReport,
  updateReport as apiUpdateReport,
  deleteReport as apiDeleteReport,
  fetchConversationReports,
} from '../services/api'

// Helper to create bookmark key
const makeBookmarkKey = (conversationId: string, messageIndex: number) =>
  `${conversationId}:${messageIndex}`

interface ReportState {
  // State
  reports: Report[]
  isLoading: boolean
  error: string | null
  // Bookmark tracking: key = "conversationId:messageIndex", value = reportId
  bookmarkedMessages: Record<string, string>
  loadingConversationId: string | null

  // Actions
  loadReports: (projectId?: string | null) => Promise<void>
  createReport: (data: ReportCreate) => Promise<Report>
  updateReportTitle: (reportId: string, title: string) => Promise<void>
  deleteReport: (reportId: string) => Promise<void>
  clearError: () => void
  reset: () => void
  // Bookmark tracking actions
  loadBookmarksForConversation: (conversationId: string) => Promise<void>
  isMessageBookmarked: (conversationId: string, messageIndex: number) => string | null
  clearBookmarks: () => void
}

const initialState = {
  reports: [],
  isLoading: false,
  error: null,
  bookmarkedMessages: {} as Record<string, string>,
  loadingConversationId: null,
}

export const useReportStore = create<ReportState>((set, get) => ({
  ...initialState,

  // Load all reports from API (optionally filtered by project)
  loadReports: async (projectId?: string | null) => {
    set({ isLoading: true, error: null })

    try {
      const result = await fetchReports(projectId || undefined)
      set({
        reports: result.reports,
        isLoading: false,
      })
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load reports'
      set({
        error: errorMessage,
        isLoading: false,
      })
      console.error('Failed to load reports:', error)
    }
  },

  // Create a new report
  createReport: async (data: ReportCreate) => {
    set({ error: null })

    try {
      const report = await apiCreateReport(data)
      const { reports, bookmarkedMessages } = get()

      // Add to bookmark tracking
      const key = makeBookmarkKey(data.conversation_id, data.message_index)

      set({
        reports: [report, ...reports], // Add to beginning (most recent)
        bookmarkedMessages: {
          ...bookmarkedMessages,
          [key]: report.id,
        },
      })
      return report
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create report'
      set({ error: errorMessage })
      console.error('Failed to create report:', error)
      throw error
    }
  },

  // Update report title with optimistic update
  updateReportTitle: async (reportId: string, title: string) => {
    const { reports } = get()

    // Optimistic update
    const previousReports = reports
    const updatedReports = reports.map((report) =>
      report.id === reportId
        ? { ...report, title, updated_at: new Date().toISOString() }
        : report
    )
    set({ reports: updatedReports })

    try {
      const updated = await apiUpdateReport(reportId, { title })
      set({
        reports: reports.map((report) => (report.id === reportId ? updated : report)),
      })
    } catch (error) {
      // Rollback on error
      set({
        reports: previousReports,
        error: error instanceof Error ? error.message : 'Failed to update report',
      })
      console.error('Failed to update report:', error)
    }
  },

  // Delete report with optimistic update
  deleteReport: async (reportId: string) => {
    const { reports, bookmarkedMessages } = get()

    // Find the report to get conversation_id and message_index for bookmark cleanup
    const reportToDelete = reports.find((r) => r.id === reportId)

    // Optimistic update
    const previousReports = reports
    const previousBookmarks = bookmarkedMessages
    const updatedReports = reports.filter((report) => report.id !== reportId)

    // Remove from bookmark tracking
    const updatedBookmarks = { ...bookmarkedMessages }
    if (reportToDelete) {
      const key = makeBookmarkKey(reportToDelete.conversation_id, reportToDelete.message_index)
      delete updatedBookmarks[key]
    }

    set({ reports: updatedReports, bookmarkedMessages: updatedBookmarks })

    try {
      await apiDeleteReport(reportId)
    } catch (error) {
      // Rollback on error
      set({
        reports: previousReports,
        bookmarkedMessages: previousBookmarks,
        error: error instanceof Error ? error.message : 'Failed to delete report',
      })
      console.error('Failed to delete report:', error)
    }
  },

  // Clear error message
  clearError: () => {
    set({ error: null })
  },

  // Reset store to initial state
  reset: () => {
    set(initialState)
  },

  // Load all bookmarks for a conversation (batch loading for efficiency)
  loadBookmarksForConversation: async (conversationId: string) => {
    const { loadingConversationId } = get()

    // Skip if already loading this conversation
    if (loadingConversationId === conversationId) {
      return
    }

    set({ loadingConversationId: conversationId })

    try {
      const entries = await fetchConversationReports(conversationId)
      const { bookmarkedMessages } = get()

      // Build new bookmarks map
      const newBookmarks: Record<string, string> = { ...bookmarkedMessages }
      for (const entry of entries) {
        const key = makeBookmarkKey(conversationId, entry.message_index)
        newBookmarks[key] = entry.report_id
      }

      set({
        bookmarkedMessages: newBookmarks,
        loadingConversationId: null,
      })
    } catch (error) {
      console.error('Failed to load bookmarks for conversation:', error)
      set({ loadingConversationId: null })
    }
  },

  // Check if a message is bookmarked, returns report_id or null
  isMessageBookmarked: (conversationId: string, messageIndex: number) => {
    const { bookmarkedMessages } = get()
    const key = makeBookmarkKey(conversationId, messageIndex)
    return bookmarkedMessages[key] || null
  },

  // Clear all bookmarks (useful when switching conversations)
  clearBookmarks: () => {
    set({ bookmarkedMessages: {} })
  },
}))
