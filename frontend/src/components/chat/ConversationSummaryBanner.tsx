import { useState } from 'react'
import { ChevronDown, ChevronUp, FileText } from 'lucide-react'

interface ConversationSummaryBannerProps {
  summary: string
}

export function ConversationSummaryBanner({ summary }: ConversationSummaryBannerProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Strip markdown header prefix if present
  const cleanSummary = summary
    .replace(/^##\s*Previous conversation summary:\s*/i, '')
    .replace(/^\[Conversation Summary\]\s*/i, '')
    .trim()

  return (
    <div className="mx-4 my-3 rounded-lg border border-border/50 bg-muted/30">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-muted-foreground
                   hover:text-foreground transition-colors"
      >
        <FileText className="h-4 w-4 shrink-0" />
        <span className="font-medium">Earlier conversation summarized</span>
        <span className="ml-auto">
          {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </span>
      </button>
      {isExpanded && (
        <div className="px-4 pb-3 text-sm text-muted-foreground whitespace-pre-wrap">
          {cleanSummary}
        </div>
      )}
    </div>
  )
}
