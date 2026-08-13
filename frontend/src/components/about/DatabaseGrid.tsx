import { motion } from "framer-motion"
import { Database } from "lucide-react"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import type { LandingCopy } from "../../config/landing/copy"

interface DatabaseEntry {
  key: keyof LandingCopy["databases"]["items"]
  name: string
  color: string
  bgColor: string
  /** Set where the brand colour is too light for a white glyph. */
  iconClass?: string
}

/**
 * The two engines the shipped profiles actually run on. clinvar is SQLite;
 * gwas and ensembl are DuckDB over Parquet. See DATABASE_PROFILES in
 * backend/src/config/database_registry.py.
 */
const IN_USE: DatabaseEntry[] = [
  { key: "sqlite", name: "SQLite", color: "#003B57", bgColor: "bg-sky-100" },
  {
    key: "duckdb",
    name: "DuckDB",
    color: "#FFF000",
    bgColor: "bg-yellow-100",
    iconClass: "text-slate-900",
  },
]

/**
 * Connectors that exist in backend/src/service/database/connections/ and are
 * wired into DatabaseManager, but which no shipped profile selects. Shown
 * muted so the page doesn't imply the project runs on them.
 *
 * MongoDB is deliberately absent: it backs accounts, conversations,
 * checkpoints and traces, but it is not a DatabaseType and the SQL agent
 * never queries it.
 */
const AVAILABLE: DatabaseEntry[] = [
  { key: "postgres", name: "PostgreSQL", color: "#336791", bgColor: "bg-slate-100" },
  { key: "mysql", name: "MySQL", color: "#4479A1", bgColor: "bg-slate-100" },
  { key: "mssql", name: "MSSQL", color: "#CC2927", bgColor: "bg-slate-100" },
  { key: "athena", name: "Athena", color: "#FF9900", bgColor: "bg-slate-100" },
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

function GroupLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-slate-400 mb-4 text-center">
      {children}
    </p>
  )
}

function EngineCard({ db, muted }: { db: DatabaseEntry; muted?: boolean }) {
  const copy = useLandingCopy()

  return (
    <motion.div
      className={`flex flex-col items-center p-4 rounded-xl border group cursor-default ${db.bgColor} ${
        muted ? "border-slate-200/70" : "border-slate-200"
      }`}
      variants={itemVariants}
      whileHover={{
        scale: 1.05,
        y: -4,
        boxShadow: "0 12px 24px -8px rgba(0,0,0,0.15)"
      }}
      transition={{ type: "spring", stiffness: 400 }}
    >
      <motion.div
        className={`w-12 h-12 rounded-lg flex items-center justify-center mb-2 ${
          muted ? "opacity-45 saturate-50 group-hover:opacity-100 group-hover:saturate-100" : ""
        } transition-all`}
        style={{ backgroundColor: db.color }}
        whileHover={{ rotate: 360 }}
        transition={{ duration: 0.5 }}
      >
        <Database className={`w-6 h-6 ${db.iconClass ?? "text-white"}`} />
      </motion.div>
      <span
        className={`font-semibold text-sm text-center ${
          muted ? "text-slate-600" : "text-slate-900"
        }`}
      >
        {db.name}
      </span>
      <span className="text-xs text-slate-500 text-center mt-1 hidden md:block">
        {copy.databases.items[db.key]}
      </span>
    </motion.div>
  )
}

export function DatabaseGrid() {
  const copy = useLandingCopy()

  return (
    <div className="space-y-12">
      <div>
        <GroupLabel>{copy.databases.groups.inUse}</GroupLabel>
        <motion.div
          className="grid grid-cols-2 gap-4 max-w-md mx-auto"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
        >
          {IN_USE.map((db) => (
            <EngineCard key={db.key} db={db} />
          ))}
        </motion.div>
      </div>

      <div>
        <GroupLabel>{copy.databases.groups.available}</GroupLabel>
        <motion.div
          className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-3xl mx-auto"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
        >
          {AVAILABLE.map((db) => (
            <EngineCard key={db.key} db={db} muted />
          ))}
        </motion.div>
        <p className="text-xs text-slate-400 text-center mt-5">
          {copy.databases.groups.availableNote}
        </p>
      </div>
    </div>
  )
}
