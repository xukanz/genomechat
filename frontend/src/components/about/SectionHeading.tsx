import { motion } from "framer-motion"

interface SectionHeadingProps {
  eyebrow: string
  title: string
  subtitle: string
}

/**
 * The eyebrow / heading / subtitle block that opens every landing section.
 * Previously inlined seven times with identical motion props.
 */
export function SectionHeading({ eyebrow, title, subtitle }: SectionHeadingProps) {
  return (
    <div className="text-center mb-12">
      <motion.p
        className="section-label mb-3"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        {eyebrow}
      </motion.p>
      <motion.h2
        className="text-3xl md:text-4xl font-bold text-slate-900 mb-4 tracking-tight"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        {title}
      </motion.h2>
      <motion.p
        className="text-slate-500 max-w-2xl mx-auto leading-relaxed"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
        transition={{ delay: 0.1 }}
      >
        {subtitle}
      </motion.p>
    </div>
  )
}
