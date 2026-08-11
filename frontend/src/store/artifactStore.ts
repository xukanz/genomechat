/**
 * Artifacts store using Zustand
 * Manages artifact state for files and plots generated in conversations
 */

import { create } from 'zustand'

export interface Artifact {
  file_id: string
  user_id: string | null
  thread_id: string | null
  conversation_id: string | null
  conversation_title: string | null
  file_type: 'query_result' | 'coder_output' | 'analysis' | 'other'
  s3_bucket: string
  s3_key: string
  content_type: string
  size_bytes: number
  metadata: Record<string, any>
  created_at: string
}

// URL cache with expiration (50 minutes to allow buffer before 60-minute expiry)
const URL_CACHE_TTL_MS = 50 * 60 * 1000
const urlCache: Map<string, { url: string; expiry: number }> = new Map()

function getCachedUrl(fileId: string): string | null {
  const cached = urlCache.get(fileId)
  if (cached && Date.now() < cached.expiry) {
    return cached.url
  }
  if (cached) {
    urlCache.delete(fileId)
  }
  return null
}

function setCachedUrl(fileId: string, url: string): void {
  urlCache.set(fileId, { url, expiry: Date.now() + URL_CACHE_TTL_MS })
}

interface ArtifactStore {
  // State
  artifacts: Artifact[]
  artifactUrls: Record<string, string> // file_id -> download_url
  isLoading: boolean
  isLoadingUrls: boolean
  error: string | null
  hasMore: boolean
  currentPage: number

  // Actions
  loadArtifacts: (threadId?: string, projectId?: string, fileType?: string) => Promise<void>
  loadMoreArtifacts: (threadId?: string, projectId?: string, fileType?: string) => Promise<void>
  loadArtifactUrls: (fileIds: string[]) => Promise<void>
  getArtifactUrl: (fileId: string) => string | null
  downloadArtifact: (fileId: string) => Promise<void>
  clearArtifacts: () => void
  clearError: () => void
}

const PAGE_SIZE = 20 // Increased to get more artifacts per request

export const useArtifactStore = create<ArtifactStore>((set, get) => ({
  // Initial state
  artifacts: [],
  artifactUrls: {},
  isLoading: false,
  isLoadingUrls: false,
  error: null,
  hasMore: true,
  currentPage: 0,

  // Load initial artifacts with optional filters
  loadArtifacts: async (threadId?: string, projectId?: string, fileType?: string) => {
    console.log('[ArtifactStore] loadArtifacts START', { threadId, projectId, fileType })
    const startTime = performance.now()
    set({ isLoading: true, error: null, currentPage: 0, artifacts: [] })

    try {
      const { listArtifacts } = await import('@/services/api')
      console.log('[ArtifactStore] Calling listArtifacts API...')
      const apiStartTime = performance.now()
      const response = await listArtifacts(threadId, projectId, fileType, PAGE_SIZE)
      console.log(`[ArtifactStore] listArtifacts returned in ${(performance.now() - apiStartTime).toFixed(0)}ms, got ${response.artifacts.length} artifacts`)

      set({
        artifacts: response.artifacts,
        isLoading: false,
        error: null,
        hasMore: response.artifacts.length === PAGE_SIZE,
        currentPage: 1,
      })

      // Auto-load URLs for the artifacts
      if (response.artifacts.length > 0) {
        const fileIds = response.artifacts.map((a) => a.file_id)
        console.log(`[ArtifactStore] Calling loadArtifactUrls for ${fileIds.length} files...`)
        get().loadArtifactUrls(fileIds)
      }
      console.log(`[ArtifactStore] loadArtifacts COMPLETE in ${(performance.now() - startTime).toFixed(0)}ms`)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load artifacts'
      set({
        artifacts: [],
        isLoading: false,
        error: errorMessage,
        hasMore: false,
      })
      console.error('Failed to load artifacts:', err)
    }
  },

  // Load more artifacts for pagination
  loadMoreArtifacts: async (threadId?: string, projectId?: string, fileType?: string) => {
    const { isLoading, hasMore, currentPage, artifacts: currentArtifacts } = get()

    if (isLoading || !hasMore) return

    set({ isLoading: true, error: null })

    try {
      const { listArtifacts } = await import('@/services/api')
      const response = await listArtifacts(threadId, projectId, fileType, PAGE_SIZE, currentPage * PAGE_SIZE)

      set({
        artifacts: [...currentArtifacts, ...response.artifacts],
        isLoading: false,
        error: null,
        hasMore: response.artifacts.length === PAGE_SIZE,
        currentPage: currentPage + 1,
      })

      // Auto-load URLs for the new artifacts
      if (response.artifacts.length > 0) {
        const fileIds = response.artifacts.map((a) => a.file_id)
        get().loadArtifactUrls(fileIds)
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load more artifacts'
      set({
        isLoading: false,
        error: errorMessage,
      })
      console.error('Failed to load more artifacts:', err)
    }
  },

  // Load download URLs for multiple artifacts in batch (with caching)
  loadArtifactUrls: async (fileIds: string[]) => {
    console.log(`[ArtifactStore] loadArtifactUrls START for ${fileIds.length} files`)
    if (fileIds.length === 0) return

    // Filter out already cached URLs
    const uncachedIds: string[] = []
    const cachedUrls: Record<string, string> = {}

    for (const fileId of fileIds) {
      const cached = getCachedUrl(fileId)
      if (cached) {
        cachedUrls[fileId] = cached
      } else {
        uncachedIds.push(fileId)
      }
    }

    console.log(`[ArtifactStore] Cache check: ${Object.keys(cachedUrls).length} cached, ${uncachedIds.length} uncached`)

    // Update state with cached URLs immediately
    if (Object.keys(cachedUrls).length > 0) {
      set((state) => ({
        artifactUrls: { ...state.artifactUrls, ...cachedUrls },
      }))
    }

    // Fetch uncached URLs from backend
    if (uncachedIds.length === 0) {
      console.log('[ArtifactStore] All URLs cached, skipping API call')
      return
    }

    set({ isLoadingUrls: true })

    try {
      const { getBatchDownloadUrls } = await import('@/services/api')
      console.log(`[ArtifactStore] Calling getBatchDownloadUrls API for ${uncachedIds.length} files...`)
      const apiStartTime = performance.now()
      const response = await getBatchDownloadUrls(uncachedIds)
      console.log(`[ArtifactStore] getBatchDownloadUrls returned in ${(performance.now() - apiStartTime).toFixed(0)}ms`)

      const newUrls: Record<string, string> = {}
      for (const item of response.urls) {
        if (item.download_url) {
          newUrls[item.file_id] = item.download_url
          setCachedUrl(item.file_id, item.download_url)
        }
      }

      set((state) => ({
        artifactUrls: { ...state.artifactUrls, ...newUrls },
        isLoadingUrls: false,
      }))
    } catch (err) {
      console.error('Failed to load artifact URLs:', err)
      set({ isLoadingUrls: false })
    }
  },

  // Get artifact URL (from store state)
  getArtifactUrl: (fileId: string) => {
    return get().artifactUrls[fileId] || null
  },

  // Download artifact via presigned URL
  downloadArtifact: async (fileId: string) => {
    try {
      // Try to use cached URL first
      let downloadUrl: string | null = get().artifactUrls[fileId] || getCachedUrl(fileId)

      if (!downloadUrl) {
        // Fetch single URL if not cached
        const { getDownloadUrl } = await import('@/services/api')
        const response = await getDownloadUrl(fileId)
        downloadUrl = response.download_url
        setCachedUrl(fileId, downloadUrl)
        set((state) => ({
          artifactUrls: { ...state.artifactUrls, [fileId]: response.download_url },
        }))
      }

      // Trigger browser download
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = '' // Let browser determine filename from S3
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      console.log('Download initiated for file_id:', fileId)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to download artifact'
      set({ error: errorMessage })
      console.error('Failed to download artifact:', err)
      throw err // Re-throw for UI error handling
    }
  },

  // Clear artifacts
  clearArtifacts: () => {
    set({ artifacts: [], artifactUrls: {}, error: null })
  },

  // Clear error
  clearError: () => {
    set({ error: null })
  },
}))
