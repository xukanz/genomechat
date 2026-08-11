import { useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Dna, Microscope, Activity, Search, ArrowRight } from "lucide-react"

const useCases = [
  {
    id: "variants",
    title: "Variant Interpretation",
    icon: Dna,
    color: "blue",
    description: "Query 4.4M+ ClinVar variant-condition assertions",
    details: [
      "Filter variants by clinical significance and ACMG review status",
      "Break down pathogenic and likely-pathogenic calls per gene",
      "Quantify variant-of-uncertain-significance burden across gene panels",
      "Plot pathogenic variant density along each chromosome"
    ],
    example: "How many pathogenic and likely pathogenic variants are reported in BRCA1? Break them down by variant type"
  },
  {
    id: "gwas",
    title: "Trait Genetics",
    icon: Activity,
    color: "purple",
    description: "Explore 1.1M+ curated SNP-trait associations",
    details: [
      "Find genome-wide significant hits (p < 5e-8) for any trait",
      "Rank pleiotropic SNPs by number of distinct associated traits",
      "Relate effect size to risk allele frequency",
      "Join to study metadata for sample size and ancestry context"
    ],
    example: "Find genome-wide significant associations for type 2 diabetes. Show the strongest 25 with their mapped genes"
  },
  {
    id: "literature",
    title: "Literature Validation",
    icon: Search,
    color: "green",
    description: "Cross-reference findings with published research",
    details: [
      "Vector search across biomedical literature",
      "Retrieve papers by DOI for citation",
      "Validate computational findings against publications",
      "Generate summaries with source attribution"
    ],
    example: "Find recent papers on polygenic risk scores for coronary artery disease"
  },
  {
    id: "annotation",
    title: "Gene Annotation",
    icon: Microscope,
    color: "orange",
    description: "Query the Ensembl human core reference live",
    details: [
      "Resolve genes, transcripts, exons and translations by symbol or ID",
      "Look up genomic coordinates on GRCh38 via seq_region",
      "Map between HGNC, RefSeq and UniProt identifiers through xrefs",
      "Anchor ClinVar and GWAS results to reference gene models"
    ],
    example: "List all protein-coding transcripts of TP53 with their exon counts and genomic coordinates"
  }
]

const colorMap: Record<string, { bg: string; text: string; border: string; light: string }> = {
  blue: { bg: "bg-blue-600", text: "text-blue-600", border: "border-blue-200", light: "bg-blue-50" },
  purple: { bg: "bg-purple-600", text: "text-purple-600", border: "border-purple-200", light: "bg-purple-50" },
  green: { bg: "bg-green-600", text: "text-green-600", border: "border-green-200", light: "bg-green-50" },
  orange: { bg: "bg-orange-600", text: "text-orange-600", border: "border-orange-200", light: "bg-orange-50" }
}

export function UseCaseTabs() {
  const [activeTab, setActiveTab] = useState(0)
  const activeCase = useCases[activeTab]
  const colors = colorMap[activeCase.color]

  return (
    <div className="w-full">
      {/* Tab Navigation */}
      <div className="flex flex-wrap justify-center gap-2 mb-8">
        {useCases.map((useCase, index) => {
          const Icon = useCase.icon
          const isActive = activeTab === index
          const tabColors = colorMap[useCase.color]

          return (
            <motion.button
              key={useCase.id}
              onClick={() => setActiveTab(index)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                isActive
                  ? `${tabColors.bg} text-white`
                  : `${tabColors.light} ${tabColors.text} hover:opacity-80`
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{useCase.title}</span>
            </motion.button>
          )
        })}
      </div>

      {/* Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
          className={`rounded-xl border ${colors.border} ${colors.light} p-6 md:p-8`}
        >
          <div className="flex items-start gap-4 mb-6">
            <div className={`w-12 h-12 rounded-lg ${colors.bg} flex items-center justify-center flex-shrink-0`}>
              <activeCase.icon className="w-6 h-6 text-white" />
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
                key={index}
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
            <p className="text-xs text-slate-400 mb-2">Example Query</p>
            <p className="text-sm text-slate-100 font-mono">
              "{activeCase.example}"
            </p>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

export function UseCaseCards() {
  return (
    <motion.div
      className="grid grid-cols-1 md:grid-cols-2 gap-4"
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true }}
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.1 } }
      }}
    >
      {useCases.map((useCase) => {
        const Icon = useCase.icon
        const colors = colorMap[useCase.color]

        return (
          <motion.div
            key={useCase.id}
            className={`p-6 rounded-xl border ${colors.border} ${colors.light} group cursor-default`}
            variants={{
              hidden: { opacity: 0, y: 20 },
              visible: { opacity: 1, y: 0 }
            }}
            whileHover={{ y: -4 }}
          >
            <div className={`w-10 h-10 rounded-lg ${colors.bg} flex items-center justify-center mb-4`}>
              <Icon className="w-5 h-5 text-white" />
            </div>
            <h3 className="font-semibold text-slate-900 mb-2">
              {useCase.title}
            </h3>
            <p className="text-sm text-slate-600">
              {useCase.description}
            </p>
          </motion.div>
        )
      })}
    </motion.div>
  )
}
