import { motion } from "framer-motion"
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip, LabelList } from "recharts"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import { useLocaleStore } from "../../store/localeStore"
import { formatCount, formatExact } from "../../lib/formatCount"
import { DATA_SCALE } from "../../config/landing/facts"

/**
 * Per-table row counts, straight from the shipped schema descriptions.
 *
 * There used to be a companion pie chart of "query routing distribution"
 * here. Its percentages were invented — nothing in the platform measures
 * them — so it was removed rather than translated.
 */
export function DataScaleChart() {
  const copy = useLandingCopy()
  const locale = useLocaleStore((state) => state.locale)

  const data = DATA_SCALE.map((entry) => ({
    name: copy.dataScale.tables[entry.key],
    records: entry.rows,
    color: entry.color,
  }))

  return (
    <motion.div
      className="w-full"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
    >
      <h3 className="text-sm font-semibold text-slate-500 mb-6 text-center tracking-wide uppercase">
        {copy.dataScale.chartTitle}
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 64 }}>
          <XAxis type="number" hide domain={[0, "dataMax"]} />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 12, fill: "#64748B" }}
            width={150}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(148, 163, 184, 0.08)" }}
            formatter={(value: number) => [
              `${formatExact(value, locale)} ${copy.dataScale.rowsUnit}`,
              copy.dataScale.chartTitle,
            ]}
            contentStyle={{
              backgroundColor: "#1E293B",
              border: "none",
              borderRadius: "8px",
              color: "#fff",
            }}
          />
          <Bar
            dataKey="records"
            radius={[0, 4, 4, 0]}
            animationDuration={1500}
            animationBegin={300}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
            <LabelList
              dataKey="records"
              position="right"
              formatter={(value) =>
                typeof value === "number" ? formatCount(value, locale) : ""
              }
              style={{ fill: "#475569", fontSize: 12, fontWeight: 500 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </motion.div>
  )
}
