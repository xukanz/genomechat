import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { ChevronDown, Brain, Loader2, Code2, Database, Workflow } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { cn } from "../../lib/utils"

interface ThinkingProcessProps {
  content: string
  isStreaming?: boolean
}

const agentIcons: Record<string, LucideIcon> = {
  Coordinator: Brain,
  Orchestrator: Workflow,
  Coder: Code2,
  "SQL Agent": Database,
}

const agentColors: Record<string, string> = {
  Coordinator: "text-purple-500",
  Orchestrator: "text-green-500",
  Coder: "text-blue-500",
  "SQL Agent": "text-yellow-500",
}

function parseThinkingLine(line: string): { agent?: string; text: string; icon?: LucideIcon; color?: string } {
  // Check if line starts with "AgentName: "
  const match = line.match(/^([^:]+):\s*(.+)$/)
  if (match) {
    const agentName = match[1].trim()
    const text = match[2].trim()
    return {
      agent: agentName,
      text,
      icon: agentIcons[agentName],
      color: agentColors[agentName],
    }
  }
  return { text: line }
}

export function ThinkingProcess({ content, isStreaming = false }: ThinkingProcessProps) {
  const [isOpen, setIsOpen] = useState(true)

  // Split thinking content into steps and parse agent names
  const steps = content
    .split('\n')
    .filter(line => line.trim().length > 0)
    .map(parseThinkingLine)

  return (
    <div className="my-2 rounded-lg border bg-muted/30 overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors"
      >
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          {isStreaming ? (
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
          ) : (
            <Brain className="h-4 w-4 text-primary" />
          )}
          <span>{isStreaming ? "Reasoning..." : "Thought Process"}</span>
        </div>
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform duration-200",
            isOpen && "rotate-180"
          )}
        />
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div className="px-4 pb-4 pt-0 text-sm text-muted-foreground border-t border-border/50 bg-background/50">
                <div className="pt-3 space-y-3 font-mono text-xs relative">
                    {/* Timeline line */}
                    <div className="absolute left-[7px] top-3 bottom-0 w-px bg-border/40" />
                    
                    {steps.map((step, idx) => {
                      const Icon = step.icon
                      const isLast = idx === steps.length - 1
                      const hasIcon = !!Icon
                      
                      return (
                        <div key={idx} className="flex gap-3 items-start relative">
                          {/* Icon or dot */}
                          <div className="relative z-10 mt-0.5 min-w-[16px] flex items-center justify-center">
                            {hasIcon ? (
                              <div className="bg-background rounded-full p-0.5">
                                <Icon className={cn("h-3.5 w-3.5", step.color)} />
                              </div>
                            ) : isLast && isStreaming ? (
                              <div className="h-2 w-2 rounded-full bg-primary animate-pulse ring-2 ring-primary/20" />
                            ) : (
                              <div className="h-1.5 w-1.5 rounded-full bg-border" />
                            )}
                          </div>
                          
                          {/* Content */}
                          <div className="flex-1 pt-[1px]">
                            {step.agent && (
                              <span className={cn("font-semibold mr-2", step.color)}>
                                {step.agent}:
                              </span>
                            )}
                            <span className={cn(
                              isLast && isStreaming ? "text-primary" : "text-muted-foreground",
                              !hasIcon && "text-muted-foreground/80"
                            )}>
                              {step.text}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}


