import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Check, X, ArrowRight, Zap } from "lucide-react"
import { Button } from "../ui/button"
import { BRANDING } from "../../config/branding"

const comparisons = [
  {
    traditional: "Days of manual SQL queries",
    platform: "Minutes with natural language"
  },
  {
    traditional: "SQL/Python expertise required",
    platform: "No coding needed"
  },
  {
    traditional: "Static reports and exports",
    platform: "Real-time streaming responses"
  },
  {
    traditional: "Single database at a time",
    platform: "3 genomics sources, runtime switching"
  },
  {
    traditional: "Manual literature validation",
    platform: "Built-in cross-validation"
  },
  {
    traditional: "Local notebooks, no persistence",
    platform: "Containerized deployment, persistent state"
  }
]

export function BeforeAfterComparison() {
  const [showAfter, setShowAfter] = useState(false)
  const navigate = useNavigate()

  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      {/* Toggle Button */}
      <div className="flex justify-center mb-8">
        <motion.div
          className="inline-flex rounded-full p-1 bg-slate-100"
          layout
        >
          <button
            onClick={() => setShowAfter(false)}
            className={`px-6 py-2 rounded-full text-sm font-medium transition-colors ${
              !showAfter
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            Traditional Approach
          </button>
          <button
            onClick={() => setShowAfter(true)}
            className={`px-6 py-2 rounded-full text-sm font-medium transition-colors ${
              showAfter
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {BRANDING.name}
          </button>
        </motion.div>
      </div>

      {/* Comparison Grid */}
      <div className="grid gap-3 max-w-2xl mx-auto">
        <AnimatePresence mode="wait">
          {comparisons.map((item, index) => (
            <motion.div
              key={showAfter ? `after-${index}` : `before-${index}`}
              initial={{ opacity: 0, x: showAfter ? 20 : -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: showAfter ? -20 : 20 }}
              transition={{ delay: index * 0.05, duration: 0.3 }}
              className={`flex items-center gap-3 p-4 rounded-lg border ${
                showAfter
                  ? "bg-green-50 border-green-200"
                  : "bg-red-50 border-red-200"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                  showAfter ? "bg-green-100" : "bg-red-100"
                }`}
              >
                {showAfter ? (
                  <Check className="w-5 h-5 text-green-600" />
                ) : (
                  <X className="w-5 h-5 text-red-500" />
                )}
              </div>
              <span
                className={`font-medium ${
                  showAfter ? "text-green-900" : "text-red-900"
                }`}
              >
                {showAfter ? item.platform : item.traditional}
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* CTA when showing the platform column */}
      <AnimatePresence>
        {showAfter && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="flex justify-center mt-8"
          >
            <Button
              className="gap-2 bg-blue-600 hover:bg-blue-700"
              onClick={() => navigate("/app")}
            >
              <Zap className="w-4 h-4" />
              Experience the Difference
              <ArrowRight className="w-4 h-4" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

export function ComparisonTable() {
  return (
    <motion.div
      className="overflow-hidden rounded-xl border border-slate-200 shadow-sm"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
    >
      <table className="w-full">
        <thead>
          <tr className="bg-slate-50">
            <th className="px-6 py-4 text-left text-sm font-semibold text-slate-900">
              Traditional Approach
            </th>
            <th className="px-6 py-4 text-left text-sm font-semibold text-blue-600">
              With {BRANDING.name}
            </th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((item, index) => (
            <motion.tr
              key={index}
              className="border-t border-slate-100"
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ delay: index * 0.1 }}
            >
              <td className="px-6 py-4">
                <div className="flex items-center gap-2">
                  <X className="w-4 h-4 text-red-500 flex-shrink-0" />
                  <span className="text-slate-600 text-sm">{item.traditional}</span>
                </div>
              </td>
              <td className="px-6 py-4 bg-blue-50/50">
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-green-600 flex-shrink-0" />
                  <span className="text-slate-900 text-sm font-medium">{item.platform}</span>
                </div>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </motion.div>
  )
}
