import { motion } from "framer-motion"
import { Code2, Database, Brain, Workflow, CheckCircle2, Loader2, Sparkles } from "lucide-react"
import { cn } from "../../lib/utils"
import type { AgentActivity } from "../../types/conversation"

interface AgentActivityPanelProps {
  activities: AgentActivity[]
}

const agentIcons: Record<string, any> = {
  Coordinator: Brain,
  Orchestrator: Workflow,
  Coder: Code2,
  "SQL Agent": Database,
}

const agentColors: Record<string, string> = {
  Coordinator: "text-purple-600 bg-purple-100 dark:bg-purple-950/30 border-purple-200 dark:border-purple-800",
  Orchestrator: "text-green-600 bg-green-100 dark:bg-green-950/30 border-green-200 dark:border-green-800",
  Coder: "text-blue-600 bg-blue-100 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800",
  "SQL Agent": "text-yellow-600 bg-yellow-100 dark:bg-yellow-950/30 border-yellow-200 dark:border-yellow-800",
}

export function AgentActivityPanel({ activities }: AgentActivityPanelProps) {
  if (activities.length === 0) return null

  return (
    <div className="my-3 flex items-center gap-2 flex-wrap">
      {activities.map((activity, idx) => {
        const Icon = agentIcons[activity.agent] || Brain
        const colorClass = agentColors[activity.agent] || "text-gray-600 bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700"
        const isSdk = activity.backend === "sdk"

        return (
          <motion.div
            key={`${activity.agent}-${idx}`}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: idx * 0.1 }}
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-medium",
              colorClass
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{activity.agent}</span>
            {isSdk && (
              <span
                title="Ran through Claude Agent SDK (Phase 1 feature-flag)"
                className="flex items-center gap-1 rounded-full border border-current/30 bg-white/40 dark:bg-black/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
              >
                <Sparkles className="h-2.5 w-2.5" />
                SDK
              </span>
            )}
            {activity.status === "thinking" && (
              <div className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
            )}
            {activity.status === "working" && (
              <Loader2 className="h-3 w-3 animate-spin" />
            )}
            {activity.status === "completed" && (
              <CheckCircle2 className="h-3 w-3" />
            )}
            {activity.status === "failed" && (
              <span className="text-xs">✗</span>
            )}
          </motion.div>
        )
      })}
    </div>
  )
}
