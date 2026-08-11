import { motion } from "framer-motion"
import { ArrowRight, Zap, ChevronDown } from "lucide-react"
import { Card, CardContent } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { useNavigate } from "react-router-dom"
import { StatCard } from "../components/about/AnimatedCounter"
import { AgentWorkflowDiagram } from "../components/about/AgentWorkflowDiagram"
import { BeforeAfterComparison } from "../components/about/BeforeAfterComparison"
import { SecurityFeatures, SecurityBadges } from "../components/about/SecurityFeatures"
import { DatabaseGrid } from "../components/about/DatabaseGrid"
import { UseCaseTabs } from "../components/about/UseCaseTabs"
import { SplineScene } from "../components/ui/spline-scene"
import { Spotlight } from "../components/ui/spotlight"
import { useAuthStore } from "../store/authStore"
import { BRANDING } from "../config/branding"
import logoMark from "../assets/logo.svg"

export function AboutPage() {
  const navigate = useNavigate()
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  const handleCTA = () => {
    navigate(isAuthenticated ? "/app" : "/login")
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-slate-100">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src={logoMark} alt={`${BRANDING.name} logo`} className="h-8 w-8 rounded-lg" />
            <span className="font-semibold text-slate-900 tracking-tight">{BRANDING.name}</span>
          </div>
          <Button onClick={handleCTA} className="bg-slate-900 hover:bg-slate-800 text-white rounded-full px-6 text-sm font-medium shadow-none">
            {isAuthenticated ? "Open App" : "Get Started"}
          </Button>
        </div>
      </nav>

      {/* Hero Section with 3D Robot - Full viewport height */}
      <section className="relative overflow-hidden min-h-[calc(100vh-65px)] flex flex-col">
        <Spotlight className="-top-40 left-0 md:left-60 md:-top-20" />
        <div className="absolute inset-0 hero-mesh" />
        <div className="absolute inset-0 bg-gradient-to-b from-slate-50/40 to-white" />

        <div className="max-w-7xl mx-auto px-6 py-12 relative flex-1 flex flex-col justify-center">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-8">
            {/* Left content */}
            <motion.div
              className="w-full md:w-1/2 text-center md:text-left z-10 flex-shrink-0"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6 }}
            >
              <motion.p
                className="section-label mb-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
              >
                AI-Powered Research Platform
              </motion.p>

              <motion.h1
                className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6 tracking-tight"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
              >
                <span className="text-slate-900">Meet</span>
                <br />
                <span className="text-shimmer">
                  {BRANDING.name}
                </span>
              </motion.h1>

              <motion.p
                className="text-lg text-slate-500 max-w-md mb-8 leading-relaxed"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
              >
                Every breakthrough starts with a question. {BRANDING.name} removes the wall between curiosity and discovery.
              </motion.p>

              <motion.div
                className="flex items-center gap-4"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 }}
              >
                <Button
                  size="lg"
                  onClick={handleCTA}
                  className="h-12 px-8 text-sm font-medium bg-blue-600 hover:bg-blue-500 rounded-full shadow-lg shadow-blue-600/20 transition-all hover:shadow-xl hover:shadow-blue-600/25"
                >
                  Try {BRANDING.name}
                  <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </motion.div>
            </motion.div>

            {/* Right content - 3D Robot (desktop only) */}
            <motion.div
              className="hidden md:flex md:w-1/2 h-[400px] relative items-center justify-center flex-shrink-0"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.3 }}
            >
              <SplineScene
                scene="https://prod.spline.design/kZDDjO5HuC9GJUM2/scene.splinecode"
                className="w-full h-full"
              />
            </motion.div>
          </div>

          {/* Key Stats */}
          <motion.div
            className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto mt-12"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
          >
            <StatCard value={6200000} label="Records" suffix="+" formatLarge />
            <StatCard value={5} label="AI Agents" />
            <StatCard value={7} label="Database Types" />
            <StatCard value={24000000} label="Scientific Articles" suffix="+" formatLarge />
          </motion.div>

          {/* Scroll indicator */}
          <motion.div
            className="absolute bottom-6 left-1/2 -translate-x-1/2"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, y: [0, 8, 0] }}
            transition={{ opacity: { delay: 1 }, y: { duration: 1.5, repeat: Infinity } }}
          >
            <ChevronDown className="w-6 h-6 text-slate-400" />
          </motion.div>
        </div>
      </section>

      {/* Production Badge */}
      <motion.section
        className="max-w-7xl mx-auto px-6 py-6"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <div className="flex flex-wrap justify-center gap-3">
          <motion.div
            className="flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-700 rounded-full text-xs font-medium border border-emerald-200/60 tracking-wide"
            whileHover={{ scale: 1.02 }}
          >
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            Container-Native, Kubernetes Ready
          </motion.div>
          <motion.div
            className="flex items-center gap-2 px-4 py-2 bg-blue-50 text-blue-700 rounded-full text-xs font-medium border border-blue-200/60 tracking-wide"
            whileHover={{ scale: 1.02 }}
          >
            <Zap className="w-3.5 h-3.5" />
            Real-time SSE Streaming
          </motion.div>
        </div>
      </motion.section>

      {/* Patient Impact Statement */}
      <motion.section
        className="max-w-5xl mx-auto px-6 py-16"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
      >
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-blue-950 to-slate-900 p-10 md:p-14 text-center">
          {/* Background pattern */}
          <div className="absolute inset-0 opacity-[0.04]">
            <div className="absolute inset-0" style={{
              backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
              backgroundSize: "32px 32px"
            }} />
          </div>

          <motion.div
            className="relative"
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
          >
            <p className="text-blue-400/80 text-xs font-semibold tracking-[0.2em] uppercase mb-4">
              Why This Matters
            </p>
            <h2 className="text-2xl md:text-3xl lg:text-4xl font-bold text-white mb-5 tracking-tight">
              Accelerating Genomics Discovery
            </h2>
            <p className="text-slate-400 text-lg max-w-2xl mx-auto leading-relaxed">
              Every minute saved in research is a step closer to better treatments for patients.
              {" "}{BRANDING.name} helps researchers go from question to discovery faster—turning days of analysis into minutes.
            </p>
          </motion.div>
        </div>
      </motion.section>

      {/* Multi-Agent Architecture */}
      <motion.section
        className="max-w-7xl mx-auto px-6 py-24"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <div className="text-center mb-12">
          <motion.p
            className="section-label mb-3"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
          >
            Architecture
          </motion.p>
          <motion.h2
            className="text-3xl md:text-4xl font-bold text-slate-900 mb-4 tracking-tight"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            Multi-Agent Architecture
          </motion.h2>
          <motion.p
            className="text-slate-500 max-w-2xl mx-auto leading-relaxed"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
          >
            Five specialized AI agents collaborate to handle complex research queries with intelligent task routing
          </motion.p>
        </div>

        <Card className="border-slate-200/80 shadow-lg shadow-slate-200/50 overflow-hidden rounded-2xl">
          <CardContent className="p-6 md:p-10">
            <AgentWorkflowDiagram />
          </CardContent>
        </Card>
      </motion.section>

      {/* Before/After Comparison */}
      <motion.section
        className="max-w-7xl mx-auto px-6 py-24"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <div className="text-center mb-12">
          <motion.p
            className="section-label mb-3"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
          >
            Impact
          </motion.p>
          <motion.h2
            className="text-3xl md:text-4xl font-bold text-slate-900 mb-4 tracking-tight"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            Transform Your Research Workflow
          </motion.h2>
          <motion.p
            className="text-slate-500 max-w-2xl mx-auto leading-relaxed"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
          >
            See how {BRANDING.name} transforms the way researchers explore data
          </motion.p>
        </div>

        <BeforeAfterComparison />
      </motion.section>

      {/* Database Support */}
      <motion.section
        className="bg-slate-50/70 py-24 border-y border-slate-100"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <motion.p
              className="section-label mb-3"
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
            >
              Data Infrastructure
            </motion.p>
            <motion.h2
              className="text-3xl md:text-4xl font-bold text-slate-900 mb-4 tracking-tight"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              Multi-Database Architecture
            </motion.h2>
            <motion.p
              className="text-slate-500 max-w-2xl mx-auto leading-relaxed"
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
            >
              Connect to 7 database types with runtime switching — no restart required
            </motion.p>
          </div>

          <DatabaseGrid />
        </div>
      </motion.section>

      {/* Research Use Cases */}
      <motion.section
        className="max-w-7xl mx-auto px-6 py-24"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <div className="text-center mb-12">
          <motion.p
            className="section-label mb-3"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
          >
            Use Cases
          </motion.p>
          <motion.h2
            className="text-3xl md:text-4xl font-bold text-slate-900 mb-4 tracking-tight"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            Research Use Cases
          </motion.h2>
          <motion.p
            className="text-slate-500 max-w-2xl mx-auto leading-relaxed"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
          >
            From exploratory research to clinical data analysis — all through natural language
          </motion.p>
        </div>

        <UseCaseTabs />
      </motion.section>

      {/* Security & Trust */}
      <motion.section
        className="bg-slate-50/70 py-24 border-y border-slate-100"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-12">
            <motion.p
              className="section-label mb-3"
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
            >
              Compliance & Security
            </motion.p>
            <motion.h2
              className="text-3xl md:text-4xl font-bold text-slate-900 mb-4 tracking-tight"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
            >
              Enterprise Security & Trust
            </motion.h2>
            <motion.p
              className="text-slate-500 max-w-2xl mx-auto leading-relaxed"
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
            >
              Built with enterprise-grade security and hallucination prevention
            </motion.p>
          </div>

          <SecurityFeatures />

          <div className="mt-10">
            <SecurityBadges />
          </div>
        </div>
      </motion.section>

      {/* CTA Footer */}
      <motion.section
        className="relative overflow-hidden bg-gradient-to-br from-slate-950 via-slate-900 to-blue-950 py-28"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        {/* Background pattern */}
        <div className="absolute inset-0 opacity-[0.03]">
          <div className="absolute inset-0" style={{
            backgroundImage: "radial-gradient(circle at 2px 2px, white 1px, transparent 0)",
            backgroundSize: "40px 40px"
          }} />
        </div>

        {/* Gradient orb */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-blue-600/10 rounded-full blur-3xl" />

        <div className="relative max-w-4xl mx-auto px-6 text-center">
          <motion.p
            className="text-blue-400/70 text-xs font-semibold tracking-[0.2em] uppercase mb-4"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
          >
            Get Started
          </motion.p>
          <motion.h2
            className="text-3xl md:text-4xl lg:text-5xl font-bold text-white mb-5 tracking-tight"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            Ready to Transform{" "}
            <br className="hidden md:block" />
            Genomics Research?
          </motion.h2>
          <motion.p
            className="text-slate-400 text-lg mb-10 max-w-2xl mx-auto leading-relaxed"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
          >
            Query 5.6M+ variant and association records, generate visualizations, and validate findings — all through natural conversation
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.2 }}
          >
            <Button
              size="lg"
              onClick={handleCTA}
              className="h-14 px-10 text-base font-medium bg-white text-slate-900 hover:bg-slate-100 rounded-full shadow-2xl shadow-white/10 transition-all hover:shadow-white/20"
            >
              Try {BRANDING.name}
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </motion.div>

          {/* Tech Stack */}
          <motion.div
            className="flex flex-wrap justify-center gap-3 mt-16"
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3 }}
          >
            {["React", "FastAPI", "LangGraph", "MongoDB", "DuckDB", "Docker"].map((tech) => (
              <span
                key={tech}
                className="px-3 py-1.5 bg-white/[0.06] text-white/50 rounded-full text-xs font-medium tracking-wide border border-white/[0.06]"
              >
                {tech}
              </span>
            ))}
          </motion.div>
        </div>
      </motion.section>

      {/* Footer */}
      <footer className="bg-slate-950 py-8 text-center border-t border-slate-800/50">
        <p className="text-xs text-slate-600 tracking-wide">
          &copy; {new Date().getFullYear()} {BRANDING.name}
        </p>
      </footer>
    </div>
  )
}
