import type { LandingCopy } from './copy.types'

export const en: LandingCopy = {
  nav: {
    architecture: 'Architecture',
    data: 'Data',
    useCases: 'Use cases',
    security: 'Security',
    openApp: 'Open app',
    getStarted: 'Get started',
    menu: 'Open menu',
    language: 'Change language',
  },
  hero: {
    eyebrow: 'AI-powered research platform',
    titleLead: 'Meet',
    subtitle:
      'Every breakthrough starts with a question. GenomeChat removes the wall between curiosity and discovery.',
    cta: 'Try GenomeChat',
    stats: {
      records: 'Queryable rows',
      agents: 'Collaborating agents',
      tools: 'Agent tools',
      sources: 'Public data sources',
    },
  },
  badges: {
    k8s: 'Container-native, Kubernetes ready',
    sse: 'Real-time SSE streaming',
  },
  impact: {
    eyebrow: 'Why this matters',
    title: 'Accelerating genomics discovery',
    body: 'Every minute saved in research is a step closer to better treatments for patients. GenomeChat helps researchers go from question to discovery faster — turning days of analysis into minutes.',
  },
  architecture: {
    eyebrow: 'Architecture',
    title: 'Multi-agent architecture',
    subtitle:
      'Five specialised agents collaborate on complex research queries, with the orchestrator routing the work',
    agents: {
      coordinator: { title: 'Coordinator', description: 'Routes queries' },
      sqlAgent: { title: 'SQL Agent', description: 'Queries data' },
      coder: { title: 'Coder', description: 'Runs code' },
      researcher: { title: 'Researcher', description: 'Searches papers' },
    },
    flow: {
      query: 'Query',
      coordinator: 'Coordinator',
      orchestrator: 'Orchestrator',
      workers: 'Workers',
    },
  },
  dataScale: {
    eyebrow: 'Data scale',
    title: 'Every number here is checkable',
    subtitle: 'Three public genomics sources, built locally, switchable at runtime',
    chartTitle: 'Rows per table',
    rowsUnit: 'rows',
    footnote:
      'ClinVar tracks the weekly variant_summary release · GWAS Catalog is CC BY 4.0 · Ensembl is pinned to release-116 · all built locally and reproducibly by build_genomics_databases.py',
    tables: {
      clinvar: 'ClinVar assertions',
      gwasAssociations: 'GWAS associations',
      gwasStudies: 'GWAS studies',
      ensemblGenes: 'Ensembl genes',
      ensemblExons: 'Ensembl exons',
      ensemblTranscripts: 'Ensembl transcripts',
    },
  },
  comparison: {
    eyebrow: 'Impact',
    title: 'Transform your research workflow',
    subtitle: 'See how GenomeChat changes the way researchers explore data',
    traditionalTab: 'Traditional approach',
    cta: 'Experience the difference',
    rows: [
      { traditional: 'Days of hand-written SQL', platform: 'Minutes with natural language' },
      { traditional: 'SQL/Python expertise required', platform: 'No coding needed' },
      { traditional: 'Static reports and exports', platform: 'Real-time streaming responses' },
      {
        traditional: 'One database at a time',
        platform: 'Three genomics sources, runtime switching',
      },
      { traditional: 'Manual literature validation', platform: 'Built-in cross-validation' },
      {
        traditional: 'Local notebooks, no persistence',
        platform: 'Containerised deployment, persistent state',
      },
    ],
  },
  databases: {
    eyebrow: 'Data infrastructure',
    title: 'A pluggable data layer',
    subtitle:
      'Three data profiles switch at runtime across SQLite and DuckDB — no restart required',
    groups: {
      inUse: 'In use',
      available: 'Connector implemented',
      availableNote: 'Supported by the connection layer; no shipped profile uses these yet',
    },
    items: {
      sqlite: 'ClinVar variant archive',
      duckdb: 'GWAS / Ensembl Parquet analytics',
      mysql: 'Enterprise SQL',
      postgres: 'Enterprise SQL',
      mssql: 'Microsoft SQL Server',
      athena: 'AWS serverless SQL',
    },
  },
  useCases: {
    eyebrow: 'Use cases',
    title: 'Research use cases',
    subtitle: 'From exploratory research to clinical data analysis — all through natural language',
    exampleLabel: 'Example query',
    items: {
      variants: {
        title: 'Variant interpretation',
        description: 'Query 4.48M ClinVar variant-condition assertions',
        details: [
          'Filter variants by clinical significance and ACMG review status',
          'Break down pathogenic and likely-pathogenic calls per gene',
          'Quantify variant-of-uncertain-significance burden across gene panels',
          'Plot pathogenic variant density along each chromosome',
        ],
        example:
          'How many pathogenic and likely pathogenic variants are reported in BRCA1? Break them down by variant type',
      },
      gwas: {
        title: 'Trait genetics',
        description: 'Explore 1.19M curated SNP-trait associations',
        details: [
          'Find genome-wide significant hits (p < 5e-8) for any trait',
          'Rank pleiotropic SNPs by number of distinct associated traits',
          'Relate effect size to risk allele frequency',
          'Join to study metadata for sample size and ancestry context',
        ],
        example:
          'Find genome-wide significant associations for type 2 diabetes. Show the strongest 25 with their mapped genes',
      },
      literature: {
        title: 'Literature validation',
        description: 'Cross-reference findings with published research',
        details: [
          'Search biomedical literature through Europe PMC',
          'Retrieve papers by DOI for citation',
          'Validate computational findings against publications',
          'Generate summaries with source attribution',
        ],
        example: 'Find recent papers on polygenic risk scores for coronary artery disease',
      },
      annotation: {
        title: 'Gene annotation',
        description: 'Query GRCh38 gene, transcript and exon annotation',
        details: [
          'Resolve genes, transcripts and exons by symbol or Ensembl ID',
          'Read GRCh38 chromosome, start/end coordinates and strand',
          'Pick MANE Select transcripts as the representative per gene',
          'Anchor ClinVar and GWAS results to reference gene models',
        ],
        example:
          'List all protein-coding transcripts of TP53 with their exon counts and genomic coordinates',
      },
    },
  },
  security: {
    eyebrow: 'Compliance & security',
    title: 'Built for production',
    subtitle: 'From authentication to sandboxing to SQL review — every layer serves trustworthy results',
    items: {
      auth: {
        title: 'JWT authentication',
        description: 'Token-based auth with automatic refresh and bcrypt password hashing',
      },
      sandbox: {
        title: 'Isolated sandbox',
        description:
          'Code runs in a separate container: non-root, read-only rootfs, PID and resource caps',
      },
      grounding: {
        title: 'Schema grounding',
        description: 'Agents only ever see real database schemas, which suppresses hallucination at the source',
      },
      kubernetes: {
        title: 'Kubernetes ready',
        description: 'Containerised deployment, Vault-injected secrets, runtime API URL for the frontend',
      },
      validation: {
        title: 'Validation layers',
        description: 'SQL passes LLM review, DDL rejection and automatic row limits before it runs',
      },
      isolation: {
        title: 'User isolation',
        description: 'MongoDB checkpoints are keyed user_id:conversation_id, so state never leaks across users',
      },
    },
    badges: {
      auth: 'JWT auth',
      sandboxed: 'Sandboxed',
      validated: 'SQL validated',
      deployable: 'Containerised',
    },
  },
  cta: {
    eyebrow: 'Get started',
    title: 'Ready to transform genomics research?',
    subtitle:
      'Query variant and association records, generate visualisations, and validate findings — all through natural conversation',
    button: 'Try GenomeChat',
  },
}
