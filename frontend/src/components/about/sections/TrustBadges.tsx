import { motion } from "framer-motion"
import { Zap } from "lucide-react"
import { useLandingCopy } from "../../../hooks/useLandingCopy"

export function TrustBadges() {
  const copy = useLandingCopy()

  return (
    <motion.section
      className="max-w-7xl mx-auto px-6 pt-16"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
    >
      <div className="flex flex-wrap justify-center gap-3">
        <motion.div
          className="flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-700 rounded-full text-xs font-medium border border-emerald-200/60 tracking-wide"
          whileHover={{ scale: 1.02 }}
        >
          <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse motion-reduce:animate-none" />
          {copy.badges.k8s}
        </motion.div>
        <motion.div
          className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-700 rounded-full text-xs font-medium border border-blue-200/60 tracking-wide"
          whileHover={{ scale: 1.02 }}
        >
          <Zap className="w-3.5 h-3.5" />
          {copy.badges.sse}
        </motion.div>
      </div>
    </motion.section>
  )
}
