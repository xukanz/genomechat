import { motion } from "framer-motion"
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Cell, Tooltip, PieChart, Pie } from "recharts"

const dataScale = [
  { name: "ClinVar", records: 4480843, color: "#0066CC" },
  { name: "GWAS associations", records: 1188619, color: "#22C55E" },
  { name: "GWAS studies", records: 229607, color: "#A855F7" }
]

const agentUsage = [
  { name: "SQL Agent", value: 45, color: "#EAB308" },
  { name: "Coder", value: 25, color: "#3B82F6" },
  { name: "Orchestrator", value: 20, color: "#6366F1" },
  { name: "Direct Response", value: 10, color: "#64748B" }
]

const formatNumber = (num: number) => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(0)}K`
  return num.toString()
}

export function DataScaleChart() {
  return (
    <motion.div
      className="w-full"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5 }}
    >
      <h3 className="text-lg font-semibold text-slate-900 mb-4 text-center">
        Data Scale
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={dataScale} layout="vertical" margin={{ left: 20, right: 40 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 12, fill: "#64748B" }}
            width={100}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(value: number) => [formatNumber(value) + " records", "Records"]}
            contentStyle={{
              backgroundColor: "#1E293B",
              border: "none",
              borderRadius: "8px",
              color: "#fff"
            }}
          />
          <Bar
            dataKey="records"
            radius={[0, 4, 4, 0]}
            animationDuration={1500}
            animationBegin={300}
          >
            {dataScale.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </motion.div>
  )
}

export function AgentUsageChart() {
  return (
    <motion.div
      className="w-full"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, delay: 0.2 }}
    >
      <h3 className="text-lg font-semibold text-slate-900 mb-4 text-center">
        Query Routing Distribution
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={agentUsage}
            cx="50%"
            cy="50%"
            innerRadius={40}
            outerRadius={70}
            paddingAngle={2}
            dataKey="value"
            animationDuration={1500}
            animationBegin={500}
          >
            {agentUsage.map((entry, index) => (
              <Cell key={index} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number) => [`${value}%`, "Usage"]}
            contentStyle={{
              backgroundColor: "#1E293B",
              border: "none",
              borderRadius: "8px",
              color: "#fff"
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap justify-center gap-3 mt-2">
        {agentUsage.map((entry) => (
          <div key={entry.name} className="flex items-center gap-1.5 text-xs">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: entry.color }}
            />
            <span className="text-slate-600">{entry.name}</span>
          </div>
        ))}
      </div>
    </motion.div>
  )
}

export function MetricsDashboard() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
      <DataScaleChart />
      <AgentUsageChart />
    </div>
  )
}
