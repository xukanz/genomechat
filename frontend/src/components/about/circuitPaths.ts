/**
 * Circuit-board geometry, shared by the diagram and its <defs>.
 *
 * viewBox is 0 0 280 110. The orchestrator chip is the rect (118, 47, 44, 16),
 * centred at (140, 55), with pins symmetric about y=55 at y=50 and y=56. All
 * four traces use identical geometry — 62 horizontal, a 6-unit corner, then 22
 * vertical — so the animation timings are the only thing that distinguishes
 * them.
 *
 * These strings are duplicated as `offset-path` values in index.css
 * (.agent-line-1 … .agent-line-4). Change them together.
 */
export const PATHS = [
  "M 45 24 h 62 q 6 0 6 6 v 22",       // 1 Coordinator → left upper pin
  "M 235 24 h -62 q -6 0 -6 6 v 22",   // 2 SQL Agent   → right upper pin
  "M 45 86 h 62 q 6 0 6 -6 v -22",     // 3 Researcher  → left lower pin
  "M 235 86 h -62 q -6 0 -6 -6 v -22", // 4 Coder       → right lower pin
]

/** Glow gradient stop pairs, index-aligned with PATHS. */
export const GLOWS: [string, string][] = [
  ["#C4B5FD", "#8B5CF6"], // violet  – Coordinator
  ["#FDE68A", "#F59E0B"], // amber   – SQL Agent
  ["#6EE7B7", "#10B981"], // emerald – Researcher
  ["#7DD3FC", "#0EA5E9"], // sky     – Coder
]
