import { motion } from "framer-motion"
import { SectionHeading } from "../SectionHeading"
import { DatabaseGrid } from "../DatabaseGrid"
import { useLandingCopy } from "../../../hooks/useLandingCopy"

export function DatabaseSection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      className="max-w-7xl mx-auto px-6 py-24"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <SectionHeading
        eyebrow={copy.databases.eyebrow}
        title={copy.databases.title}
        subtitle={copy.databases.subtitle}
      />

      <DatabaseGrid />
    </motion.section>
  )
}
