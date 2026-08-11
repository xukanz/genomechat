/**
 * Authentication store using Zustand
 * Manages auth state with localStorage persistence
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '@/types/auth'
import {
  loginUser as apiLogin,
  registerUser as apiRegister,
  refreshAccessToken as apiRefresh,
  getCurrentUser as apiGetCurrentUser,
  logoutUser as apiLogout,
  updateProfile as apiUpdateProfile,
} from '@/services/authApi'
import { useConversationStore } from './conversationStore'
import { useProjectStore } from './projectStore'
import { useReportStore } from './reportStore'
import { useArtifactStore } from './artifactStore'
import { useFeedbackStore } from './feedbackStore'

interface AuthStore {
  // State
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Actions
  login: (email: string, password: string) => Promise<void>
  register: (email: string, name: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refreshAccessToken: () => Promise<boolean>
  fetchCurrentUser: () => Promise<void>
  updateProfile: (name: string) => Promise<void>
  clearError: () => void
  setTokens: (accessToken: string, refreshToken: string, user: User) => void
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      // Login action
      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null })

        try {
          const response = await apiLogin(email, password)
          
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          })
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Login failed'
          set({
            error: errorMessage,
            isLoading: false,
            isAuthenticated: false,
          })
          throw error
        }
      },

      // Register action
      register: async (email: string, name: string, password: string) => {
        set({ isLoading: true, error: null })

        try {
          const response = await apiRegister(email, name, password)
          
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          })
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Registration failed'
          set({
            error: errorMessage,
            isLoading: false,
            isAuthenticated: false,
          })
          throw error
        }
      },

      // Logout action
      logout: async () => {
        const { accessToken } = get()

        // Call server logout if we have a token
        if (accessToken) {
          try {
            await apiLogout(accessToken)
          } catch (error) {
            console.error('Logout API call failed:', error)
            // Continue with client-side logout even if server call fails
          }
        }

        // Reset all stores to clear user-specific data
        useConversationStore.getState().reset()
        useProjectStore.getState().reset()
        useReportStore.getState().reset()
        useArtifactStore.getState().clearArtifacts()
        useFeedbackStore.getState().reset()

        // Clear local state
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        })
      },

      // Refresh access token
      refreshAccessToken: async () => {
        const { refreshToken } = get()

        if (!refreshToken) {
          return false
        }

        try {
          const response = await apiRefresh(refreshToken)
          
          set({
            user: response.user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
          })
          
          return true
        } catch (error) {
          console.error('Token refresh failed:', error)
          // Clear auth state on refresh failure
          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          })
          return false
        }
      },

      // Fetch current user
      fetchCurrentUser: async () => {
        const { accessToken } = get()

        if (!accessToken) {
          return
        }

        try {
          const user = await apiGetCurrentUser(accessToken)
          set({ user })
        } catch (error) {
          console.error('Failed to fetch current user:', error)
          // Don't clear auth on this failure - token might still be valid
        }
      },

      // Update user profile
      updateProfile: async (name: string) => {
        const { accessToken } = get()

        if (!accessToken) {
          throw new Error('Not authenticated')
        }

        set({ isLoading: true, error: null })

        try {
          const updatedUser = await apiUpdateProfile(accessToken, { name })
          set({ user: updatedUser, isLoading: false })
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Failed to update profile'
          set({ error: errorMessage, isLoading: false })
          throw error
        }
      },

      // Clear error
      clearError: () => {
        set({ error: null })
      },

      // Set tokens (for external use like after registration)
      setTokens: (accessToken: string, refreshToken: string, user: User) => {
        set({
          accessToken,
          refreshToken,
          user,
          isAuthenticated: true,
        })
      },
    }),
    {
      name: 'auth-storage', // localStorage key
      partialize: (state) => ({
        // Only persist these fields
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
)
