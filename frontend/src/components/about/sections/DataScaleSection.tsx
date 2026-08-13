import { motion } from "framer-motion"
import { Card, CardContent } from "../../ui/card"
import { SectionHeading } from "../SectionHeading"
import { DataScaleChart } from "../MetricsDashboard"
import { useLandingCopy } from "../../../hooks/useLandingCopy"
import { SECTION_IDS } from "./anchors"

/**
 * Sits directly after the architecture section so the 11.7M figure quoted in
 * the hero can be checked against a per-table breakdown without leaving the
 * page.
 */
export function DataScaleSection() {
  const copy = useLandingCopy()

  return (
    <motion.section
      id={SECTION_IDS.data}
      className="bg-slate-50/70 py-24 border-y border-slate-100 scroll-mt-20"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      <div className="max-w-5xl mx-auto px-6">
        <SectionHeading
          eyebrow={copy.dataScale.eyebrow}
          title={copy.dataScale.title}
          subtitle={copy.dataScale.subtitle}
        />

        <Card className="border-slate-200/80 shadow-sm rounded-2xl bg-white">
          <CardContent className="p-6 md:p-8">
            <DataScaleChart />
          </CardContent>
        </Card>

        <p className="mt-6 text-center text-xs text-slate-400 leading-relaxed max-w-3xl mx-auto">
          {copy.dataScale.footnote}
        </p>
      </div>
    </motion.section>
  )
}
