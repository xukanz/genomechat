# ClinVar Database Context

## Database Overview

ClinVar is NCBI's public archive of reported relationships between human genetic variants and phenotypes, together with the supporting evidence. Each row is one variant, with its associated conditions and the aggregated classification across all submitters.

## Key Characteristics

- **Database Type**: SQLite
- **Primary Focus**: Variant-disease clinical interpretation
- **Data Source**: NCBI ClinVar weekly `variant_summary` release
- **SQL Dialect**: SQLite (use SQLite-compatible SQL syntax)
- **Assembly**: GRCh38 only (the build script filters other assemblies out)
- **License**: Public domain (US Government work)

## Schema Overview

### Table: `variants`

Roughly **4.48 million rows**, one per variant. All coordinates are GRCh38.

| Column | Type | Notes |
|---|---|---|
| `variation_id` | INTEGER | ClinVar's stable variant identifier. Effectively unique here (~2,300 exact duplicate rows out of 4.48M) |
| `variant_type` | TEXT | `single nucleotide variant`, `Deletion`, `Duplication`, `Indel`, `Microsatellite`, ... |
| `name` | TEXT | HGVS-style full name, e.g. `NM_007294.4(BRCA1):c.5266dupC (p.Gln1756fs)` |
| `gene_id` | INTEGER | NCBI Gene ID |
| `gene_symbol` | TEXT | HGNC symbol. NULL for intergenic or large events; may list several symbols |
| `clinical_significance` | TEXT | Free-text label, 107 distinct values — see the important note below |
| `clin_sig_simple` | INTEGER | `1` = pathogenic/likely pathogenic, `0` = benign/likely benign, `-1` = neither (VUS, conflicting, not provided) |
| `rsid` | TEXT | dbSNP rsID without the `rs` prefix; NULL when unmapped |
| `phenotype_ids` | TEXT | Ontology refs (MedGen, OMIM, Orphanet, MONDO), delimited |
| `phenotype_list` | TEXT | Human-readable condition names, **`\|`-delimited** when a variant has several |
| `origin` | TEXT | `germline`, `somatic`, `de novo`, `inherited`, ... |
| `chromosome` | TEXT | `1`–`22`, `X`, `Y`, `MT` — **stored as text**, so numeric ordering needs a cast |
| `start_pos` / `stop_pos` | INTEGER | 1-based genomic coordinates |
| `ref_allele` / `alt_allele` | TEXT | VCF-style alleles; NULL for variants without a simple representation |
| `review_status` | TEXT | ACMG-style confidence, 9 distinct values — see below |
| `num_submitters` | INTEGER | How many labs submitted this assertion |
| `last_evaluated` | TEXT | Date string, often `MMM DD, YYYY`; frequently NULL |

There is no `assembly` column: the build filters to GRCh38, so storing it would
just repeat one literal 4.5 million times.

### Indexes

Single column: `gene_symbol`, `clinical_significance`, `rsid`, `variation_id`.
Composite: `(chromosome, start_pos)`, `(gene_symbol, clinical_significance)`,
`(review_status, clinical_significance)`.

The two composite indexes on `clinical_significance` exist because per-gene and
per-review-tier breakdowns of classification are the most common question shape
here. Grouping by `gene_symbol` **and** aggregating over `clinical_significance`
stays inside a covering index and returns in well under a second across all
4.5M rows. Pulling any *other* column into the same aggregate leaves the index
and forces a lookup per row, which is dramatically slower — measured at over
300 seconds versus 0.6. Prefer two focused queries over one wide one.

## Critical Query Guidance

### 1. `clinical_significance` is free text, not an enum

107 distinct submitter-authored values, including compound forms. Actual counts
in the current build:

| Value | Rows |
|---|---:|
| Uncertain significance | 2,331,127 |
| Likely benign | 1,093,923 |
| *(NULL)* | 245,063 |
| Benign | 211,440 |
| Pathogenic | 192,889 |
| Conflicting classifications of pathogenicity | 165,637 |
| Likely pathogenic | 119,909 |
| Benign/Likely benign | 67,035 |

Two things follow. **VUS is the single largest class at ~52%** — any "how many
variants" question needs to say whether VUS are included. And **`= 'Pathogenic'`
alone silently drops `Pathogenic/Likely pathogenic`** and the other compound
labels. Prefer:

```sql
-- The pre-computed flag — most reliable
WHERE clin_sig_simple = 1

-- Or pattern match, excluding the conflicting bucket
WHERE clinical_significance LIKE '%athogenic%'
  AND clinical_significance NOT LIKE '%Conflicting%'
```

`LIKE '%athogenic%'` matches "Conflicting classifications of pathogenicity",
which is why that exclusion is there.

### 2. Conditions are packed into one column, not separate rows

`phenotype_list` holds every associated condition for a variant, `|`-delimited:

```
Hereditary spastic paraplegia 48|Macular dystrophy with or without extraocular features|not provided
```

So there is **one row per variant**, not one per variant/condition pair. To find
variants for a condition, match with `LIKE`; to count conditions, split the
string in the coder agent rather than in SQL. `not provided` is a common
placeholder entry inside these lists.

### 3. `chromosome` sorts lexically

`'10' < '2'` as text. Cast when ordering:

```sql
ORDER BY CASE chromosome
           WHEN 'X' THEN 23 WHEN 'Y' THEN 24 WHEN 'MT' THEN 25
           ELSE CAST(chromosome AS INTEGER)
         END
```

### 4. `review_status` encodes confidence

9 distinct values. Actual counts, ordered weakest to strongest:

| Value | Rows |
|---|---:|
| no assertion criteria provided | 116,362 |
| no classification provided | 7,182 |
| no classification for the single variant | 683 |
| criteria provided, single submitter | 3,255,105 |
| criteria provided, conflicting classifications | 165,295 |
| criteria provided, multiple submitters, no conflicts | 668,821 |
| reviewed by expert panel | 22,132 |
| *(NULL)* | 245,063 |

Note the shape: **73% of the archive is single-submitter** and only 22k variants
have expert-panel review. Any claim about classification confidence should say
which tier it refers to. Star ratings in the ClinVar UI map to these labels;
there is no numeric star column here.

## Query Patterns

**Clinical significance distribution**
```sql
SELECT clinical_significance, COUNT(*) AS n
FROM variants
GROUP BY clinical_significance
ORDER BY n DESC
LIMIT 20;
```

**Pathogenic variants in a gene, by type**
```sql
SELECT variant_type, COUNT(*) AS n
FROM variants
WHERE gene_symbol = 'BRCA1' AND clin_sig_simple = 1
GROUP BY variant_type
ORDER BY n DESC;
```

**VUS rate per gene (top genes only)**
```sql
SELECT gene_symbol,
       COUNT(*) AS total,
       SUM(clinical_significance = 'Uncertain significance') AS vus,
       ROUND(100.0 * SUM(clinical_significance = 'Uncertain significance')
             / COUNT(*), 1) AS vus_pct
FROM variants
WHERE gene_symbol IS NOT NULL
GROUP BY gene_symbol
HAVING total >= 100
ORDER BY total DESC
LIMIT 20;
```

**Positional density in 10 Mb bins**
```sql
SELECT chromosome,
       start_pos / 10000000 AS bin_10mb,
       COUNT(*) AS n
FROM variants
WHERE clin_sig_simple = 1 AND start_pos IS NOT NULL
GROUP BY chromosome, bin_10mb
ORDER BY n DESC;
```

**Condition search** — `phenotype_list` is delimited text, so match with `LIKE`:
```sql
SELECT gene_symbol, COUNT(*) AS n
FROM variants
WHERE phenotype_list LIKE '%Lynch syndrome%'
GROUP BY gene_symbol
ORDER BY n DESC;
```

## Domain Context

ClinVar underpins:
- Clinical variant interpretation and diagnostic reporting
- ACMG/AMP classification workflows
- VUS reclassification tracking over time
- Benchmarking of variant-effect prediction tools
- Gene panel design for hereditary disease testing

Useful caveats when interpreting results: submission is voluntary and uneven, so gene-level counts reflect *testing volume* as much as biology. Well-studied genes (BRCA1/2, CFTR, mismatch-repair genes) dominate. A high VUS fraction usually signals a gene that is sequenced often but understood poorly.
