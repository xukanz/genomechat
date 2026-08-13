/**
 * SVG <defs> for the agent circuit board: the masks that clip each travelling
 * glow to its path, the radial gradients that colour them, and the chip's pin
 * gradient, drop shadow and sweeping label gradient.
 *
 * Split out of AgentWorkflowDiagram purely for file size — it is a hundred
 * lines of declarations with no logic, and inlining it pushed the diagram past
 * the project's component limit.
 */

import { PATHS, GLOWS } from "./circuitPaths"

export function CircuitDefs() {
  return (
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
  )
}
