import { useEffect, useRef, useState } from "react"
import { motion, useInView, useMotionValue, animate } from "framer-motion"

interface AnimatedCounterProps {
  value: number
  duration?: number
  suffix?: string
  prefix?: string
  decimals?: number
  className?: string
  /**
   * Abbreviate the running value. Injected rather than built in because the
   * landing page groups by 万 in Chinese and by K/M in English — see
   * lib/formatCount.ts.
   */
  format?: (value: number) => string
}

export function AnimatedCounter({
  value,
  duration = 2,
  suffix = "",
  prefix = "",
  decimals = 0,
  className = "",
  format
}: AnimatedCounterProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const isInView = useInView(ref, { once: true, margin: "-100px" })
  const count = useMotionValue(0)
  const [displayValue, setDisplayValue] = useState("0")

  useEffect(() => {
    if (isInView) {
      const controls = animate(count, value, {
        duration,
        ease: "easeOut",
        onUpdate: (latest) => {
          if (format) {
            setDisplayValue(format(Math.round(latest)))
          } else if (decimals > 0) {
            setDisplayValue(latest.toFixed(decimals))
          } else {
            setDisplayValue(Math.round(latest).toLocaleString())
          }
        }
      })
      return controls.stop
    }
  }, [isInView, value, duration, decimals, format, count])

  return (
    <motion.span
      ref={ref}
      className={className}
      initial={{ opacity: 0, y: 10 }}
      animate={isInView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.3 }}
    >
      {prefix}{displayValue}{suffix}
    </motion.span>
  )
}

interface StatCardProps {
  value: number
  label: string
  suffix?: string
  icon?: React.ReactNode
  color?: string
  format?: (value: number) => string
}

export function StatCard({ value, label, suffix = "", icon, color = "text-blue-600", format }: StatCardProps) {
  return (
    <motion.div
      className="text-center p-5"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.3 }}
    >
      {icon && (
        <div className={`mb-3 ${color}`}>
          {icon}
        </div>
      )}
      <div className={`text-3xl md:text-4xl font-bold ${color} mb-1 tracking-tight`}>
        <AnimatedCounter value={value} suffix={suffix} format={format} />
      </div>
      <div className="text-xs text-slate-500 font-medium tracking-wide uppercase">{label}</div>
    </motion.div>
  )
}
