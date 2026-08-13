import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Dna, Microscope, Activity, Search, ArrowRight } from "lucide-react"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import type { LandingCopy } from "../../config/landing/copy"

type UseCaseKey = keyof LandingCopy["useCases"]["items"]

/** Presentation only — the wording lives in the copy dictionary. */
const USE_CASES: { key: UseCaseKey; icon: typeof Dna; color: keyof typeof colorMap }[] = [
  { key: "variants", icon: Dna, color: "blue" },
  { key: "gwas", icon: Activity, color: "purple" },
  { key: "literature", icon: Search, color: "green" },
  { key: "annotation", icon: Microscope, color: "orange" },
]

const colorMap = {
  blue: { bg: "bg-blue-600", text: "text-blue-600", border: "border-blue-200", light: "bg-blue-50" },
  purple: { bg: "bg-purple-600", text: "text-purple-600", border: "border-purple-200", light: "bg-purple-50" },
  green: { bg: "bg-green-600", text: "text-green-600", border: "border-green-200", light: "bg-green-50" },
  orange: { bg: "bg-orange-600", text: "text-orange-600", border: "border-orange-200", light: "bg-orange-50" }
}

export function UseCaseTabs() {
  const [activeTab, setActiveTab] = useState(0)
  const copy = useLandingCopy()

  const active = USE_CASES[activeTab]
  const activeCase = copy.useCases.items[active.key]
  const colors = colorMap[active.color]
  const ActiveIcon = active.icon

  return (
    <div className="w-full">
      {/* Tab Navigation */}
      <div className="flex flex-wrap justify-center gap-2 mb-8">
        {USE_CASES.map((useCase, index) => {
          const Icon = useCase.icon
          const isActive = activeTab === index
          const tabColors = colorMap[useCase.color]

          return (
            <motion.button
              key={useCase.key}
              onClick={() => setActiveTab(index)}
              aria-pressed={isActive}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                isActive
                  ? `${tabColors.bg} text-white`
                  : `${tabColors.light} ${tabColors.text} hover:opacity-80`
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{copy.useCases.items[useCase.key].title}</span>
            </motion.button>
          )
        })}
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={active.key}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
          className={`rounded-xl border ${colors.border} ${colors.light} p-6 md:p-8`}
        >
          <div className="flex items-start gap-4 mb-6">
            <div className={`w-12 h-12 rounded-lg ${colors.bg} flex items-center justify-center flex-shrink-0`}>
              <ActiveIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-slate-900">
                {activeCase.title}
              </h3>
              <p className="text-slate-600 mt-1">
                {activeCase.description}
              </p>
            </div>
          </div>

          {/* Feature List */}
          <ul className="space-y-3 mb-6">
            {activeCase.details.map((detail, index) => (
              <motion.li
                key={detail}
                className="flex items-start gap-3"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.1 }}
              >
                <div className={`w-5 h-5 rounded-full ${colors.bg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                  <ArrowRight className="w-3 h-3 text-white" />
                </div>
                <span className="text-slate-700">{detail}</span>
              </motion.li>
            ))}
          </ul>

          {/* Example Query */}
          <div className="bg-slate-900 rounded-lg p-4">
            <p className="text-xs text-slate-400 mb-2">{copy.useCases.exampleLabel}</p>
            <p className="text-sm text-slate-100 font-mono">
              “{activeCase.example}”
            </p>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
