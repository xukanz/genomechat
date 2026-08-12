import { motion } from "framer-motion"
import { Database } from "lucide-react"

const databases = [
  {
    name: "SQLite",
    description: "ClinVar variant archive",
    color: "#003B57",
    bgColor: "bg-sky-100"
  },
  {
    name: "DuckDB",
    description: "GWAS Parquet analytics",
    color: "#FFF000",
    bgColor: "bg-yellow-100",
    textDark: true
  },
  {
    name: "MySQL",
    description: "Enterprise SQL",
    color: "#4479A1",
    bgColor: "bg-cyan-100"
  },
  {
    name: "PostgreSQL",
    description: "Enterprise SQL",
    color: "#336791",
    bgColor: "bg-blue-100"
  },
  {
    name: "MSSQL",
    description: "Microsoft SQL Server",
    color: "#CC2927",
    bgColor: "bg-red-100"
  },
  {
    name: "Athena",
    description: "AWS serverless SQL",
    color: "#FF9900",
    bgColor: "bg-orange-100"
  }
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
  return (
    <motion.div
      className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4"
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
    >
      {databases.map((db) => (
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
            <Database className="w-6 h-6 text-white" />
          </motion.div>
          <span className="font-semibold text-slate-900 text-sm text-center">
            {db.name}
          </span>
          <span className="text-xs text-slate-500 text-center mt-1 hidden md:block">
            {db.description}
          </span>
        </motion.div>
      ))}
    </motion.div>
  )
}

export function DatabaseChips() {
  return (
    <motion.div
      className="flex flex-wrap justify-center gap-2"
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
    >
      {databases.map((db) => (
        <motion.div
          key={db.name}
          className="flex items-center gap-2 px-3 py-1.5 bg-white rounded-full border border-slate-200 shadow-sm"
          variants={itemVariants}
          whileHover={{ scale: 1.05, borderColor: db.color }}
        >
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: db.color }}
          />
          <span className="text-sm font-medium text-slate-700">{db.name}</span>
        </motion.div>
      ))}
    </motion.div>
  )
}

export function DatabaseCount() {
  return (
    <motion.div
      className="text-center"
      initial={{ opacity: 0, scale: 0.9 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
    >
      <motion.div
        className="text-6xl md:text-7xl font-bold text-blue-600 mb-2"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        {databases.length}
      </motion.div>
      <p className="text-slate-600 font-medium">Database Types Supported</p>
      <p className="text-sm text-slate-500 mt-1">
        Runtime switching without restart
      </p>
    </motion.div>
  )
}
