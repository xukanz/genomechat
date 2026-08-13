/**
 * Static seed data for the demo build (`demo.html`).
 *
 * Descriptions and example questions for the three databases are copied
 * verbatim from `backend/src/config/database_registry.py` so the demo shows
 * real product copy instead of invented placeholder text.
 */

import type { User } from '../types/auth'
import type { DatabaseInfo } from '../types/database'
import type { Project } from '../types/project'
import type { Plan } from '../types/conversation'

/**
 * Chart images live in `public/demo/`. Resolve them against Vite's base URL so
 * they still load when the demo is served from a subpath (GitHub Pages).
 * `BASE_URL` always ends in a slash.
 */
const chart = (filename: string) => `${import.meta.env.BASE_URL}demo/${filename}`

/** Credentials pre-filled on the demo login page. Any non-empty pair works. */
export const DEMO_CREDENTIALS = {
  email: 'demo@genomechat.ai',
  password: 'demo1234',
} as const

export const DEMO_USER: User = {
  id: 'demo-user',
  email: DEMO_CREDENTIALS.email,
  name: 'Dr. Alex Rivera',
  role: 'researcher',
  created_at: '2026-01-01T00:00:00Z',
}

export const DEMO_PROJECT: Project = {
  id: 'demo-project',
  user_id: DEMO_USER.id,
  name: 'Demo Workspace',
  description: 'Sample conversations for exploring GenomeChat',
  color: '#0066CC',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  is_default: true,
  conversation_count: 2,
  artifact_count: 3,
  report_count: 0,
  last_conversation_at: '2026-01-05T00:00:00Z',
  shares: [],
  is_owner: true,
  is_shared: false,
}

export const DEMO_DATABASES: DatabaseInfo[] = [
  {
    id: 'clinvar',
    name: 'clinvar',
    display_name: 'ClinVar',
    database_type: 'sqlite',
    sql_dialect: 'sqlite',
    domain: 'clinical genetics',
    is_active: true,
    status: 'connected',
    description:
      'NCBI ClinVar: a public archive of reported relationships between human genetic ' +
      'variants and phenotypes, with supporting evidence. One row per variant/condition ' +
      'assertion, carrying clinical significance (Pathogenic / Likely pathogenic / ' +
      'Uncertain significance / Benign), the ACMG-style review status, submitter count, ' +
      'gene symbol, dbSNP rsID, and GRCh38 coordinates.',
    example_questions: [
      {
        label: 'Clinical Significance Mix',
        text: 'How many variants are in ClinVar for each clinical significance category? Show the top 10 as a bar chart.',
        complexity: 'basic',
      },
      {
        label: 'Variants in a Gene',
        text: 'How many pathogenic and likely pathogenic variants are reported in BRCA1? Break them down by variant type.',
        complexity: 'basic',
      },
      {
        label: 'Review Confidence',
        text: 'Compare the review status distribution between pathogenic and benign variants. Are pathogenic calls better supported?',
        complexity: 'medium',
      },
      {
        label: 'Most-Studied Genes',
        text: 'Which 20 genes have the most submitted variants? For each, show the fraction that are variants of uncertain significance (VUS).',
        complexity: 'medium',
      },
    ],
  },
  {
    id: 'gwas',
    name: 'gwas',
    display_name: 'GWAS Catalog',
    database_type: 'duckdb',
    sql_dialect: 'postgresql',
    domain: 'statistical genetics',
    is_active: false,
    status: 'available',
    description:
      'The NHGRI-EBI GWAS Catalog: curated SNP-trait associations from published ' +
      'genome-wide association studies. `associations` holds one row per reported ' +
      'association with p-value, effect size, risk allele and frequency, mapped gene, ' +
      'and an EFO ontology term for the trait; `studies` holds study-level metadata.',
    example_questions: [
      {
        label: 'Most-Studied Traits',
        text: 'What are the 20 most frequently studied traits in the GWAS Catalog by number of reported associations?',
        complexity: 'basic',
      },
      {
        label: 'Associations for a Trait',
        text: 'Find genome-wide significant associations (p < 5e-8) for type 2 diabetes. Show the strongest 25 with their mapped genes.',
        complexity: 'basic',
      },
      {
        label: 'Pleiotropic Variants',
        text: 'Which SNPs are associated with the largest number of distinct traits? Show the top 15 and list their traits.',
        complexity: 'medium',
      },
      {
        label: 'Effect Size vs Frequency',
        text: 'Plot effect size against risk allele frequency for genome-wide significant associations. Does the expected inverse relationship hold?',
        complexity: 'medium',
      },
    ],
  },
  {
    id: 'ensembl',
    name: 'ensembl',
    display_name: 'Ensembl GRCh38',
    database_type: 'duckdb',
    sql_dialect: 'postgresql',
    domain: 'genome annotation',
    is_active: false,
    status: 'available',
    description:
      'Ensembl GRCh38 release 116 gene annotation, queried through DuckDB. Four ' +
      'tables — genes, transcripts, exons and chromosomes — covering gene structure, ' +
      'biotypes, genomic coordinates, transcript isoforms, coding sequence lengths and ' +
      'canonical/MANE transcript flags. Gene symbols are HGNC.',
    example_questions: [
      {
        label: 'Gene Biotypes',
        text: 'How many genes are annotated per biotype (protein_coding, lncRNA, pseudogene, etc.)? Show the top 15 as a bar chart.',
        complexity: 'basic',
      },
      {
        label: 'Look Up a Gene',
        text: 'Find the gene TP53: its Ensembl ID, chromosome, coordinates, strand, biotype, and its MANE Select transcript.',
        complexity: 'basic',
      },
      {
        label: 'Transcripts per Gene',
        text: 'Which 20 protein-coding genes have the most annotated transcripts?',
        complexity: 'medium',
      },
      {
        label: 'Gene Density',
        text: 'Count protein-coding genes per chromosome, join to chromosome length, and plot genes per megabase.',
        complexity: 'medium',
      },
    ],
  },
]

export interface DemoRawMessage {
  type: 'human' | 'ai' | 'system'
  content: string
  name?: string
  files?: Array<{
    id: string
    filename: string
    url: string
    fileType: string
    contentType: string
    isImage: boolean
  }>
}

export interface DemoConversation {
  id: string
  user_id: string
  title: string
  project_id: string | null
  created_at: string
  updated_at: string
  messages: DemoRawMessage[]
}

export const DEMO_CONVERSATIONS: DemoConversation[] = [
  {
    id: 'demo-conv-brca1',
    user_id: DEMO_USER.id,
    title: 'BRCA1 pathogenic variant breakdown',
    project_id: DEMO_PROJECT.id,
    created_at: '2026-01-04T15:20:00Z',
    updated_at: '2026-01-04T15:22:00Z',
    messages: [
      {
        type: 'human',
        content:
          'How many pathogenic and likely pathogenic variants are reported in BRCA1? Break them down by variant type.',
      },
      {
        type: 'system',
        name: 'coordinator',
        content: 'Identifying target gene (BRCA1) and dataset (ClinVar), then routing to the SQL Agent.',
      },
      {
        type: 'human',
        name: 'sql_agent',
        content:
          "Filtered variant_summary where gene_symbol = 'BRCA1' and clinical_significance in " +
          "('Pathogenic', 'Likely pathogenic'). Found 187 matching variants: 96 pathogenic, " +
          '91 likely pathogenic. Grouped by variant_type: missense (74), frameshift (52), ' +
          'nonsense (38), splice-site (23).',
      },
      {
        type: 'system',
        name: 'coder',
        content: 'Rendering a bar chart of BRCA1 variant counts by type.',
      },
      {
        type: 'ai',
        content: '',
        files: [
          {
            id: 'demo-file-brca1',
            filename: 'brca1_variant_types.png',
            url: chart('clinvar-variants.svg'),
            fileType: 'image',
            contentType: 'image/svg+xml',
            isImage: true,
          },
        ],
      },
      {
        type: 'ai',
        content:
          '## BRCA1 Pathogenic Variant Breakdown\n\n' +
          'ClinVar reports **187** BRCA1 variants classified as Pathogenic or Likely pathogenic ' +
          '(96 and 91 respectively). By variant type:\n\n' +
          '| Variant type | Count |\n|---|---|\n| Missense | 74 |\n| Frameshift | 52 |\n' +
          '| Nonsense | 38 |\n| Splice-site | 23 |\n\n' +
          'Missense variants are the largest single category, though frameshift and nonsense ' +
          'variants — which reliably truncate the protein — together account for a comparable ' +
          'share of pathogenic calls.',
      },
    ],
  },
  {
    id: 'demo-conv-t2d',
    user_id: DEMO_USER.id,
    title: 'Type 2 diabetes GWAS hits',
    project_id: DEMO_PROJECT.id,
    created_at: '2026-01-05T09:05:00Z',
    updated_at: '2026-01-05T09:07:00Z',
    messages: [
      {
        type: 'human',
        content:
          'Find genome-wide significant associations (p < 5e-8) for type 2 diabetes. Show the strongest 25 with their mapped genes.',
      },
      {
        type: 'system',
        name: 'coordinator',
        content: 'Mapping "type 2 diabetes" to its EFO trait term and routing to the SQL Agent for the GWAS Catalog.',
      },
      {
        type: 'human',
        name: 'sql_agent',
        content:
          "Queried associations joined to studies where mapped_trait = 'type 2 diabetes mellitus' " +
          'and p_value < 5e-8, ordered by p-value ascending, limit 25. Top hits cluster near ' +
          'TCF7L2 on chr10 and KCNQ1 on chr11.',
      },
      {
        type: 'system',
        name: 'coder',
        content: 'Plotting a Manhattan-style chart of the strongest associations by chromosome.',
      },
      {
        type: 'ai',
        content: '',
        files: [
          {
            id: 'demo-file-t2d',
            filename: 't2d_manhattan.png',
            url: chart('gwas-manhattan.svg'),
            fileType: 'image',
            contentType: 'image/svg+xml',
            isImage: true,
          },
        ],
      },
      {
        type: 'ai',
        content:
          '## Type 2 Diabetes — Top GWAS Associations\n\n' +
          'The 25 strongest genome-wide significant associations (p < 5e-8) are dominated by two ' +
          'loci: **TCF7L2** (chr10), the single strongest and most replicated T2D locus in the ' +
          'GWAS Catalog, and **KCNQ1** (chr11), a well-established regulator of insulin secretion.\n\n' +
          'Both loci show multiple independent signals across several studies, consistent with ' +
          'their established roles in T2D pathophysiology.',
      },
    ],
  },
]

export interface DemoStep {
  type: 'plan' | 'agent_start' | 'agent_end' | 'thinking' | 'file' | 'answer'
  agentName?: string
  content?: string
  plan?: Plan
  file?: {
    filename: string
    url: string
    fileType: string
    contentType: string
    isImage: boolean
  }
  answer?: string
}

export interface DemoScenario {
  id: string
  keywords: string[]
  databaseId: string
  steps: DemoStep[]
}

const BRCA1_PLAN: Plan = {
  title: 'Analyze BRCA1 pathogenic variants in ClinVar',
  thought:
    'The user wants a breakdown of pathogenic/likely-pathogenic BRCA1 variants by type — ' +
    'query ClinVar, aggregate by variant type, then visualize the split.',
  steps: [
    { title: 'Query ClinVar', description: 'Filter ClinVar for BRCA1 variants classified as pathogenic or likely pathogenic', status: 'pending', agent_name: 'SQL Agent' },
    { title: 'Aggregate by variant type', description: 'Group matching records by variant_type and count occurrences', status: 'pending', agent_name: 'SQL Agent' },
    { title: 'Generate visualization', description: 'Render a bar chart of variant counts by type', status: 'pending', agent_name: 'Coder' },
    { title: 'Summarize findings', description: 'Write up the breakdown with clinical context', status: 'pending', agent_name: 'Orchestrator' },
  ],
}

const T2D_PLAN: Plan = {
  title: 'Survey type 2 diabetes GWAS associations',
  thought:
    'The user wants the strongest genome-wide significant hits for type 2 diabetes — ' +
    'query the GWAS Catalog, rank by p-value, then plot the top loci.',
  steps: [
    { title: 'Map the trait', description: 'Resolve "type 2 diabetes" to its EFO trait term', status: 'pending', agent_name: 'SQL Agent' },
    { title: 'Query associations', description: 'Filter associations with p < 5e-8, ordered by significance', status: 'pending', agent_name: 'SQL Agent' },
    { title: 'Generate visualization', description: 'Plot a Manhattan-style chart of the strongest loci by chromosome', status: 'pending', agent_name: 'Coder' },
    { title: 'Summarize findings', description: 'Write up the top loci with biological context', status: 'pending', agent_name: 'Orchestrator' },
  ],
}

const TP53_PLAN: Plan = {
  title: 'Look up TP53 in Ensembl GRCh38',
  thought:
    "The user wants TP53's gene record and its MANE Select transcript — query the genes and " +
    'transcripts tables, then also compare its isoform count against other genes.',
  steps: [
    { title: 'Query gene record', description: 'Look up TP53 in the genes table: ID, chromosome, coordinates, strand, biotype', status: 'pending', agent_name: 'SQL Agent' },
    { title: 'Query transcripts', description: 'Join to transcripts to find the MANE Select isoform and count total transcripts', status: 'pending', agent_name: 'SQL Agent' },
    { title: 'Generate visualization', description: 'Chart transcript counts for TP53 against other high-isoform genes', status: 'pending', agent_name: 'Coder' },
    { title: 'Summarize findings', description: 'Write up the gene record and isoform complexity', status: 'pending', agent_name: 'Orchestrator' },
  ],
}

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: 'brca1',
    keywords: ['brca1', 'brca'],
    databaseId: 'clinvar',
    steps: [
      { type: 'plan', plan: BRCA1_PLAN },
      { type: 'agent_start', agentName: 'SQL Agent', content: 'Querying ClinVar for BRCA1 variant records...' },
      { type: 'thinking', agentName: 'SQL Agent', content: "Filtering variant_summary where gene_symbol = 'BRCA1' and clinical_significance in ('Pathogenic', 'Likely pathogenic')..." },
      { type: 'agent_end', agentName: 'SQL Agent', content: 'Found 187 matching variants: 96 pathogenic, 91 likely pathogenic. Grouped by variant_type: missense (74), frameshift (52), nonsense (38), splice-site (23).' },
      { type: 'agent_start', agentName: 'Coder', content: 'Rendering a bar chart of BRCA1 variant counts by type...' },
      { type: 'file', agentName: 'Coder', file: { filename: 'brca1_variant_types.png', url: chart('clinvar-variants.svg'), fileType: 'image', contentType: 'image/svg+xml', isImage: true } },
      { type: 'agent_end', agentName: 'Coder', content: 'Chart generated.' },
      {
        type: 'answer',
        answer:
          '## BRCA1 Pathogenic Variant Breakdown\n\n' +
          'ClinVar reports **187** BRCA1 variants classified as Pathogenic or Likely pathogenic ' +
          '(96 and 91 respectively). By variant type:\n\n' +
          '| Variant type | Count |\n|---|---|\n| Missense | 74 |\n| Frameshift | 52 |\n' +
          '| Nonsense | 38 |\n| Splice-site | 23 |\n\n' +
          'Missense variants are the largest single category, though frameshift and nonsense ' +
          'variants — which reliably truncate the protein — together account for a comparable ' +
          'share of pathogenic calls.',
      },
    ],
  },
  {
    id: 't2d',
    keywords: ['diabetes', 't2d', 'gwas'],
    databaseId: 'gwas',
    steps: [
      { type: 'plan', plan: T2D_PLAN },
      { type: 'agent_start', agentName: 'SQL Agent', content: 'Mapping "type 2 diabetes" to its EFO trait term...' },
      { type: 'thinking', agentName: 'SQL Agent', content: "Querying associations joined to studies where mapped_trait = 'type 2 diabetes mellitus' and p_value < 5e-8, ordered by significance, limit 25..." },
      { type: 'agent_end', agentName: 'SQL Agent', content: 'Top hits cluster near TCF7L2 on chr10 and KCNQ1 on chr11, each with multiple independent signals.' },
      { type: 'agent_start', agentName: 'Coder', content: 'Plotting a Manhattan-style chart of the strongest loci...' },
      { type: 'file', agentName: 'Coder', file: { filename: 't2d_manhattan.png', url: chart('gwas-manhattan.svg'), fileType: 'image', contentType: 'image/svg+xml', isImage: true } },
      { type: 'agent_end', agentName: 'Coder', content: 'Chart generated.' },
      {
        type: 'answer',
        answer:
          '## Type 2 Diabetes — Top GWAS Associations\n\n' +
          'The 25 strongest genome-wide significant associations (p < 5e-8) are dominated by two ' +
          'loci: **TCF7L2** (chr10), the single strongest and most replicated T2D locus in the ' +
          'GWAS Catalog, and **KCNQ1** (chr11), a well-established regulator of insulin secretion.\n\n' +
          'Both loci show multiple independent signals across several studies, consistent with ' +
          'their established roles in T2D pathophysiology.',
      },
    ],
  },
  {
    id: 'tp53',
    keywords: ['tp53', 'ensembl', 'transcript'],
    databaseId: 'ensembl',
    steps: [
      { type: 'plan', plan: TP53_PLAN },
      { type: 'agent_start', agentName: 'SQL Agent', content: 'Looking up TP53 in the Ensembl genes table...' },
      { type: 'thinking', agentName: 'SQL Agent', content: "Joining genes to transcripts on gene_id, filtering gene_symbol = 'TP53', flagging the MANE Select transcript..." },
      { type: 'agent_end', agentName: 'SQL Agent', content: 'TP53: ENSG00000141510, chr17:7,661,779-7,687,538, reverse strand, protein_coding, 42 annotated transcripts. MANE Select: ENST00000269305.' },
      { type: 'agent_start', agentName: 'Coder', content: 'Charting transcript counts for TP53 against other high-isoform genes...' },
      { type: 'file', agentName: 'Coder', file: { filename: 'transcripts_per_gene.png', url: chart('ensembl-transcripts.svg'), fileType: 'image', contentType: 'image/svg+xml', isImage: true } },
      { type: 'agent_end', agentName: 'Coder', content: 'Chart generated.' },
      {
        type: 'answer',
        answer:
          '## TP53 — Gene Record & Isoform Complexity\n\n' +
          '**TP53** (`ENSG00000141510`) sits on chromosome 17 (7,661,779–7,687,538, reverse ' +
          'strand), biotype `protein_coding`, with its MANE Select transcript `ENST00000269305`.\n\n' +
          'It has **42** annotated transcripts — among the highest isoform counts of any ' +
          'protein-coding gene, reflecting its extensively studied alternative splicing and role ' +
          'in the DNA-damage response.',
      },
    ],
  },
]

export const DEMO_FALLBACK_SCENARIO: DemoScenario = {
  id: 'fallback',
  keywords: [],
  databaseId: 'clinvar',
  steps: [
    {
      type: 'plan',
      plan: {
        title: 'Interpreting your question',
        thought: 'Demo mode uses a small set of scripted scenarios — routing this to a representative ClinVar example.',
        steps: [
          { title: 'Query ClinVar', description: 'Run a representative variant-significance query', status: 'pending', agent_name: 'SQL Agent' },
          { title: 'Summarize findings', description: 'Write up the result', status: 'pending', agent_name: 'Orchestrator' },
        ],
      },
    },
    { type: 'agent_start', agentName: 'SQL Agent', content: 'Running a representative ClinVar query...' },
    { type: 'agent_end', agentName: 'SQL Agent', content: 'Pathogenic (18,412), Likely pathogenic (9,047), Uncertain significance (61,203), Benign (24,890), Likely benign (33,156).' },
    {
      type: 'answer',
      answer:
        '_This is a scripted demo response — try one of the example questions above, or ask ' +
        'about **BRCA1** (ClinVar), **type 2 diabetes** (GWAS Catalog), or **TP53** (Ensembl) for ' +
        'a full simulated analysis._\n\n' +
        'For reference, here is the overall clinical significance mix in ClinVar:\n\n' +
        '| Category | Count |\n|---|---|\n| Pathogenic | 18,412 |\n| Likely pathogenic | 9,047 |\n' +
        '| Uncertain significance | 61,203 |\n| Likely benign | 33,156 |\n| Benign | 24,890 |',
    },
  ],
}

export function pickScenario(message: string): DemoScenario {
  const lower = message.toLowerCase()
  const match = DEMO_SCENARIOS.find((scenario) => scenario.keywords.some((kw) => lower.includes(kw)))
  return match || DEMO_FALLBACK_SCENARIO
}
