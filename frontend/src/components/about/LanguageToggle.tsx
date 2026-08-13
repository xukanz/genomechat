import { useLocaleStore, type Locale } from "../../store/localeStore"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import { cn } from "../../lib/utils"

const OPTIONS: { value: Locale; label: string }[] = [
  { value: "zh", label: "中" },
  { value: "en", label: "EN" },
]

/**
 * Segmented 中 / EN switch for the landing nav. Each option is its own button
 * rather than a single toggle so the current language is announced, not just
 * the action that would change it.
 */
export function LanguageToggle({ className }: { className?: string }) {
  const locale = useLocaleStore((state) => state.locale)
  const setLocale = useLocaleStore((state) => state.setLocale)
  const copy = useLandingCopy()

  return (
    <div
      role="group"
      aria-label={copy.nav.language}
      className={cn(
        "inline-flex items-center rounded-full bg-slate-100 p-0.5",
        className
      )}
    >
      {OPTIONS.map((option) => {
        const isActive = locale === option.value
        return (
          <button
            key={option.value}
            type="button"
            lang={option.value}
            onClick={() => setLocale(option.value)}
            aria-pressed={isActive}
            className={cn(
              "rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1",
              isActive
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-900"
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
