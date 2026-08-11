import { create } from 'zustand'
import type { AgentBackend } from '../types/conversation'

type CodeLanguage = 'python' | 'r' | 'auto'

interface UIState {
  isSidebarOpen: boolean
  isDeepResearchEnabled: boolean
  codeLanguage: CodeLanguage
  /**
   * Phase 2, Workstream A — per-request coder backend override.
   * `null` = use the server's configured default (typically LangChain).
   * `'sdk'` = route the next coder turn through the Claude Agent SDK path.
   * Intentionally NOT persisted to MongoDB / localStorage — purely in-memory
   * for the session so a refresh resets to the default (keeps the toggle
   * from leaking into project/conversation settings where it doesn't belong).
   */
  coderBackendOverride: AgentBackend | null
  /**
   * Phase 2, Workstream B — per-request orchestrator backend override.
   * Same semantics as coderBackendOverride. When set to `'sdk'`, the next
   * chat turn routes the ENTIRE multi-worker plan through the Claude
   * Agent SDK's self-driving path instead of the LangGraph loop.
   */
  orchestratorBackendOverride: AgentBackend | null
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleDeepResearch: () => void
  setCodeLanguage: (language: CodeLanguage) => void
  cycleCodeLanguage: () => void
  setCoderBackendOverride: (backend: AgentBackend | null) => void
  toggleCoderBackendOverride: () => void
  setOrchestratorBackendOverride: (backend: AgentBackend | null) => void
  toggleOrchestratorBackendOverride: () => void
}

const CODE_LANGUAGE_CYCLE: CodeLanguage[] = ['python', 'r', 'auto']

export const useUIStore = create<UIState>((set) => ({
  isSidebarOpen: true,
  isDeepResearchEnabled: false,
  codeLanguage: 'python' as CodeLanguage,
  coderBackendOverride: null,
  orchestratorBackendOverride: null,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  setSidebarOpen: (open) => set({ isSidebarOpen: open }),
  toggleDeepResearch: () => set((state) => ({ isDeepResearchEnabled: !state.isDeepResearchEnabled })),
  setCodeLanguage: (language) => set({ codeLanguage: language }),
  cycleCodeLanguage: () => set((state) => {
    const currentIndex = CODE_LANGUAGE_CYCLE.indexOf(state.codeLanguage)
    const nextIndex = (currentIndex + 1) % CODE_LANGUAGE_CYCLE.length
    return { codeLanguage: CODE_LANGUAGE_CYCLE[nextIndex] }
  }),
  setCoderBackendOverride: (backend) => set({ coderBackendOverride: backend }),
  toggleCoderBackendOverride: () => set((state) => ({
    // Binary toggle: null → 'sdk' → null. No other states.
    coderBackendOverride: state.coderBackendOverride === 'sdk' ? null : 'sdk',
  })),
  setOrchestratorBackendOverride: (backend) => set({ orchestratorBackendOverride: backend }),
  toggleOrchestratorBackendOverride: () => set((state) => ({
    orchestratorBackendOverride: state.orchestratorBackendOverride === 'sdk' ? null : 'sdk',
  })),
}))

