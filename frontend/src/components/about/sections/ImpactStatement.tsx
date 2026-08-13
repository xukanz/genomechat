import { motion } from "framer-motion"
import { useLandingCopy } from "../../../hooks/useLandingCopy"

export function ImpactStatement() {
  const copy = useLandingCopy()

  return (
    <motion.section
      className="max-w-5xl mx-auto px-6 py-24"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
    >
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-10 md:p-14 text-center">
        <div className="absolute inset-0 opacity-[0.04]">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
              backgroundSize: "32px 32px",
            }}
          />
        </div>

        <motion.div
          className="relative"
          initial={{ opacity: 0, scale: 0.95 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
        >
          <p className="text-blue-400/80 text-xs font-semibold tracking-[0.2em] uppercase mb-4">
            {copy.impact.eyebrow}
          </p>
          <h2 className="text-2xl md:text-3xl lg:text-4xl font-bold text-white mb-5 tracking-tight">
            {copy.impact.title}
          </h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto leading-relaxed">
            {copy.impact.body}
          </p>
        </motion.div>
      </div>
    </motion.section>
  )
}
