import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Check, X, ArrowRight, Zap } from "lucide-react"
import { Button } from "../ui/button"
import { useLandingCopy } from "../../hooks/useLandingCopy"
import { BRANDING } from "../../config/branding"

export function BeforeAfterComparison() {
  const [showAfter, setShowAfter] = useState(false)
  const navigate = useNavigate()
  const copy = useLandingCopy()
  const comparisons = copy.comparison.rows

  return (
    <motion.div
      className="relative"
      initial={{ opacity: 0 }}
      whileInView={{ opacity: 1 }}
      viewport={{ once: true }}
    >
      {/* Toggle Button */}
      <div className="flex justify-center mb-8">
        <motion.div className="inline-flex rounded-full p-1 bg-slate-100" layout>
          <button
            onClick={() => setShowAfter(false)}
            aria-pressed={!showAfter}
            className={`px-6 py-2 rounded-full text-sm font-medium transition-colors ${
              !showAfter
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            {copy.comparison.traditionalTab}
          </button>
          <button
            onClick={() => setShowAfter(true)}
            aria-pressed={showAfter}
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
              {copy.comparison.cta}
              <ArrowRight className="w-4 h-4" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
