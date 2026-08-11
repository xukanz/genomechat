/**
 * Zustand store for project management
 */

import { create } from 'zustand'
import type { Project } from '../types/project'
import {
  fetchProjects,
  createProject as apiCreateProject,
  updateProject as apiUpdateProject,
  deleteProject as apiDeleteProject,
  moveConversationToProject as apiMoveConversation,
  shareProject as apiShareProject,
  removeShare as apiRemoveShare,
} from '../services/api'

interface ProjectState {
  // State
  projects: Project[]
  selectedProjectId: string | null
  isLoading: boolean
  error: string | null

  // Actions
  loadProjects: () => Promise<void>
  getDefaultProject: () => Project | null
  setSelectedProject: (projectId: string | null) => void
  createProject: (name: string, description?: string, color?: string) => Promise<Project>
  updateProject: (projectId: string, updates: Partial<Project>) => Promise<void>
  deleteProject: (projectId: string) => Promise<void>
  moveConversation: (conversationId: string, projectId: string) => Promise<void>
  // Sharing actions
  shareProject: (projectId: string, userId: string) => Promise<void>
  removeShare: (projectId: string, userId: string) => Promise<void>
  clearError: () => void
  reset: () => void
}

const initialState = {
  projects: [],
  selectedProjectId: null,
  isLoading: false,
  error: null,
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  ...initialState,

  /**
   * Load all projects from API
   */
  loadProjects: async () => {
    set({ isLoading: true, error: null })

    try {
      const result = await fetchProjects()
      const defaultProject = result.projects.find(p => p.is_default)
      
      set({
        projects: result.projects,
        // Auto-select default project if no project is selected
        selectedProjectId: get().selectedProjectId || defaultProject?.id || null,
        isLoading: false,
      })
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load projects'
      set({
        error: errorMessage,
        isLoading: false,
      })
      console.error('Failed to load projects:', error)
    }
  },

  /**
   * Get the default project
   */
  getDefaultProject: () => {
    return get().projects.find(p => p.is_default) || null
  },

  /**
   * Set the currently selected project
   */
  setSelectedProject: (projectId: string | null) => {
    set({ selectedProjectId: projectId })
  },

  /**
   * Create a new project
   */
  createProject: async (name: string, description?: string, color?: string) => {
    set({ isLoading: true, error: null })

    try {
      const project = await apiCreateProject({ name, description, color })
      
      set((state) => ({
        projects: [project, ...state.projects],
        isLoading: false,
      }))
      
      return project
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to create project'
      set({
        error: errorMessage,
        isLoading: false,
      })
      throw error
    }
  },

  /**
   * Update a project with optimistic update
   */
  updateProject: async (projectId: string, updates: Partial<Project>) => {
    const { projects } = get()

    // Optimistic update
    const previousProjects = projects
    const updatedProjects = projects.map((proj) =>
      proj.id === projectId
        ? { ...proj, ...updates, updated_at: new Date().toISOString() }
        : proj
    )
    set({ projects: updatedProjects })

    try {
      const updated = await apiUpdateProject(projectId, updates)
      
      set({
        projects: projects.map((proj) => (proj.id === projectId ? updated : proj)),
      })
    } catch (error) {
      // Rollback on error
      set({
        projects: previousProjects,
        error: error instanceof Error ? error.message : 'Failed to update project',
      })
      throw error
    }
  },

  /**
   * Delete a project with optimistic update
   */
  deleteProject: async (projectId: string) => {
    const { projects, selectedProjectId } = get()

    // Optimistic update
    const previousProjects = projects
    const previousSelectedId = selectedProjectId
    const updatedProjects = projects.filter((proj) => proj.id !== projectId)
    set({ projects: updatedProjects })

    // Clear selected project if it was deleted
    if (selectedProjectId === projectId) {
      // Find default project or set to null
      const defaultProject = updatedProjects.find((p) => p.is_default)
      set({ selectedProjectId: defaultProject?.id || null })
    }

    try {
      await apiDeleteProject(projectId)
    } catch (error) {
      // Rollback on error
      set({
        projects: previousProjects,
        selectedProjectId: previousSelectedId,
        error: error instanceof Error ? error.message : 'Failed to delete project',
      })
      throw error
    }
  },

  /**
   * Move a conversation to a different project
   */
  moveConversation: async (conversationId: string, projectId: string) => {
    try {
      await apiMoveConversation(conversationId, projectId)

      // Reload projects to update conversation counts
      await get().loadProjects()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to move conversation'
      set({ error: errorMessage })
      throw error
    }
  },

  /**
   * Share a project with another user
   */
  shareProject: async (projectId: string, userId: string) => {
    try {
      await apiShareProject(projectId, userId)

      // Reload projects to update shares list
      await get().loadProjects()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to share project'
      set({ error: errorMessage })
      throw error
    }
  },

  /**
   * Remove a user's access to a shared project
   */
  removeShare: async (projectId: string, userId: string) => {
    try {
      await apiRemoveShare(projectId, userId)

      // Reload projects to update shares list
      await get().loadProjects()
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to remove share'
      set({ error: errorMessage })
      throw error
    }
  },

  /**
   * Clear error message
   */
  clearError: () => {
    set({ error: null })
  },

  /**
   * Reset store to initial state
   */
  reset: () => {
    set(initialState)
  },
}))
