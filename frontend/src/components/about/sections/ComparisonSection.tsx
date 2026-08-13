import { motion } from "framer-motion"
import { SectionHeading } from "../SectionHeading"
import { BeforeAfterComparison } from "../BeforeAfterComparison"
import { useLandingCopy } from "../../../hooks/useLandingCopy"

export function ComparisonSection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      className="max-w-7xl mx-auto px-6 py-24"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <SectionHeading
        eyebrow={copy.comparison.eyebrow}
        title={copy.comparison.title}
        subtitle={copy.comparison.subtitle}
      />

      <BeforeAfterComparison />
    </motion.section>
  )
}
