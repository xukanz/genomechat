import { motion } from "framer-motion"
import { Shield, Lock, CheckCircle2, Server, FileCheck, Users } from "lucide-react"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import type { LandingCopy } from "../../config/landing/copy"

type FeatureKey = keyof LandingCopy["security"]["items"]

const FEATURES: { key: FeatureKey; icon: typeof Shield; color: string; bgColor: string }[] = [
  { key: "auth", icon: Shield, color: "text-blue-600", bgColor: "bg-blue-100" },
  { key: "sandbox", icon: Lock, color: "text-green-600", bgColor: "bg-green-100" },
  { key: "grounding", icon: CheckCircle2, color: "text-purple-600", bgColor: "bg-purple-100" },
  { key: "kubernetes", icon: Server, color: "text-orange-600", bgColor: "bg-orange-100" },
  { key: "validation", icon: FileCheck, color: "text-teal-600", bgColor: "bg-teal-100" },
  { key: "isolation", icon: Users, color: "text-indigo-600", bgColor: "bg-indigo-100" },
]

const BADGES: { key: keyof LandingCopy["security"]["badges"]; icon: typeof Shield }[] = [
  { key: "auth", icon: Shield },
  { key: "sandboxed", icon: Lock },
  { key: "validated", icon: CheckCircle2 },
  { key: "deployable", icon: Server },
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
  const copy = useLandingCopy()

  return (
    <motion.div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
      variants={containerVariants}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
    >
      {FEATURES.map((feature) => {
        const Icon = feature.icon
        const text = copy.security.items[feature.key]
        return (
          <motion.div
            key={feature.key}
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

              <h3 className="font-semibold text-slate-900 mb-2">{text.title}</h3>
              <p className="text-sm text-slate-600">{text.description}</p>
            </div>
          </motion.div>
        )
      })}
    </motion.div>
  )
}

export function SecurityBadges() {
  const copy = useLandingCopy()

  return (
    <motion.div
      className="flex flex-wrap justify-center gap-3"
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
      variants={containerVariants}
    >
      {BADGES.map((badge) => {
        const Icon = badge.icon
        return (
          <motion.div
            key={badge.key}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-full text-sm font-medium"
            variants={itemVariants}
            whileHover={{ scale: 1.05 }}
          >
            <Icon className="w-4 h-4" />
            {copy.security.badges[badge.key]}
          </motion.div>
        )
      })}
    </motion.div>
  )
}
