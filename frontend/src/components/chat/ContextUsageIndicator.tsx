import { useConversationStore } from '../../store/conversationStore'

export function ContextUsageIndicator() {
  const contextUsage = useConversationStore((s) => s.contextUsage)

  if (!contextUsage) return null

  const { usage_pct } = contextUsage
  const size = 18
  const strokeWidth = 2.5
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const filled = (usage_pct / 100) * circumference

  // Color thresholds
  const color = usage_pct >= 80 ? '#ef4444' : usage_pct >= 50 ? '#eab308' : '#22c55e'
  const pulse = usage_pct >= 80

  return (
    <div className="relative group" title={`${usage_pct}% context used`}>
      <svg width={size} height={size} className={pulse ? 'animate-pulse' : ''}>
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          className="text-muted-foreground/20"
        />
        {/* Filled arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={circumference - filled}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {/* Tooltip */}
      <div
        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block
                    bg-popover text-popover-foreground text-xs rounded-md px-2 py-1 shadow-md
                    whitespace-nowrap z-50"
      >
        {usage_pct}% context used
        {usage_pct >= 80 && (
          <div className="text-destructive">Consider starting a new conversation</div>
        )}
      </div>
    </div>
  )
}
