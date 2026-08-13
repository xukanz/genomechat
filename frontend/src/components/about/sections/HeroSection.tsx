import { useCallback } from "react"
import { motion } from "framer-motion"
import { ArrowRight, ChevronDown } from "lucide-react"
import { Button } from "../../ui/button"
import { SplineScene } from "../../ui/spline-scene"
import { Spotlight } from "../../ui/spotlight"
import { StatCard } from "../AnimatedCounter"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { useLocaleStore } from "../../../store/localeStore"
import { formatCount } from "../../../lib/formatCount"
import { BRANDING } from "../../../config/branding"
import {
  AGENT_COUNT,
  DATABASE_TYPE_COUNT,
  DATA_SOURCE_COUNT,
  TOTAL_ROWS,
} from "../../../config/landing/facts"

const SPLINE_SCENE = "https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"

export function HeroSection({ onCTA }: { onCTA: () => void }) {
  const copy = useLandingCopy()
  const locale = useLocaleStore((state) => state.locale)

  // Identity is stable per locale, so the counter animation isn't restarted on
  // every parent render.
  const abbreviate = useCallback((value: number) => formatCount(value, locale), [locale])

  return (
    <section
      id="top"
      className="relative overflow-hidden min-h-[calc(100vh-65px)] flex flex-col"
    >
      <Spotlight className="-top-40 left-0 md:left-60 md:-top-20" />
      <div className="absolute inset-0 hero-mesh" />
      <div className="absolute inset-0 bg-gradient-to-b from-slate-50/40 to-white" />

      <div className="max-w-7xl mx-auto px-6 py-12 relative flex-1 flex flex-col justify-center">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-8">
          <motion.div
            className="w-full md:w-1/2 text-center md:text-left z-10 flex-shrink-0"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6 }}
          >
            <motion.p
              className="section-label mb-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
            >
              {copy.hero.eyebrow}
            </motion.p>

            <motion.h1
              className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6 tracking-tight"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              <span className="text-slate-900">{copy.hero.titleLead}</span>
              <br />
              <span className="text-shimmer">{BRANDING.name}</span>
            </motion.h1>

            <motion.p
              className="text-lg text-slate-500 max-w-md mb-8 leading-relaxed mx-auto md:mx-0"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
            >
              {copy.hero.subtitle}
            </motion.p>

            <motion.div
              className="flex items-center justify-center md:justify-start gap-4"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 }}
            >
              <Button
                size="lg"
                onClick={onCTA}
                className="h-12 px-8 text-sm font-medium bg-blue-600 hover:bg-blue-500 rounded-full shadow-lg shadow-blue-600/20 transition-all hover:shadow-xl hover:shadow-blue-600/25"
              >
                {copy.hero.cta}
                <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </motion.div>
          </motion.div>

          <motion.div
            className="hidden md:flex md:w-1/2 h-[400px] relative items-center justify-center flex-shrink-0"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 0.3 }}
          >
            {/* Placeholder behind the scene so the column isn't blank while the
                Spline runtime downloads. */}
            <div className="absolute inset-8 rounded-3xl bg-slate-100/40 animate-pulse motion-reduce:animate-none" />
            <SplineScene scene={SPLINE_SCENE} className="w-full h-full relative" />
          </motion.div>
        </div>

        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto mt-12"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
        >
          <StatCard value={TOTAL_ROWS} label={copy.hero.stats.records} format={abbreviate} />
          <StatCard value={AGENT_COUNT} label={copy.hero.stats.agents} />
          <StatCard value={DATABASE_TYPE_COUNT} label={copy.hero.stats.databases} />
          <StatCard value={DATA_SOURCE_COUNT} label={copy.hero.stats.sources} />
        </motion.div>

        <motion.div
          className="absolute bottom-6 left-1/2 -translate-x-1/2 motion-reduce:hidden"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, y: [0, 8, 0] }}
          transition={{ opacity: { delay: 1 }, y: { duration: 1.5, repeat: Infinity } }}
        >
          <ChevronDown className="w-6 h-6 text-slate-400" />
        </motion.div>
      </div>
    </section>
  )
}
