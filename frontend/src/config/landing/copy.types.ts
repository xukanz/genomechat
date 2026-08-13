/**
 * Shape of the landing page's copy.
 *
 * Both locale files are typed against this, so a key added here without a
 * translation in copy.zh.ts or copy.en.ts fails `npm run type-check`. That
 * compile-time completeness check is the whole reason this is a typed
 * dictionary rather than react-i18next.
 *
 * Numbers never appear here — they live in ./facts.ts so the two locales
 * cannot drift apart on a figure.
 */

interface Titled {
  title: string
  description: string
}

export interface LandingCopy {
  nav: {
    architecture: string
    data: string
    useCases: string
    security: string
    openApp: string
    getStarted: string
    menu: string
    language: string
  }
  hero: {
    eyebrow: string
    titleLead: string
    subtitle: string
    cta: string
    stats: {
      records: string
      agents: string
      databases: string
      sources: string
    }
  }
  badges: {
    k8s: string
    sse: string
  }
  impact: {
    eyebrow: string
    title: string
    body: string
  }
  architecture: {
    eyebrow: string
    title: string
    subtitle: string
    agents: {
      coordinator: Titled
      sqlAgent: Titled
      coder: Titled
      researcher: Titled
    }
    flow: {
      query: string
      coordinator: string
      orchestrator: string
      workers: string
    }
  }
  dataScale: {
    eyebrow: string
    title: string
    subtitle: string
    chartTitle: string
    rowsUnit: string
    footnote: string
    tables: {
      clinvar: string
      gwasAssociations: string
      gwasStudies: string
      ensemblGenes: string
      ensemblExons: string
      ensemblTranscripts: string
    }
  }
  comparison: {
    eyebrow: string
    title: string
    subtitle: string
    traditionalTab: string
    cta: string
    rows: { traditional: string; platform: string }[]
  }
  databases: {
    eyebrow: string
    title: string
    subtitle: string
    items: {
      sqlite: string
      duckdb: string
      mysql: string
      postgres: string
      mssql: string
      athena: string
      mongodb: string
    }
  }
  useCases: {
    eyebrow: string
    title: string
    subtitle: string
    exampleLabel: string
    items: {
      variants: Titled & { details: string[]; example: string }
      gwas: Titled & { details: string[]; example: string }
      literature: Titled & { details: string[]; example: string }
      annotation: Titled & { details: string[]; example: string }
    }
  }
  security: {
    eyebrow: string
    title: string
    subtitle: string
    items: {
      auth: Titled
      sandbox: Titled
      grounding: Titled
      kubernetes: Titled
      validation: Titled
      isolation: Titled
    }
    badges: {
      auth: string
      sandboxed: string
      validated: string
      deployable: string
    }
  }
  cta: {
    eyebrow: string
    title: string
    subtitle: string
    button: string
  }
}
