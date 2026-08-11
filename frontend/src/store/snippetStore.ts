/**
 * Zustand store for snippet management
 */

import { create } from 'zustand'
import type { Snippet, SnippetCreate, SnippetUpdate } from '../types/project'
import {
  fetchSnippets,
  createSnippet as apiCreateSnippet,
  updateSnippet as apiUpdateSnippet,
  deleteSnippet as apiDeleteSnippet,
  toggleSnippet as apiToggleSnippet,
} from '../services/api'

interface SnippetState {
  // State
  snippets: Snippet[]
  currentProjectId: string | null
  isLoading: boolean
  error: string | null

  // Actions
  loadSnippets: (projectId: string) => Promise<void>
  createSnippet: (projectId: string, data: SnippetCreate) => Promise<Snippet>
  updateSnippet: (projectId: string, snippetId: string, updates: SnippetUpdate) => Promise<Snippet>
  deleteSnippet: (projectId: string, snippetId: string) => Promise<void>
  toggleSnippet: (projectId: string, snippetId: string) => Promise<Snippet>
  clearSnippets: () => void
  clearError: () => void
}

const initialState = {
  snippets: [],
  currentProjectId: null,
  isLoading: false,
  error: null,
}

export const useSnippetStore = create<SnippetState>((set, get) => ({
  ...initialState,

  /**
   * Load all snippets for a project
   */
  loadSnippets: async (projectId: string) => {
    set({ isLoading: true, error: null, currentProjectId: projectId })

    try {
      const result = await fetchSnippets(projectId)
      set({
        snippets: result.snippets,
        isLoading: false,
      })
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load snippets'
      set({
        error: errorMessage,
        isLoading: false,
        snippets: [],
      })
      console.error('Failed to load snippets:', error)
    }
  },

  /**
   * Create a new snippet
   */
  createSnippet: async (projectId: string, data: SnippetCreate) => {
    set({ isLoading: true, error: null })

    try {
      const snippet = await apiCreateSnippet(projectId, data)

      set((state) => ({
        snippets: [...state.snippets, snippet],
        isLoading: false,
      }))

      return snippet
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create snippet'
      set({
        error: errorMessage,
        isLoading: false,
      })
      throw error
    }
  },

  /**
   * Update a snippet with optimistic update
   */
  updateSnippet: async (projectId: string, snippetId: string, updates: SnippetUpdate) => {
    const { snippets } = get()

    // Optimistic update
    const previousSnippets = snippets
    const updatedSnippets = snippets.map((snippet) =>
      snippet.id === snippetId
        ? { ...snippet, ...updates, updated_at: new Date().toISOString() }
        : snippet
    )
    set({ snippets: updatedSnippets })

    try {
      const updated = await apiUpdateSnippet(projectId, snippetId, updates)

      set({
        snippets: snippets.map((snippet) =>
          snippet.id === snippetId ? updated : snippet
        ),
      })

      return updated
    } catch (error) {
      // Rollback on error
      set({
        snippets: previousSnippets,
        error: error instanceof Error ? error.message : 'Failed to update snippet',
      })
      throw error
    }
  },

  /**
   * Delete a snippet with optimistic update
   */
  deleteSnippet: async (projectId: string, snippetId: string) => {
    const { snippets } = get()

    // Optimistic update
    const previousSnippets = snippets
    const updatedSnippets = snippets.filter((snippet) => snippet.id !== snippetId)
    set({ snippets: updatedSnippets })

    try {
      await apiDeleteSnippet(projectId, snippetId)
    } catch (error) {
      // Rollback on error
      set({
        snippets: previousSnippets,
        error: error instanceof Error ? error.message : 'Failed to delete snippet',
      })
      throw error
    }
  },

  /**
   * Toggle a snippet's enabled status with optimistic update
   */
  toggleSnippet: async (projectId: string, snippetId: string) => {
    const { snippets } = get()

    // Optimistic update
    const previousSnippets = snippets
    const updatedSnippets = snippets.map((snippet) =>
      snippet.id === snippetId
        ? { ...snippet, enabled: !snippet.enabled, updated_at: new Date().toISOString() }
        : snippet
    )
    set({ snippets: updatedSnippets })

    try {
      const updated = await apiToggleSnippet(projectId, snippetId)

      set({
        snippets: snippets.map((snippet) =>
          snippet.id === snippetId ? updated : snippet
        ),
      })

      return updated
    } catch (error) {
      // Rollback on error
      set({
        snippets: previousSnippets,
        error: error instanceof Error ? error.message : 'Failed to toggle snippet',
      })
      throw error
    }
  },

  /**
   * Clear snippets (when switching projects)
   */
  clearSnippets: () => {
    set({ snippets: [], currentProjectId: null })
  },

  /**
   * Clear error message
   */
  clearError: () => {
    set({ error: null })
  },
}))
