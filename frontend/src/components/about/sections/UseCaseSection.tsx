import { motion } from "framer-motion"
import { SectionHeading } from "../SectionHeading"
import { UseCaseTabs } from "../UseCaseTabs"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { SECTION_IDS } from "./anchors"

export function UseCaseSection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      id={SECTION_IDS.useCases}
      className="bg-slate-50/70 py-24 border-y border-slate-100 scroll-mt-20"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <div className="max-w-7xl mx-auto px-6">
        <SectionHeading
          eyebrow={copy.useCases.eyebrow}
          title={copy.useCases.title}
          subtitle={copy.useCases.subtitle}
        />

        <UseCaseTabs />
      </div>
    </motion.section>
  )
}
