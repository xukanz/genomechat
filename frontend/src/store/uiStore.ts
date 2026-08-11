import { create } from 'zustand'

type CodeLanguage = 'python' | 'r' | 'auto'

interface UIState {
  isSidebarOpen: boolean
  isDeepResearchEnabled: boolean
  codeLanguage: CodeLanguage
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  toggleDeepResearch: () => void
  setCodeLanguage: (language: CodeLanguage) => void
  cycleCodeLanguage: () => void
}

const CODE_LANGUAGE_CYCLE: CodeLanguage[] = ['python', 'r', 'auto']

export const useUIStore = create<UIState>((set) => ({
  isSidebarOpen: true,
  isDeepResearchEnabled: false,
  codeLanguage: 'python' as CodeLanguage,
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  setSidebarOpen: (open) => set({ isSidebarOpen: open }),
  toggleDeepResearch: () => set((state) => ({ isDeepResearchEnabled: !state.isDeepResearchEnabled })),
  setCodeLanguage: (language) => set({ codeLanguage: language }),
  cycleCodeLanguage: () => set((state) => {
    const currentIndex = CODE_LANGUAGE_CYCLE.indexOf(state.codeLanguage)
    const nextIndex = (currentIndex + 1) % CODE_LANGUAGE_CYCLE.length
    return { codeLanguage: CODE_LANGUAGE_CYCLE[nextIndex] }
  }),
}))
