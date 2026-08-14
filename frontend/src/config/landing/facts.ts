/**
 * Verifiable numbers used on the landing page.
 *
 * Every value here is traceable to a schema description shipped with the
 * backend, so a claim on the marketing page can be checked against the data
 * the agents actually query. Keeping them out of the copy dictionary means the
 * Chinese and English versions can never drift apart on a number, and a
 * database rebuild is a one-file update.
 *
 * Sources (backend/databases/<profile>/schema_description.yaml):
 *   clinvar  — variant_summary  ~4.48 million rows
 *   gwas     — associations     ~1.19 million rows
 *              studies          ~229,600 rows
 *   ensembl  — genes            78,941 rows (20,131 protein-coding)
 *              transcripts      646,577 rows (19,299 MANE Select)
 *              exons            5,087,789 occurrences / 1,322,941 distinct
 */

export const CLINVAR_ROWS = 4_480_843
export const GWAS_ASSOCIATION_ROWS = 1_188_619
export const GWAS_STUDY_ROWS = 229_607
export const ENSEMBL_GENE_ROWS = 78_941
export const ENSEMBL_TRANSCRIPT_ROWS = 646_577
export const ENSEMBL_EXON_ROWS = 5_087_789

/** Graph nodes: coordinator, orchestrator, coder, SQL agent, researcher. */
export const AGENT_COUNT = 5

/**
 * LangChain tools defined in backend/src/tools/ — every function carrying the
 * @tool decorator, across database, file, code-execution, literature,
 * planning and SQL-pipeline modules. Not all of them go to every agent.
 */
export const AGENT_TOOL_COUNT = 16

/** Public genomics resources shipped as profiles: ClinVar, GWAS Catalog, Ensembl. */
export const DATA_SOURCE_COUNT = 3

/**
 * Per-table breakdown driving the data-scale chart.
 *
 * Must cover every table counted in TOTAL_ROWS — the section exists so a
 * visitor can add the bars up and land on the figure quoted in the hero.
 */
export interface DataScaleEntry {
  /** Key into LandingCopy.dataScale.tables for the display label. */
  key:
    | 'clinvar'
    | 'gwasAssociations'
    | 'gwasStudies'
    | 'ensemblGenes'
    | 'ensemblExons'
    | 'ensemblTranscripts'
  rows: number
  color: string
}

export const DATA_SCALE: DataScaleEntry[] = [
  { key: 'clinvar', rows: CLINVAR_ROWS, color: '#0066CC' },
  { key: 'ensemblExons', rows: ENSEMBL_EXON_ROWS, color: '#F97316' },
  { key: 'gwasAssociations', rows: GWAS_ASSOCIATION_ROWS, color: '#22C55E' },
  { key: 'ensemblTranscripts', rows: ENSEMBL_TRANSCRIPT_ROWS, color: '#14B8A6' },
  { key: 'gwasStudies', rows: GWAS_STUDY_ROWS, color: '#A855F7' },
  { key: 'ensemblGenes', rows: ENSEMBL_GENE_ROWS, color: '#6366F1' },
]

/**
 * Every queryable row across the three shipped profiles: 11,712,376.
 *
 * Summed from DATA_SCALE rather than written out, so the headline figure and
 * the chart that justifies it cannot disagree — adding a table to the chart
 * updates the hero automatically.
 */
export const TOTAL_ROWS = DATA_SCALE.reduce((sum, entry) => sum + entry.rows, 0)
