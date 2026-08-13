import { motion, useReducedMotion } from "framer-motion"
import { MessageSquare, Brain, Workflow } from "lucide-react"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import { CircuitBoard } from "./CircuitBoard"

// ── Main export ─────────────────────────────────────────────────────────────

export function AgentWorkflowDiagram() {
  const { flow } = useLandingCopy().architecture

  return (
    <div className="relative w-full">
      <CircuitBoard />

      {/* Flow indicator */}
      <motion.div
        className="flex items-center justify-center gap-2 mt-4 flex-nowrap"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
      >
        <FlowStep icon={MessageSquare} label={flow.query} />
        <FlowArrow />
        <FlowStep icon={Brain} label={flow.coordinator} />
        <FlowArrow delay={0.1} />
        <FlowStep icon={Workflow} label={flow.orchestrator} />
        <FlowArrow delay={0.2} />
        <FlowStep label={flow.workers} />
      </motion.div>
    </div>
  )
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function FlowStep({
  icon: Icon,
  label,
}: {
  icon?: React.ComponentType<{ className?: string }>
  label: string
}) {
  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 rounded-full
        border border-slate-200/80 whitespace-nowrap"
    >
      {Icon && <Icon className="w-3 h-3 text-slate-400 flex-shrink-0" />}
      <span className="text-[10px] md:text-xs font-medium text-slate-500">
        {label}
      </span>
    </div>
  )
}

function FlowArrow({ delay = 0 }: { delay?: number }) {
  // Tailwind's motion-reduce: variant only reaches CSS animations, so the
  // looping nudge has to be switched off in JS.
  const reduceMotion = useReducedMotion()

  return (
    <motion.span
      className="text-slate-300 text-xs flex-shrink-0"
      animate={reduceMotion ? undefined : { x: [0, 2, 0] }}
      transition={{ duration: 1.5, repeat: Infinity, delay }}
    >
      →
    </motion.span>
  )
}
