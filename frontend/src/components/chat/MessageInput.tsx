import * as React from "react"
import { ArrowUp, Plug } from "lucide-react"
import { Button } from "../ui/button"
import { Textarea } from "../ui/textarea"
import { Switch } from "../ui/switch"
import { useUIStore } from "../../store/uiStore"
import { useDatabaseStore } from "../../store/databaseStore"
import { BackendSettingsMenu } from "./BackendSettingsMenu"
import { ContextUsageIndicator } from "./ContextUsageIndicator"
import { BRANDING } from "../../config/branding"

const MAX_TEXTAREA_HEIGHT = 220
const COMPOSER_HORIZONTAL_PADDING = "px-3"

interface MessageInputProps {
  onSendMessage: (message: string) => void
  isLoading?: boolean
  disabled?: boolean
  disabledMessage?: string
  initialMessage?: string // When set, populates the input (e.g., from example question click)
}

export function MessageInput({ onSendMessage, isLoading, disabled, disabledMessage, initialMessage }: MessageInputProps) {
  const [message, setMessage] = React.useState("")
  const {
    isDeepResearchEnabled,
    toggleDeepResearch,
    codeLanguage,
    cycleCodeLanguage,
  } = useUIStore()
  const { getActiveDatabase, loadDatabases } = useDatabaseStore()
  const activeDatabase = getActiveDatabase()
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)

  // Load databases on mount to ensure connection indicator works
  React.useEffect(() => {
    loadDatabases()
  }, [loadDatabases])

  // Update message when initialMessage changes (from example question click)
  React.useEffect(() => {
    if (initialMessage !== undefined && initialMessage !== "") {
      setMessage(initialMessage)
      // Focus the textarea after populating
      textareaRef.current?.focus()
    }
  }, [initialMessage])

  // Keep the composer compact while still expanding for longer prompts.
  // All hooks must be called before any conditional returns (Rules of Hooks)
  const adjustTextareaHeight = React.useCallback(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    textarea.style.height = "auto"
    const nextHeight = Math.min(textarea.scrollHeight, MAX_TEXTAREA_HEIGHT)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > MAX_TEXTAREA_HEIGHT ? "auto" : "hidden"
  }, [])

  React.useLayoutEffect(() => {
    if (!disabled) {
      adjustTextareaHeight()
    }
  }, [adjustTextareaHeight, message, disabled])

  const resetTextareaHeight = React.useCallback(() => {
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(adjustTextareaHeight)
    } else {
      adjustTextareaHeight()
    }
  }, [adjustTextareaHeight])

  const handleKeyDown = React.useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (message.trim()) {
        onSendMessage(message)
        setMessage("")
        resetTextareaHeight()
      }
    }
  }, [message, onSendMessage, resetTextareaHeight])

  const handleSend = React.useCallback(() => {
    if (message.trim()) {
      onSendMessage(message)
      setMessage("")
      resetTextareaHeight()
    }
  }, [message, onSendMessage, resetTextareaHeight])

  // Show read-only notice when disabled (after all hooks)
  if (disabled) {
    return (
      <div className="relative mx-auto w-full">
        <div className="relative flex items-center justify-center rounded-[1.7rem] border border-slate-200 bg-slate-100/50 px-4 py-3 text-slate-500">
          <p className="text-sm">{disabledMessage || "This conversation is read-only"}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative mx-auto w-full">
      <div
        className={`relative flex flex-col gap-0 rounded-[1.7rem] border bg-slate-200/95 ${COMPOSER_HORIZONTAL_PADDING} py-1 text-slate-900 shadow-sm transition-all duration-200 ${
          isDeepResearchEnabled
            ? "border-[#0C3B78] focus-within:ring-1 focus-within:ring-[#0C3B78]/50"
            : "border-slate-300 focus-within:ring-1 focus-within:ring-slate-400/50"
        }`}
      >
        <div className="relative flex items-center pt-1 pb-0.5">
            <Textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask me anything..."
              className="min-h-[12px] max-h-[220px] w-full resize-none border-0 bg-transparent pl-3 pr-2 py-1 text-[15px] leading-tight text-slate-900 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 focus-visible:ring-transparent focus-visible:outline-none focus:outline-none outline-none placeholder:text-slate-500/70"
            />
        </div>

      <div className="flex items-center justify-between pl-3 pr-2 pt-0.5 pb-1">
        <div className="flex items-center gap-1">
          <div className={`flex h-[22px] items-center gap-1 rounded-full border px-2 py-0.5 shadow-inner ${
            isDeepResearchEnabled ? "border-[#0C3B78]/30 bg-[#0C274C]/10" : "border-slate-200 bg-slate-100/80"
          }`}>
            <span className={`text-[12px] font-medium leading-none ${isDeepResearchEnabled ? "text-[#0C3B78]" : "text-slate-600"}`}>
              Deep Research
            </span>
                    <Switch
                        checked={isDeepResearchEnabled}
                        onCheckedChange={toggleDeepResearch}
              className="scale-[0.55] bg-slate-300/70 data-[state=checked]:bg-[#0C3B78]"
                    />
                </div>
          {/* Code Language Toggle */}
          <button
            onClick={cycleCodeLanguage}
            className={`flex h-[22px] items-center gap-1 rounded-full border px-2 py-0.5 shadow-inner transition-colors ${
              codeLanguage === 'r'
                ? "border-blue-300 bg-blue-50"
                : codeLanguage === 'auto'
                ? "border-purple-300 bg-purple-50"
                : "border-slate-200 bg-slate-100/80"
            }`}
            title={`Code language: ${codeLanguage.toUpperCase()}. Click to cycle.`}
          >
            <span className={`text-[12px] font-medium leading-none ${
              codeLanguage === 'r'
                ? "text-blue-700"
                : codeLanguage === 'auto'
                ? "text-purple-700"
                : "text-slate-600"
            }`}>
              {codeLanguage === 'python' ? 'Python' : codeLanguage === 'r' ? 'R' : 'Auto'}
            </span>
          </button>
          {/* Phase 2 worker-backend overrides — Coder + Orchestrator under a
              single gear menu to keep the composer compact. The gear turns
              amber whenever either override is active, so the state stays
              visible without opening the menu. */}
          <BackendSettingsMenu />
          {/* Database Connection Indicator */}
          <div className={`flex h-[22px] items-center gap-1 rounded-full border px-2 py-0.5 shadow-inner ${
            activeDatabase
              ? "border-green-200 bg-green-50"
              : "border-slate-200 bg-slate-100/80"
          }`}>
            <Plug className={`h-3 w-3 ${activeDatabase ? "text-green-600" : "text-slate-400"}`} />
            {activeDatabase && (
              <span className="text-[12px] font-medium leading-none text-green-700">
                {activeDatabase.display_name}
              </span>
            )}
          </div>
          {/* Context Usage Indicator */}
          <ContextUsageIndicator />
            </div>

            <div className="flex items-center pr-0.5">
                <Button
                    onClick={handleSend}
                    disabled={!message.trim() || isLoading}
            className={`h-8 w-8 rounded-full border transition-all duration-200 shadow-sm ${
              message.trim()
                ? "!bg-slate-400/90 !text-white border-slate-300 hover:!bg-slate-400"
                : "!bg-white/70 !text-slate-400 border-white/60 cursor-not-allowed"
            }`}
                    size="icon"
                >
                    <ArrowUp className="h-4 w-4" />
                </Button>
            </div>
        </div>
      </div>
      <div className="text-center mt-3">
        <p className="text-[11px] text-muted-foreground/40 font-medium">
            {BRANDING.name} may display inaccurate info, so please double check the response.
        </p>
      </div>
    </div>
  )
}
