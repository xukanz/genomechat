import { motion } from "framer-motion"
import { Shield, Lock, CheckCircle2, Server, FileCheck, Users } from "lucide-react"

const securityFeatures = [
  {
    icon: Shield,
    title: "JWT Authentication",
    description: "Secure token-based authentication with automatic refresh",
    color: "text-blue-600",
    bgColor: "bg-blue-100"
  },
  {
    icon: Lock,
    title: "Isolated Sandbox",
    description: "Code executes in resource-limited Docker containers",
    color: "text-green-600",
    bgColor: "bg-green-100"
  },
  {
    icon: CheckCircle2,
    title: "Schema Grounding",
    description: "Agents only see real database schemas - prevents hallucinations",
    color: "text-purple-600",
    bgColor: "bg-purple-100"
  },
  {
    icon: Server,
    title: "Kubernetes Ready",
    description: "Containerized deployment with auto-scaling and TLS",
    color: "text-orange-600",
    bgColor: "bg-orange-100"
  },
  {
    icon: FileCheck,
    title: "Validation Layers",
    description: "SQL queries validated before execution with auto-correction",
    color: "text-teal-600",
    bgColor: "bg-teal-100"
  },
  {
    icon: Users,
    title: "User Isolation",
    description: "MongoDB checkpoints isolate conversation state per user",
    color: "text-indigo-600",
    bgColor: "bg-indigo-100"
  }
]

const containerVariants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.1
    }
  }
}

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 }
}

export function SecurityFeatures() {
  return (
    <motion.div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
    >
      {securityFeatures.map((feature) => {
        const Icon = feature.icon
        return (
          <motion.div
            key={feature.title}
            className="relative p-6 rounded-xl bg-white border border-slate-200 shadow-sm overflow-hidden group"
            variants={itemVariants}
            whileHover={{ y: -4, boxShadow: "0 12px 24px -8px rgba(0,0,0,0.1)" }}
            transition={{ duration: 0.2 }}
          >
            {/* Background gradient on hover */}
            <motion.div
              className={`absolute inset-0 ${feature.bgColor} opacity-0 group-hover:opacity-30 transition-opacity`}
            />

            <div className="relative">
              <motion.div
                className={`w-12 h-12 rounded-lg ${feature.bgColor} flex items-center justify-center mb-4`}
                whileHover={{ rotate: [0, -10, 10, 0] }}
                transition={{ duration: 0.5 }}
              >
                <Icon className={`w-6 h-6 ${feature.color}`} />
              </motion.div>

              <h3 className="font-semibold text-slate-900 mb-2">
                {feature.title}
              </h3>
              <p className="text-sm text-slate-600">
                {feature.description}
              </p>
            </div>
          </motion.div>
        )
      })}
    </motion.div>
  )
}

export function SecurityBadges() {
  const badges = [
    { label: "JWT Auth", icon: Shield },
    { label: "Sandboxed", icon: Lock },
    { label: "Validated", icon: CheckCircle2 },
    { label: "Enterprise", icon: Server }
  ]

  return (
    <motion.div
      className="flex flex-wrap justify-center gap-3"
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
      variants={containerVariants}
    >
      {badges.map((badge) => {
        const Icon = badge.icon
        return (
          <motion.div
            key={badge.label}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-full text-sm font-medium"
            variants={itemVariants}
            whileHover={{ scale: 1.05 }}
          >
            <Icon className="w-4 h-4" />
            {badge.label}
          </motion.div>
        )
      })}
    </motion.div>
  )
}
