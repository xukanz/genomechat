import { motion } from "framer-motion"
import { Card, CardContent } from "../../ui/card"
import { SectionHeading } from "../SectionHeading"
import { AgentWorkflowDiagram } from "../AgentWorkflowDiagram"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { SECTION_IDS } from "./anchors"

export function ArchitectureSection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      id={SECTION_IDS.architecture}
      className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <SectionHeading
        eyebrow={copy.architecture.eyebrow}
        title={copy.architecture.title}
        subtitle={copy.architecture.subtitle}
      />

      <Card className="border-slate-200/80 shadow-lg shadow-slate-200/50 overflow-hidden rounded-2xl">
        <CardContent className="p-6 md:p-10">
          <AgentWorkflowDiagram />
        </CardContent>
      </Card>
    </motion.section>
  )
}
