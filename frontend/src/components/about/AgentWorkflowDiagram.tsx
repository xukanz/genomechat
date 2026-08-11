import { motion } from "framer-motion"
import {
  Brain,
  Workflow,
  Database,
  Code2,
  MessageSquare,
} from "lucide-react"

// ── Agent data ──────────────────────────────────────────────────────────────

interface Agent {
  name: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  iconBg: string
  iconColor: string
  /** CSS % position matching SVG path start (viewBox 280×220) */
  position: { left: string; top: string }
}

const AGENTS: Agent[] = [
  {
    name: "Coordinator",
    description: "Routes queries",
    icon: Brain,
    iconBg: "bg-violet-100",
    iconColor: "text-violet-600",
    position: { left: "12.5%", top: "22%" },
  },
  {
    name: "SQL Agent",
    description: "Queries data",
    icon: Database,
    iconBg: "bg-amber-100",
    iconColor: "text-amber-600",
    position: { left: "87.5%", top: "22%" },
  },
  {
    name: "Orchestrator",
    description: "Plans the work",
    icon: Workflow,
    iconBg: "bg-indigo-100",
    iconColor: "text-indigo-600",
    position: { left: "12.5%", top: "78%" },
  },
  {
    name: "Coder",
    description: "Runs code",
    icon: Code2,
    iconBg: "bg-sky-100",
    iconColor: "text-sky-600",
    position: { left: "87.5%", top: "78%" },
  },
]

// ── SVG circuit paths (viewBox 0 0 280 110) ─────────────────────────────────
// Chip rect: (118, 47, 44, 16) → center at (140, 55)
// Pins symmetric around y=55: upper y=50, lower y=56
// All 4 agents: identical geometry (62h + 6curve + 22v)

const PATHS = [
  "M 45 24 h 62 q 6 0 6 6 v 22",       // 1 Coordinator → left upper pin
  "M 235 24 h -62 q -6 0 -6 6 v 22",   // 2 SQL Agent  → right upper pin
  "M 45 86 h 62 q 6 0 6 -6 v -22",     // 3 Orchestrator → left lower pin
  "M 235 86 h -62 q -6 0 -6 -6 v -22", // 4 Coder     → right lower pin
]

// Glow gradient stop pairs per path
const GLOWS: [string, string][] = [
  ["#C4B5FD", "#8B5CF6"], // violet  – Coordinator
  ["#FDE68A", "#F59E0B"], // amber   – SQL Agent
  ["#A5B4FC", "#6366F1"], // indigo  – Orchestrator
  ["#7DD3FC", "#0EA5E9"], // sky     – Coder
]

// ── Sub-components ──────────────────────────────────────────────────────────

function AgentLabel({ agent }: { agent: Agent }) {
  const Icon = agent.icon
  return (
    <div
      className="absolute z-20 flex flex-col items-center pointer-events-none"
      style={{
        left: agent.position.left,
        top: agent.position.top,
        transform: "translate(-50%, -33%)",
      }}
    >
      <div
        className={`w-16 h-16 md:w-20 md:h-20 rounded-xl ${agent.iconBg}
          flex items-center justify-center shadow-md border border-white/80`}
      >
        <Icon className={`w-8 h-8 md:w-10 md:h-10 ${agent.iconColor}`} />
      </div>
      <span className="mt-1.5 text-[10px] md:text-xs font-semibold text-slate-700 whitespace-nowrap">
        {agent.name}
      </span>
      <span className="text-[8px] md:text-[10px] text-slate-400 whitespace-nowrap">
        {agent.description}
      </span>
    </div>
  )
}

function CircuitBoard() {
  return (
    <div className="relative w-full" style={{ aspectRatio: "28 / 11" }}>
      <svg viewBox="0 0 280 110" className="absolute inset-0 w-full h-full">
        {/* ── Circuit paths ── */}
        <g
          stroke="#cbd5e1"
          fill="none"
          strokeWidth="0.4"
          strokeDasharray="100 100"
          pathLength={100}
          markerStart="url(#agent-dot)"
        >
          {PATHS.map((d, i) => (
            <path
              key={i}
              d={d}
              strokeDasharray="100 100"
              pathLength={100}
            />
          ))}
          <animate
            attributeName="stroke-dashoffset"
            from="100"
            to="0"
            dur="1s"
            fill="freeze"
            calcMode="spline"
            keySplines="0.25,0.1,0.5,1"
            keyTimes="0; 1"
          />
        </g>

        {/* ── Glow dots traveling along paths ── */}
        {PATHS.map((_, i) => (
          <g key={`glow-${i}`} mask={`url(#amask-${i})`}>
            <circle
              className={`agent-circuit agent-line-${i + 1}`}
              cx="0"
              cy="0"
              r="8"
              fill={`url(#agrad-${i})`}
            />
          </g>
        ))}

        {/* ── Orchestrator chip ── */}
        <g>
          {/* Connection pins – left and right only */}
          <g fill="url(#chip-pin-grad)">
            {/* Left pins – symmetric around y=55 */}
            <rect x="113" y="50" width="5" height="3" rx="0.8" />
            <rect x="113" y="56" width="5" height="3" rx="0.8" />
            {/* Right pins – symmetric around y=55 */}
            <rect x="162" y="50" width="5" height="3" rx="0.8" />
            <rect x="162" y="56" width="5" height="3" rx="0.8" />
          </g>
          {/* Chip body */}
          <rect
            x="118"
            y="47"
            width="44"
            height="16"
            rx="2.5"
            fill="#181818"
            filter="url(#chip-shadow)"
          />
          {/* Chip label */}
          <text
            x="140"
            y="55"
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="5.5"
            fill="url(#chip-text-grad)"
            fontWeight="600"
            letterSpacing="0.05em"
          >
            Orchestrator
          </text>
        </g>

        {/* ── Defs ── */}
        <defs>
          {/* Masks – clip glow to path stroke */}
          {PATHS.map((d, i) => (
            <mask key={`mask-${i}`} id={`amask-${i}`}>
              <path d={d} strokeWidth="0.7" stroke="white" fill="none" />
            </mask>
          ))}

          {/* Radial glow gradients */}
          {GLOWS.map(([light, dark], i) => (
            <radialGradient key={`grad-${i}`} id={`agrad-${i}`} fx="1">
              <stop offset="0%" stopColor={light} />
              <stop offset="50%" stopColor={dark} />
              <stop offset="100%" stopColor="transparent" />
            </radialGradient>
          ))}

          {/* Pin gradient */}
          <linearGradient id="chip-pin-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4F4F4F" />
            <stop offset="60%" stopColor="#121214" />
          </linearGradient>

          {/* Chip drop-shadow */}
          <filter
            id="chip-shadow"
            x="-50%"
            y="-50%"
            width="200%"
            height="200%"
          >
            <feDropShadow
              dx="1.5"
              dy="1.5"
              stdDeviation="1.5"
              floodColor="black"
              floodOpacity="0.15"
            />
          </filter>

          {/* Text shimmer for chip label */}
          <linearGradient id="chip-text-grad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#666">
              <animate
                attributeName="offset"
                values="-2;-1;0"
                dur="5s"
                repeatCount="indefinite"
                calcMode="spline"
                keyTimes="0;0.5;1"
                keySplines="0.4 0 0.2 1;0.4 0 0.2 1"
              />
            </stop>
            <stop offset="25%" stopColor="white">
              <animate
                attributeName="offset"
                values="-1;0;1"
                dur="5s"
                repeatCount="indefinite"
                calcMode="spline"
                keyTimes="0;0.5;1"
                keySplines="0.4 0 0.2 1;0.4 0 0.2 1"
              />
            </stop>
            <stop offset="50%" stopColor="#666">
              <animate
                attributeName="offset"
                values="0;1;2"
                dur="5s"
                repeatCount="indefinite"
                calcMode="spline"
                keyTimes="0;0.5;1"
                keySplines="0.4 0 0.2 1;0.4 0 0.2 1"
              />
            </stop>
          </linearGradient>

          {/* Marker – small dark dot at path start */}
          <marker
            id="agent-dot"
            viewBox="0 0 10 10"
            refX="5"
            refY="5"
            markerWidth="14"
            markerHeight="14"
          >
            <circle
              cx="5"
              cy="5"
              r="2"
              fill="black"
              stroke="#232323"
              strokeWidth="0.5"
            >
              <animate attributeName="r" values="0;3;2" dur="0.5s" />
            </circle>
          </marker>
        </defs>
      </svg>

      {/* Agent labels (HTML overlay aligned to SVG coords) */}
      {AGENTS.map((agent) => (
        <AgentLabel key={agent.name} agent={agent} />
      ))}
    </div>
  )
}

// ── Main export ─────────────────────────────────────────────────────────────

export function AgentWorkflowDiagram() {
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
        <FlowStep icon={MessageSquare} label="Query" />
        <FlowArrow />
        <FlowStep icon={Brain} label="Coordinator" />
        <FlowArrow delay={0.1} />
        <FlowStep icon={Workflow} label="Orchestrator" />
        <FlowArrow delay={0.2} />
        <FlowStep label="Agents" />
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
  return (
    <motion.span
      className="text-slate-300 text-xs flex-shrink-0"
      animate={{ x: [0, 2, 0] }}
      transition={{ duration: 1.5, repeat: Infinity, delay }}
    >
      →
    </motion.span>
  )
}

// Keep for backwards compatibility
export function AgentWorkflowCompact() {
  return null
}
