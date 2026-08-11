import { useRef, useEffect, useState, useMemo, useCallback } from "react"
import { useChat } from "../../hooks/useChat"
import { useConversationStore } from "../../store/conversationStore"
import { useAuthStore } from "../../store/authStore"
import { useDatabaseStore } from "../../store/databaseStore"
import { MessageBubble } from "./MessageBubble"
import { MessageInput } from "./MessageInput"
import { ConversationSummaryBanner } from "./ConversationSummaryBanner"
import { ExampleQuestions } from "./ExampleQuestions"
import { Loader2, CheckCircle2, Circle, XCircle, ClipboardList, ChevronDown, ChevronUp, Database } from "lucide-react"
import type { Plan } from "./PlanView"
import { cn } from "../../lib/utils"

// Helper to format agent names with proper capitalization
const formatAgentName = (agentName?: string) => {
  if (!agentName) return ''
  const formatted = agentName.replace('_', ' ')
  // Special case for SQL
  if (formatted.toLowerCase() === 'sql agent') return 'SQL Agent'
  // Capitalize first letter of each word
  return formatted.split(' ').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
}

const statusIconMap = {
  completed: CheckCircle2,
  in_progress: Loader2,
  failed: XCircle,
  pending: Circle,
} as const

/** Claude Code-style pulsing dots indicator for active streaming */
function StreamingDots({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-[3px]", className)}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse-dot"
          style={{ animationDelay: `${i * 0.2}s` }}
        />
      ))}
    </span>
  )
}

function ExecutionPlanNote({ plan, isStreaming }: { plan: Plan; isStreaming: boolean }) {
  const [isOpen, setIsOpen] = useState(true)
  const steps = plan.steps ?? []

  // Find currently running agent
  const runningStep = plan.steps?.find(step => step.status === 'in_progress')
  const runningAgentName = formatAgentName(runningStep?.agent_name)

  // Compute progress counts
  const completedCount = steps.filter(s => s.status === 'completed').length
  const totalCount = steps.length
  const allStepsDone = totalCount > 0 && completedCount === totalCount

  // Determine status label
  const getStatusLabel = () => {
    if (!isStreaming) return null // not streaming, no label needed
    if (runningAgentName) return `${runningAgentName} working...`
    if (allStepsDone) return 'Finalizing response...'
    return 'Updating'
  }
  const statusLabel = getStatusLabel()

  return (
    <div className={cn(
      "rounded-2xl border bg-slate-50/90 shadow-sm dark:bg-slate-900/70",
      isStreaming
        ? "border-primary/30 dark:border-primary/20"
        : "border-slate-200/80 dark:border-slate-800"
    )}>
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex w-full items-center justify-between px-4 py-3 text-sm"
      >
        <div className="flex items-center gap-2 font-semibold text-primary">
          <ClipboardList className="h-4 w-4" />
          <span>Execution Plan</span>
        </div>
        <div className="flex items-center gap-3">
          {isStreaming ? (
            <div className="text-xs text-muted-foreground flex items-center gap-2 whitespace-nowrap">
              <StreamingDots />
              <span className="font-medium">{statusLabel}</span>
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">Live agent roadmap</span>
          )}
          {isOpen ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>
      {isOpen && (
        <div className="px-4 pb-4 pt-3 space-y-2 max-h-64 overflow-y-auto">
          {steps.map((step, idx) => {
          const Icon = statusIconMap[step.status as keyof typeof statusIconMap] || Circle
          const iconClasses =
            step.status === "completed"
              ? "text-green-600"
              : step.status === "in_progress"
                ? "text-blue-600"
                : step.status === "failed"
                  ? "text-red-500"
                  : "text-muted-foreground"

          return (
            <div key={`${step.title}-${idx}`} className="flex items-start gap-3">
              <Icon className={`h-4 w-4 mt-1 ${step.status === "in_progress" ? "animate-spin" : ""} ${iconClasses}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium leading-snug text-foreground">
                  {step.description || step.title}
                </p>
              </div>
            </div>
          )
          })}
        </div>
      )}
    </div>
  )
}

export function Chat() {
  const { messages, isLoading, isStreaming, error, sendMessage, clearError, currentPlan } = useChat()
  const { currentConversationId, conversations } = useConversationStore()
  const { user } = useAuthStore()
  const { getActiveDatabase, loadDatabases } = useDatabaseStore()
  const activeDatabase = getActiveDatabase()
  const scrollRef = useRef<HTMLDivElement>(null)

  // Load databases on mount to ensure connection indicator works
  useEffect(() => {
    loadDatabases()
  }, [loadDatabases])

  // Determine if we're in empty state (no messages, not loading a conversation)
  const isEmpty = !isLoading && messages.length === 0 && !error

  // Determine if current conversation is read-only (shared with user, not owned)
  const isReadOnly = useMemo(() => {
    if (!currentConversationId || !user) return false
    const conversation = conversations.find(c => c.id === currentConversationId)
    if (!conversation) return false
    // If the current user doesn't own the conversation, it's read-only
    return conversation.user_id !== user.id
  }, [currentConversationId, conversations, user])

  const handleSendMessage = useCallback(async (content: string) => {
    await sendMessage(content)
  }, [sendMessage])

  // State for populating message input from example question
  const [selectedQuestion, setSelectedQuestion] = useState<string | undefined>(undefined)

  // Handle example question selection
  const handleExampleSelect = useCallback((text: string) => {
    setSelectedQuestion(text)
    // Clear after a tick to allow re-selection of same question
    setTimeout(() => setSelectedQuestion(undefined), 100)
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages, isStreaming])

  return (
    <div className={cn(
      "flex flex-col min-h-full max-w-4xl mx-auto w-full",
      isEmpty ? "justify-center items-center px-4" : "px-4 sm:px-5 py-4 gap-4"
    )}>
      {/* Messages section - only shown when not empty */}
      {!isEmpty && (
        <div className="flex-1 pt-2 pb-1 space-y-5">
          {isLoading && messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
              <Loader2 className="h-8 w-8 animate-spin mb-2" />
              <p>Loading conversation...</p>
            </div>
          )}

          {error && (
            <div className="mx-auto max-w-md p-4 rounded-lg bg-red-50 border border-red-200">
              <p className="text-sm text-red-600">{error}</p>
              <button
                onClick={clearError}
                className="text-xs text-red-500 hover:text-red-700 mt-2"
              >
                Dismiss
              </button>
            </div>
          )}

          {messages.map((msg) =>
            msg.isSummary ? (
              <ConversationSummaryBanner key={msg.id} summary={msg.content} />
            ) : (
              <MessageBubble key={msg.id} message={msg} />
            )
          )}

          <div ref={scrollRef} />
        </div>
      )}

      {/* Input section - centered when empty, sticky bottom when has messages */}
      <div className={cn(
        "relative space-y-3 transition-all duration-500 ease-out",
        isEmpty
          ? "w-full max-w-2xl mx-auto py-4"
          : "py-2 bg-[#F8FAFC]/85 backdrop-blur supports-[backdrop-filter]:bg-[#F8FAFC]/70 sticky bottom-0 z-10"
      )}>
        {/* Welcome header - only in empty state */}
        {isEmpty && (
          <div className="space-y-1 mb-6">
            <p className="text-lg text-muted-foreground">
              Hi {user?.name?.split(' ')[0] || 'there'}
            </p>
            <h2 className="text-3xl font-semibold text-slate-700">
              How can I help?
            </h2>
            <p className="text-muted-foreground text-sm pt-1">
              Ask questions about immunology research, analyze data, or explore scientific literature.
            </p>
            {/* Database Connection Indicator */}
            {activeDatabase && (
              <div className="flex items-center gap-1.5 pt-3">
                <Database className="h-3.5 w-3.5 text-green-600" />
                <span className="text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full border border-green-200">
                  Connected to {activeDatabase.display_name}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Gradient overlay - only when has messages */}
        {!isEmpty && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-2 left-0 right-0 h-4 bg-gradient-to-b from-transparent via-[#F8FAFC]/35 to-[#F8FAFC]/85"
          />
        )}

        {currentPlan && (
          <ExecutionPlanNote plan={currentPlan} isStreaming={isStreaming} />
        )}

        <MessageInput
          onSendMessage={handleSendMessage}
          isLoading={isLoading && !isStreaming}
          disabled={isReadOnly}
          disabledMessage="This is a shared conversation. You can view but not send messages."
          initialMessage={selectedQuestion}
        />

        {/* Example questions - only in empty state */}
        {isEmpty && activeDatabase?.example_questions && (
          <ExampleQuestions
            questions={activeDatabase.example_questions}
            onSelect={handleExampleSelect}
          />
        )}
      </div>
    </div>
  )
}

