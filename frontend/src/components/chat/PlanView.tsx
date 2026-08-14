import { CheckCircle2, Circle, Loader2, XCircle, ArrowRight, Zap, Code2, Database, Brain, Workflow } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { motion, AnimatePresence } from "framer-motion"
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

const agentIcons: Record<string, LucideIcon> = {
  coordinator: Brain,
  orchestrator: Workflow,
  coder: Code2,
  sql_agent: Database,
}

const agentColors: Record<string, string> = {
  coordinator: "text-purple-600 bg-purple-50 dark:bg-purple-950/20 border-purple-200 dark:border-purple-800",
  orchestrator: "text-green-600 bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800",
  coder: "text-blue-600 bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800",
  sql_agent: "text-yellow-600 bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800",
}

export interface PlanStep {
  title: string
  description: string
  status: "pending" | "in_progress" | "completed" | "failed"
  agent_name?: string
}

export interface Plan {
  title?: string
  thought?: string
  steps: PlanStep[]
}

interface PlanViewProps {
  plan: Plan
  isStreaming?: boolean
}

export function PlanView({ plan, isStreaming = false }: PlanViewProps) {
  // Find currently running agent(s)
  const runningSteps = plan.steps.filter(step => step.status === 'in_progress')
  
  return (
    <div className="my-4 rounded-lg border bg-gradient-to-br from-blue-50/50 to-indigo-50/50 dark:from-blue-950/20 dark:to-indigo-950/20 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center flex-shrink-0">
          <span className="text-lg">📋</span>
        </div>
        <h3 className="font-semibold text-sm text-foreground">Execution Plan</h3>
        {runningSteps.length > 0 ? (
          <div className="ml-auto flex items-center gap-2">
            {runningSteps.map((step, idx) => {
              const agentKey = step.agent_name?.toLowerCase() || ''
              const Icon = agentIcons[agentKey] || Zap
              const colorClass = agentColors[agentKey] || "text-gray-600 bg-gray-50 dark:bg-gray-950/20 border-gray-200 dark:border-gray-700"
              
              return (
                <div
                  key={`header-running-${idx}`}
                  className={cn(
                    "flex items-center gap-1.5 px-2 py-1 rounded-full border text-xs font-medium",
                    colorClass
                  )}
                >
                  <Icon className="h-3 w-3" />
                  <span>{formatAgentName(step.agent_name)} working...</span>
                  <Loader2 className="h-3 w-3 animate-spin" />
                </div>
              )
            })}
          </div>
        ) : isStreaming && (
          <div className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>Updating...</span>
          </div>
        )}
      </div>

      {plan.thought && (
        <p className="text-xs text-muted-foreground italic mb-3 pl-10">
          {plan.thought}
        </p>
      )}

      {/* Currently Running Agent(s) */}
      {runningSteps.length > 0 && (
        <div className="mb-3 pl-10">
          <div className="text-xs font-medium text-muted-foreground mb-2">
            Currently Running
          </div>
          <div className="flex flex-wrap gap-2">
            {runningSteps.map((step, idx) => {
              const agentKey = step.agent_name?.toLowerCase() || ''
              const Icon = agentIcons[agentKey] || Zap
              const colorClass = agentColors[agentKey] || "text-gray-600 bg-gray-50 dark:bg-gray-950/20 border-gray-200 dark:border-gray-700"
              
              return (
                <motion.div
                  key={`running-${idx}`}
                  initial={{ scale: 0.9, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium",
                    colorClass
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{formatAgentName(step.agent_name)}</span>
                  <div className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
                </motion.div>
              )
            })}
          </div>
        </div>
      )}
      
      {/* Task breakdown label */}
      {plan.steps && plan.steps.length > 0 && (
        <div className="text-xs text-muted-foreground italic mb-2 pl-10">
          Task breakdown
        </div>
      )}

      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {plan.steps.map((step, idx) => (
            <motion.div
              key={`${step.title}-${idx}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ delay: idx * 0.05 }}
              className={cn(
                "flex items-start gap-3 p-2.5 rounded-md transition-colors",
                step.status === "completed" && "bg-green-50/50 dark:bg-green-950/20",
                step.status === "in_progress" && "bg-blue-50/50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800",
                step.status === "failed" && "bg-red-50/50 dark:bg-red-950/20"
              )}
            >
              <div className="mt-0.5 flex-shrink-0">
                {step.status === "completed" && (
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                )}
                {step.status === "in_progress" && (
                  <Loader2 className="h-4 w-4 text-blue-600 dark:text-blue-400 animate-spin" />
                )}
                {step.status === "failed" && (
                  <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                )}
                {step.status === "pending" && (
                  <Circle className="h-4 w-4 text-gray-400 dark:text-gray-600" />
                )}
              </div>
              
              <div className="flex-1 min-w-0">
                <p className={cn(
                  "text-sm font-medium",
                  step.status === "completed" && "line-through text-muted-foreground",
                  step.status === "in_progress" && "text-blue-700 dark:text-blue-300",
                  step.status === "pending" && "text-foreground",
                  step.status === "failed" && "text-red-700 dark:text-red-400"
                )}>
                  {step.description || step.title}
                </p>
                {step.agent_name && (
                  <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                    <ArrowRight className="h-3 w-3" />
                    <span className="font-medium">{formatAgentName(step.agent_name)}</span>
                  </p>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
