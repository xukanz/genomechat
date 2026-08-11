# GWAS Catalog Database Context

## Database Overview

The NHGRI-EBI GWAS Catalog is a curated collection of SNP–trait associations extracted from published genome-wide association studies. One row per reported association, with study-level metadata joinable on `"PUBMEDID"`.

## Key Characteristics

- **Database Type**: DuckDB over Parquet files
- **Primary Focus**: Genotype–phenotype association
- **Data Source**: NHGRI-EBI GWAS Catalog, latest release
- **SQL Dialect**: **PostgreSQL** (DuckDB implements PostgreSQL syntax)
- **License**: CC BY 4.0

## ⚠️ Column Names Need Double Quotes

The Catalog's TSV headers are preserved verbatim, so most column names contain
spaces, slashes, or symbols. **Every column reference must be double-quoted**:

```sql
SELECT "DISEASE/TRAIT", "P-VALUE" FROM associations    -- correct
SELECT DISEASE/TRAIT, P-VALUE FROM associations        -- parses as division
```

Every column is also loaded as **VARCHAR**. The source has free-text and
sentinel values mixed into numeric fields, so typing is deferred to query time.
Cast explicitly whenever comparing numerically:

```sql
WHERE TRY_CAST("P-VALUE" AS DOUBLE) < 5e-8
```

Prefer `TRY_CAST` over `CAST` — it yields NULL instead of raising on the rows
that hold text.

## Schema Overview

### Table: `associations` (38 columns)

Reference the file directly, or via the profile's Parquet glob:

```sql
SELECT * FROM 'associations.parquet' LIMIT 5;
```

Grouped by what they're for:

**Study provenance**
| Column | Notes |
|---|---|
| `"STUDY ACCESSION"` | GCST accession. Present only on this table — **not** a join key to `studies` |
| `"PUBMEDID"` | PubMed ID. The join key to `studies`, and the natural handoff to the literature-search tools |
| `"FIRST AUTHOR"`, `"DATE"`, `"JOURNAL"`, `"LINK"`, `"STUDY"` | Publication metadata |
| `"DATE ADDED TO CATALOG"` | Curation date, not publication date |

**Trait**
| Column | Notes |
|---|---|
| `"DISEASE/TRAIT"` | Author-reported trait, free text — highly variable wording |
| `"MAPPED_TRAIT"` | Curated EFO ontology term — **prefer this for grouping** |
| `"MAPPED_TRAIT_URI"` | EFO URI; multiple URIs are comma-separated |

**Variant**
| Column | Notes |
|---|---|
| `"SNPS"` | rsID(s). May hold several, delimited by `;` or `x` for interactions |
| `"STRONGEST SNP-RISK ALLELE"` | Format `rs1234-A`; `-?` when the allele is unknown |
| `"CHR_ID"`, `"CHR_POS"` | Chromosome and position; blank for unmapped variants |
| `"SNP_ID_CURRENT"`, `"MERGED"` | dbSNP bookkeeping — `MERGED=1` means the rsID was retired |
| `"CONTEXT"` | Functional class, e.g. `intron_variant`, `missense_variant` |
| `"INTERGENIC"` | `1` when the SNP falls outside a gene |

**Gene mapping**
| Column | Notes |
|---|---|
| `"MAPPED_GENE"` | Ensembl-mapped gene(s). `A - B` means intergenic between two genes; `A, B` means overlapping several |
| `"REPORTED GENE(S)"` | What the authors named — often disagrees with the mapping |
| `"UPSTREAM_GENE_ID"`, `"DOWNSTREAM_GENE_ID"`, `"SNP_GENE_IDS"` | Ensembl gene IDs |
| `"UPSTREAM_GENE_DISTANCE"`, `"DOWNSTREAM_GENE_DISTANCE"` | Base pairs to the flanking genes |

**Statistics**
| Column | Notes |
|---|---|
| `"P-VALUE"` | Association p-value, as text in scientific notation |
| `"PVALUE_MLOG"` | −log₁₀(p). **Easier and safer to sort on** than the raw p-value |
| `"P-VALUE (TEXT)"` | Free-text qualifier, e.g. `(European)`, `(male)` |
| `"OR or BETA"` | Odds ratio **or** beta — the column does not say which. Read `"95% CI (TEXT)"` for units |
| `"95% CI (TEXT)"` | Confidence interval as free text, often with the unit |
| `"RISK ALLELE FREQUENCY"` | Frequency of the risk allele; `NR` when not reported |

**Cohort / platform**
| Column | Notes |
|---|---|
| `"INITIAL SAMPLE SIZE"`, `"REPLICATION SAMPLE SIZE"` | **Free-text prose**, e.g. "12,345 European ancestry cases, 6,789 controls". Not numeric — parse in the coder agent |
| `"PLATFORM [SNPS PASSING QC]"`, `"GENOTYPING TECHNOLOGY"` | Array or sequencing platform |
| `"REGION"` | Cytogenetic band |
| `"CNV"` | `Y` for copy-number association rows |

### Table: `studies` (12 columns, ~229,600 rows)

`"DATE ADDED TO CATALOG"`, `"PUBMEDID"`, `"FIRST AUTHOR"`, `"DATE"`,
`"JOURNAL"`, `"LINK"`, `"STUDY"`, `"DISEASE/TRAIT"`,
`"INITIAL SAMPLE SIZE"`, `"REPLICATION SAMPLE SIZE"`,
`"PLATFORM [SNPS PASSING QC]"`, `"ASSOCIATION COUNT"`.

**The join key is `"PUBMEDID"`, not `"STUDY ACCESSION"`.** The accession
column exists only on `associations`; `studies` does not carry it, so
`USING ("STUDY ACCESSION")` fails to bind. Note also that a PubMed ID can map
to several studies (one paper often reports several GWAS), so the join is
many-to-many — deduplicate before counting.

`associations` already carries most study fields denormalised, so a join is
only needed for `"ASSOCIATION COUNT"` or to enumerate studies with no
associations recorded.

## Critical Query Guidance

### Genome-wide significance

The conventional threshold is p < 5×10⁻⁸. Because `"P-VALUE"` is text:

```sql
SELECT "DISEASE/TRAIT", "SNPS", "MAPPED_GENE", "P-VALUE", "OR or BETA"
FROM associations
WHERE TRY_CAST("P-VALUE" AS DOUBLE) < 5e-8
ORDER BY TRY_CAST("PVALUE_MLOG" AS DOUBLE) DESC
LIMIT 25;
```

**Always order by `"PVALUE_MLOG"` descending, never by the cast p-value.** The
strongest associations carry exponents far below what a double can hold — real
rows in this release include `2E-28539` — and `TRY_CAST` silently returns
`0.0` for them. Ordering on the raw p-value therefore scrambles exactly the
hits you care about. `"PVALUE_MLOG"` holds −log₁₀(p) as an ordinary number
(`28538.69…` for that row) and sorts correctly.

The `< 5e-8` filter still behaves, since underflow to `0.0` satisfies it.

### Group by the ontology term, not the free text

`"DISEASE/TRAIT"` is author-authored, so "Type 2 diabetes",
"Type II diabetes", and "T2D" are separate strings. `"MAPPED_TRAIT"` is
curated:

```sql
SELECT "MAPPED_TRAIT", COUNT(*) AS n
FROM associations
WHERE "MAPPED_TRAIT" IS NOT NULL AND "MAPPED_TRAIT" != ''
GROUP BY 1
ORDER BY n DESC
LIMIT 20;
```

For a trait search, match both columns case-insensitively:

```sql
WHERE lower("MAPPED_TRAIT") LIKE '%diabetes%'
   OR lower("DISEASE/TRAIT") LIKE '%diabetes%'
```

### "OR or BETA" is two measures in one column

Odds ratios cluster around 1 and are always positive; betas centre on 0 and can
be negative. Never average the column as-is. Split on sign and magnitude, or
read the unit out of `"95% CI (TEXT)"`, and say which you used.

### Empty strings, not NULLs

Missing values often arrive as `''` rather than NULL. Guard both:

```sql
WHERE "MAPPED_GENE" IS NOT NULL AND "MAPPED_GENE" != ''
```

### Multi-valued cells

`"SNPS"`, `"MAPPED_GENE"`, and `"MAPPED_TRAIT_URI"` can hold several values in
one cell. Expand with `unnest`, but note that DuckDB rejects `unnest` in a
SELECT list that also has `GROUP BY` — do the expansion in a subquery first:

```sql
SELECT gene, COUNT(*) AS n
FROM (
  SELECT unnest(string_split("MAPPED_GENE", ', ')) AS gene
  FROM associations
  WHERE "MAPPED_GENE" IS NOT NULL AND "MAPPED_GENE" != ''
)
GROUP BY 1
ORDER BY n DESC
LIMIT 20;
```

## Query Patterns

**Pleiotropic variants — SNPs hitting many distinct traits**
```sql
SELECT "SNPS", COUNT(DISTINCT "MAPPED_TRAIT") AS traits
FROM associations
WHERE TRY_CAST("P-VALUE" AS DOUBLE) < 5e-8
GROUP BY 1
ORDER BY traits DESC
LIMIT 15;
```

**Effect size against allele frequency**
```sql
SELECT TRY_CAST("RISK ALLELE FREQUENCY" AS DOUBLE) AS raf,
       TRY_CAST("OR or BETA" AS DOUBLE)            AS effect
FROM associations
WHERE TRY_CAST("P-VALUE" AS DOUBLE) < 5e-8
  AND TRY_CAST("RISK ALLELE FREQUENCY" AS DOUBLE) IS NOT NULL
  AND TRY_CAST("OR or BETA" AS DOUBLE) IS NOT NULL;
```

**Join to studies for association counts** — on `"PUBMEDID"`
```sql
SELECT s."STUDY",
       s."ASSOCIATION COUNT",
       COUNT(DISTINCT a."SNPS") AS distinct_snps
FROM studies s
LEFT JOIN associations a ON a."PUBMEDID" = s."PUBMEDID"
GROUP BY 1, 2
ORDER BY TRY_CAST(s."ASSOCIATION COUNT" AS INTEGER) DESC
LIMIT 20;
```

**Publication trend over time**
```sql
SELECT substr("DATE", 1, 4) AS year, COUNT(DISTINCT "STUDY ACCESSION") AS studies
FROM associations
WHERE "DATE" IS NOT NULL AND "DATE" != ''
GROUP BY 1
ORDER BY 1;
```

## Domain Context

The GWAS Catalog is the standard reference for what has been found by
genome-wide association, and it feeds:
- Polygenic risk score construction
- Target identification and prioritisation
- Trait-to-gene mapping and colocalisation studies
- Meta-analysis of published findings

Two caveats worth stating in any result. **Ancestry is heavily skewed** toward
European-ancestry cohorts, so effect sizes and allele frequencies do not
transfer cleanly to other populations — the sample-size prose fields carry the
ancestry description. And the catalogue records **reported associations, not
replicated truths**: a row is evidence that something was published, and the
p-value threshold used varies by era and study design.

Because every row carries `"PUBMEDID"`, every association stays traceable to
its source publication — carry the PubMed ID through into results so the
underlying paper can be looked up.
