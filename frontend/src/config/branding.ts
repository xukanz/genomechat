/**
 * Product branding.
 *
 * Single source of truth for the product name and tagline so a rebrand is a
 * one-file change rather than a grep across components.
 */

export const BRANDING = {
  /** Short product name shown in the header and page title. */
  name: 'GenomeChat',
  /** One-line description used on auth pages and the document title. */
  tagline: 'Conversational AI for genomics research',
  /**
   * Longer blurb for empty states and onboarding copy.
   */
  description:
    'Ask questions in plain language across ClinVar, the GWAS Catalog, and ' +
    'Ensembl. Query, analyse, plot, and search the literature.',
} as const
