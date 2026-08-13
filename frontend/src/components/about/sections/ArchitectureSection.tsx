import { motion } from "framer-motion"
import { SectionHeading } from "../SectionHeading"
import { ArchitectureFlipCard } from "../ArchitectureFlipCard"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { SECTION_IDS } from "./anchors"

export function ArchitectureSection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      id={SECTION_IDS.architecture}
      className="max-w-5xl mx-auto px-6 py-24 scroll-mt-20"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <SectionHeading
        eyebrow={copy.architecture.eyebrow}
        title={copy.architecture.title}
        subtitle={copy.architecture.subtitle}
      />

      <ArchitectureFlipCard />
    </motion.section>
  )
}
