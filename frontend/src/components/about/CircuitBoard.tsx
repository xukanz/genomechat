import { Brain, Database, Code2, BookOpen } from "lucide-react"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import type { LandingCopy } from "../../config/landing/copy"
import { PATHS } from "./circuitPaths"
import { CircuitDefs } from "./CircuitDefs"

// ── Agent data ──────────────────────────────────────────────────────────────

type AgentKey = keyof LandingCopy["architecture"]["agents"]

interface Agent {
  key: AgentKey
  icon: React.ComponentType<{ className?: string }>
  iconBg: string
  iconColor: string
  /** CSS % position matching SVG path start (viewBox 280×220) */
  position: { left: string; top: string }
}

/**
 * The four nodes that wire into the orchestrator. The orchestrator itself is
 * the chip at the centre of the board, not a corner label — it used to appear
 * in both places, which left the researcher off a diagram the page describes
 * as having five agents.
 */
const AGENTS: Agent[] = [
  {
    key: "coordinator",
    icon: Brain,
    iconBg: "bg-violet-100",
    iconColor: "text-violet-600",
    position: { left: "12.5%", top: "22%" },
  },
  {
    key: "sqlAgent",
    icon: Database,
    iconBg: "bg-amber-100",
    iconColor: "text-amber-600",
    position: { left: "87.5%", top: "22%" },
  },
  {
    key: "researcher",
    icon: BookOpen,
    iconBg: "bg-emerald-100",
    iconColor: "text-emerald-600",
    position: { left: "12.5%", top: "78%" },
  },
  {
    key: "coder",
    icon: Code2,
    iconBg: "bg-sky-100",
    iconColor: "text-sky-600",
    position: { left: "87.5%", top: "78%" },
  },
]

// ── Sub-components ──────────────────────────────────────────────────────────

function AgentLabel({ agent, name, description }: { agent: Agent; name: string; description: string }) {
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
        {name}
      </span>
      <span className="text-[8px] md:text-[10px] text-slate-400 whitespace-nowrap">
        {description}
      </span>
    </div>
  )
}

export function CircuitBoard() {
  const copy = useLandingCopy()
  const agents = copy.architecture.agents
  const chipLabel = copy.architecture.flow.orchestrator
  // CJK glyphs are square and far wider than Latin at the same size, but the
  // label is also far shorter — bump the size so it still fills the 44-unit chip.
  const chipFontSize = /[一-龥]/.test(chipLabel) ? 7 : 5.5

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
            fontSize={chipFontSize}
            fill="url(#chip-text-grad)"
            fontWeight="600"
            letterSpacing="0.05em"
          >
            {chipLabel}
          </text>
        </g>

        <CircuitDefs />
      </svg>

      {/* Agent labels (HTML overlay aligned to SVG coords) */}
      {AGENTS.map((agent) => (
        <AgentLabel
          key={agent.key}
          agent={agent}
          name={agents[agent.key].title}
          description={agents[agent.key].description}
        />
      ))}
    </div>
  )
}
