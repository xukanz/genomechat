import { create } from 'zustand'

export type Locale = 'zh' | 'en'

const STORAGE_KEY = 'genomechat.locale'

interface LocaleState {
  locale: Locale
  setLocale: (locale: Locale) => void
  toggleLocale: () => void
}

/**
 * Resolve the initial locale: an explicit past choice wins, otherwise fall
 * back to the browser's preference. English is the default; a browser that
 * asks for Chinese still gets it.
 */
function initialLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'zh' || stored === 'en') return stored
  } catch {
    // Private browsing or a blocked storage partition — fall through to the
    // navigator hint rather than failing to render.
  }
  return navigator.language?.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

function persist(locale: Locale) {
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    // Non-fatal: the choice just won't survive a reload.
  }
}

export const useLocaleStore = create<LocaleState>((set) => ({
  locale: initialLocale(),
  setLocale: (locale) => {
    persist(locale)
    set({ locale })
  },
  toggleLocale: () =>
    set((state) => {
      const next: Locale = state.locale === 'zh' ? 'en' : 'zh'
      persist(next)
      return { locale: next }
    }),
}))
