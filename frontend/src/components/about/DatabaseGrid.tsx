import { motion } from "framer-motion"
import { Database } from "lucide-react"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import type { LandingCopy } from "../../config/landing/copy"

/**
 * One entry per connection implementation in
 * backend/src/service/database/connections/. Keep this list in step with that
 * directory — the "7 database types" claim in the hero counts these.
 */
interface DatabaseEntry {
  key: keyof LandingCopy["databases"]["items"]
  name: string
  color: string
  bgColor: string
  /** Set where the brand colour is too light for a white glyph. */
  iconClass?: string
}

const DATABASES: DatabaseEntry[] = [
  { key: "sqlite", name: "SQLite", color: "#003B57", bgColor: "bg-sky-100" },
  { key: "duckdb", name: "DuckDB", color: "#FFF000", bgColor: "bg-yellow-100", iconClass: "text-slate-900" },
  { key: "mysql", name: "MySQL", color: "#4479A1", bgColor: "bg-cyan-100" },
  { key: "postgres", name: "PostgreSQL", color: "#336791", bgColor: "bg-blue-100" },
  { key: "mssql", name: "MSSQL", color: "#CC2927", bgColor: "bg-red-100" },
  { key: "athena", name: "Athena", color: "#FF9900", bgColor: "bg-orange-100" },
  { key: "mongodb", name: "MongoDB", color: "#47A248", bgColor: "bg-green-100" },
]

const containerVariants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.08
    }
  }
}

const itemVariants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: { opacity: 1, scale: 1 }
}

export function DatabaseGrid() {
  const copy = useLandingCopy()

  return (
    <motion.div
      className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4"
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
    >
      {DATABASES.map((db) => (
        <motion.div
          key={db.name}
          className={`flex flex-col items-center p-4 rounded-xl ${db.bgColor} border border-slate-200 group cursor-default`}
          variants={itemVariants}
          whileHover={{
            scale: 1.05,
            y: -4,
            boxShadow: "0 12px 24px -8px rgba(0,0,0,0.15)"
          }}
          transition={{ type: "spring", stiffness: 400 }}
        >
          <motion.div
            className="w-12 h-12 rounded-lg flex items-center justify-center mb-2"
            style={{ backgroundColor: db.color }}
            whileHover={{ rotate: 360 }}
            transition={{ duration: 0.5 }}
          >
            <Database className={`w-6 h-6 ${db.iconClass ?? "text-white"}`} />
          </motion.div>
          <span className="font-semibold text-slate-900 text-sm text-center">
            {db.name}
          </span>
          <span className="text-xs text-slate-500 text-center mt-1 hidden md:block">
            {copy.databases.items[db.key]}
          </span>
        </motion.div>
      ))}
    </motion.div>
  )
}
