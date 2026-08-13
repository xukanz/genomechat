import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { ExternalLink, Image as ImageIcon, Network } from "lucide-react"
import { Card, CardContent } from "../ui/card"
import { AgentWorkflowDiagram } from "./AgentWorkflowDiagram"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import { cn } from "../../lib/utils"
import schemaImage from "../../assets/genomechat_schema.png"

/**
 * Architecture card with two faces: the animated agent overview, and the full
 * system diagram behind a flip.
 *
 * The diagram is a 5.8 MB PNG, so it is not mounted until the visitor shows
 * intent — hovering or focusing the toggle is enough to start the download, so
 * the flip usually lands on a decoded image, but a visitor who never touches
 * the button never pays for it.
 */
export function ArchitectureFlipCard() {
  const copy = useLandingCopy()
  const reduceMotion = useReducedMotion()

  const [showSchema, setShowSchema] = useState(false)
  const [schemaRequested, setSchemaRequested] = useState(false)

  const frontRef = useRef<HTMLDivElement>(null)
  const backRef = useRef<HTMLDivElement>(null)
  const [height, setHeight] = useState<number>()

  // Both faces are absolutely positioned so neither contributes to layout —
  // the card's height is driven from whichever face is currently showing.
  useLayoutEffect(() => {
    const measure = () => {
      const face = showSchema ? backRef.current : frontRef.current
      if (face) setHeight(face.offsetHeight)
    }

    measure()

    const observer = new ResizeObserver(measure)
    if (frontRef.current) observer.observe(frontRef.current)
    if (backRef.current) observer.observe(backRef.current)
    window.addEventListener("resize", measure)

    return () => {
      observer.disconnect()
      window.removeEventListener("resize", measure)
    }
  }, [showSchema, schemaRequested])

  // Escape returns to the overview, matching the usual dismiss affordance.
  useEffect(() => {
    if (!showSchema) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setShowSchema(false)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [showSchema])

  const requestSchema = () => setSchemaRequested(true)

  const toggle = () => {
    requestSchema()
    setShowSchema((current) => !current)
  }

  const faceBase = "absolute inset-x-0 top-0 [backface-visibility:hidden]"

  return (
    <Card className="relative border-slate-200/80 shadow-lg shadow-slate-200/50 overflow-hidden rounded-2xl">
      <button
        type="button"
        onClick={toggle}
        onMouseEnter={requestSchema}
        onFocus={requestSchema}
        aria-pressed={showSchema}
        className={cn(
          "absolute top-4 right-4 z-20 inline-flex items-center gap-1.5 rounded-full",
          "border border-slate-200 bg-white/90 backdrop-blur px-3 py-1.5",
          "text-xs font-medium text-slate-600 shadow-sm transition-colors",
          "hover:text-slate-900 hover:border-slate-300",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        )}
      >
        {showSchema ? (
          <Network className="w-3.5 h-3.5" />
        ) : (
          <ImageIcon className="w-3.5 h-3.5" />
        )}
        {showSchema ? copy.architecture.flip.toOverview : copy.architecture.flip.toSchema}
      </button>

      <CardContent className="p-4 md:p-6">
        <div className="[perspective:2000px]">
          <motion.div
            className="relative"
            style={{ transformStyle: "preserve-3d" }}
            animate={{
              rotateY: reduceMotion ? 0 : showSchema ? 180 : 0,
              height,
            }}
            transition={{
              rotateY: { duration: 0.7, ease: [0.4, 0, 0.2, 1] },
              height: { duration: 0.5, ease: [0.4, 0, 0.2, 1] },
            }}
          >
            <div
              ref={frontRef}
              className={cn(faceBase, showSchema && "pointer-events-none")}
              // Without motion the faces cross-fade instead of turning, so the
              // hidden one has to be faded out explicitly.
              style={reduceMotion ? { opacity: showSchema ? 0 : 1 } : undefined}
              aria-hidden={showSchema}
            >
              <AgentWorkflowDiagram />
            </div>

            <div
              ref={backRef}
              className={cn(faceBase, !showSchema && "pointer-events-none")}
              style={{
                transform: reduceMotion ? undefined : "rotateY(180deg)",
                opacity: reduceMotion ? (showSchema ? 1 : 0) : undefined,
              }}
              aria-hidden={!showSchema}
            >
              {schemaRequested && (
                <figure className="m-0">
                  <img
                    src={schemaImage}
                    alt={copy.architecture.flip.schemaAlt}
                    className="w-full h-auto max-h-[72vh] object-contain rounded-lg"
                    decoding="async"
                  />
                  <figcaption className="mt-3 text-center">
                    <a
                      href={schemaImage}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-700 transition-colors"
                    >
                      {copy.architecture.flip.openFullSize}
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </figcaption>
                </figure>
              )}
            </div>
          </motion.div>
        </div>
      </CardContent>
    </Card>
  )
}
