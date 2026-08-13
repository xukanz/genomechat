import { motion } from "framer-motion"
import { SectionHeading } from "../SectionHeading"
import { SecurityFeatures, SecurityBadges } from "../SecurityFeatures"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { SECTION_IDS } from "./anchors"

export function SecuritySection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      id={SECTION_IDS.security}
      className="max-w-7xl mx-auto px-6 py-24 scroll-mt-20"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <SectionHeading
        eyebrow={copy.security.eyebrow}
        title={copy.security.title}
        subtitle={copy.security.subtitle}
      />

      <SecurityFeatures />

      <div className="mt-10">
        <SecurityBadges />
      </div>
    </motion.section>
  )
}
