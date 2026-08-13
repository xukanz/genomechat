import { motion } from "framer-motion"
import { ArrowRight } from "lucide-react"
import { Button } from "../../ui/button"
import { useLandingCopy } from "../../../hooks/useLandingCopy"

const TECH_STACK = ["React", "FastAPI", "LangGraph", "MongoDB", "DuckDB", "Docker"]

export function CtaSection({ onCTA }: { onCTA: () => void }) {
  const copy = useLandingCopy()

  return (
    <motion.section
      className="relative overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 py-28"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <div className="absolute inset-0 opacity-[0.03]">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
            backgroundSize: "40px 40px",
          }}
        />
      </div>

      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-3xl" />

      <div className="relative max-w-4xl mx-auto px-6 text-center">
        <motion.p
          className="text-blue-400/70 text-xs font-semibold tracking-[0.2em] uppercase mb-4"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
        >
          {copy.cta.eyebrow}
        </motion.p>
        <motion.h2
          className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-5 tracking-tight"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          {copy.cta.title}
        </motion.h2>
        <motion.p
          className="text-slate-400 text-lg mb-10 max-w-2xl mx-auto leading-relaxed"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
        >
          {copy.cta.subtitle}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 }}
        >
          <Button
            size="lg"
            onClick={onCTA}
            className="h-14 px-10 text-base font-medium bg-white text-slate-900 hover:bg-slate-100 rounded-full shadow-2xl shadow-white/10 transition-all hover:shadow-white/20"
          >
            {copy.cta.button}
            <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
        </motion.div>

        <motion.div
          className="flex flex-wrap justify-center gap-3 mt-16"
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 0.3 }}
        >
          {TECH_STACK.map((tech) => (
            <span
              key={tech}
              className="px-3 py-1.5 bg-white/[0.06] text-white/50 rounded-full text-xs font-medium tracking-wide border border-white/[0.06]"
            >
              {tech}
            </span>
          ))}
        </motion.div>
      </div>
    </motion.section>
  )
}
