/**
 * Database store using Zustand
 * Manages database profiles and active database state
 */

import { create } from 'zustand'
import type { DatabaseInfo } from '../types/database'
import { fetchDatabases, connectToDatabase as apiConnectToDatabase } from '../services/api'

interface DatabaseStore {
  // State
  databases: DatabaseInfo[]
  activeDatabase: string | null
  isLoading: boolean
  isConnecting: boolean
  error: string | null
  connectionError: string | null
  lastFetched: number | null

  // Actions
  loadDatabases: () => Promise<void>
  connectToDatabase: (databaseId: string) => Promise<boolean>
  getActiveDatabase: () => DatabaseInfo | null
  clearError: () => void
  clearConnectionError: () => void
}

// Cache TTL: 5 minutes (databases don't change often)
const CACHE_TTL_MS = 5 * 60 * 1000

export const useDatabaseStore = create<DatabaseStore>((set, get) => ({
  // Initial state
  databases: [],
  activeDatabase: null,
  isLoading: false,
  isConnecting: false,
  error: null,
  connectionError: null,
  lastFetched: null,

  /**
   * Load all available databases from the API
   */
  loadDatabases: async () => {
    const { lastFetched, isLoading } = get()

    // Skip if already loading
    if (isLoading) {
      return
    }

    // Use cache if fresh
    if (lastFetched && Date.now() - lastFetched < CACHE_TTL_MS) {
      console.log('[DatabaseStore] Using cached databases')
      return
    }

    console.log('[DatabaseStore] Loading databases...')
    set({ isLoading: true, error: null })

    try {
      const response = await fetchDatabases()

      set({
        databases: response.databases,
        activeDatabase: response.active_database,
        isLoading: false,
        lastFetched: Date.now(),
      })

      console.log('[DatabaseStore] Loaded databases:', response.databases.length)
    } catch (error) {
      console.error('[DatabaseStore] Failed to load databases:', error)
      set({
        isLoading: false,
        error: error instanceof Error ? error.message : 'Failed to load databases',
      })
    }
  },

  /**
   * Connect to a specific database
   * Returns true on success, false on failure
   */
  connectToDatabase: async (databaseId: string) => {
    const { isConnecting } = get()

    if (isConnecting) {
      console.log('[DatabaseStore] Connection already in progress')
      return false
    }

    console.log(`[DatabaseStore] Connecting to database: ${databaseId}`)
    set({ isConnecting: true, connectionError: null })

    try {
      const response = await apiConnectToDatabase(databaseId)

      if (response.success) {
        // Update local state to reflect new active database
        set((state) => ({
          activeDatabase: databaseId,
          isConnecting: false,
          databases: state.databases.map((db) => ({
            ...db,
            is_active: db.id === databaseId,
            status: db.id === databaseId ? 'connected' : 'available',
          })),
          // Invalidate cache to force refresh on next load
          lastFetched: null,
        }))

        console.log(`[DatabaseStore] Connected to: ${databaseId}`)
        return true
      } else {
        set({
          isConnecting: false,
          connectionError: response.message || 'Connection failed',
        })
        return false
      }
    } catch (error) {
      console.error('[DatabaseStore] Connection failed:', error)
      set({
        isConnecting: false,
        connectionError: error instanceof Error ? error.message : 'Connection failed',
      })
      return false
    }
  },

  /**
   * Get the currently active database info
   */
  getActiveDatabase: () => {
    const { databases, activeDatabase } = get()
    return databases.find((db) => db.id === activeDatabase) || null
  },

  /**
   * Clear any error state
   */
  clearError: () => {
    set({ error: null })
  },

  /**
   * Clear connection error state
   */
  clearConnectionError: () => {
    set({ connectionError: null })
  },
}))
