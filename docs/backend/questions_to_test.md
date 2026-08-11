Here are example questions for manual regression testing. They cover different
aspects of the system and should exercise the full agent chain: SQL querying,
computational analysis, visualization, and multi-step synthesis.

---

# ClinVar Questions

> **Setup:** `DB_REGISTRY_ACTIVE_DATABASE=clinvar` (this is the default).

## Basic Queries (Standard Mode)

### 1. **Clinical Significance Overview**
```
How many variants are in ClinVar for each clinical significance category?
```
**Expected behavior:**
- Single `GROUP BY` on the clinical significance column
- Returns Pathogenic / Likely pathogenic / VUS / Likely benign / Benign counts

### 2. **Gene Lookup**
```
List all pathogenic variants in BRCA1 along with their molecular consequence.
```
**Expected behavior:**
- Filters on gene symbol and clinical significance
- Does not silently truncate — states the row count it returned

### 3. **Review Status Distribution**
```
What is the distribution of review status (star rating) across ClinVar submissions?
```
**Expected behavior:**
- Aggregation over the review-status column
- Notes that higher star counts mean stronger supporting evidence

### 4. **Variant Type Breakdown**
```
Break down ClinVar variants by variant type. Which types are most often
classified as pathogenic?
```
**Expected behavior:**
- Two-dimensional aggregation (type × significance)
- Reports proportions, not just raw counts

---

## Analytical Queries (Standard / Deep Mode)

### 5. **Gene Burden Comparison**
```
Which 20 genes carry the most pathogenic variants in ClinVar? Normalize by the
total number of submitted variants per gene so long genes don't dominate.
```
**Expected behavior:**
- sql_agent pulls per-gene counts
- coder computes the normalized rate and ranks
- Flags genes with small denominators as unstable

### 6. **VUS Reclassification Pressure**
```
Which genes have the highest ratio of variants of uncertain significance to
total submissions? What does that suggest about interpretation difficulty?
```
**Expected behavior:**
- Ratio computed in SQL or in coder
- Answer distinguishes "hard to interpret" from "rarely submitted"

### 7. **Multi-Table Reasoning**
```
For the genes with the most pathogenic variants, what conditions are they
associated with, and do any conditions recur across multiple genes?
```
**Expected behavior:**
- Join or two-step query across variant and condition columns
- Identifies shared phenotypes

---

# GWAS Catalog Questions

> **Setup:** Set `DB_REGISTRY_ACTIVE_DATABASE=gwas` before testing.

## Basic Queries (Standard Mode)

### 8. **Trait Coverage**
```
How many associations does the GWAS Catalog contain, and what are the 20 most
studied traits by association count?
```
**Expected behavior:**
- DuckDB scan over the Parquet files
- Returns trait names with counts

### 9. **Genome-Wide Significance**
```
How many associations reach genome-wide significance (p < 5e-8)?
What fraction of the catalog is that?
```
**Expected behavior:**
- Filter on the p-value column, report both the count and the share

### 10. **Effect Size Distribution**
```
What is the distribution of odds ratios / beta values for associations with
p < 5e-8?
```
**Expected behavior:**
- coder computes quantiles, notes the mixed OR/beta semantics of the column

### 11. **Per-Chromosome Density**
```
Which chromosomes carry the most significant associations, normalized by
chromosome length?
```
**Expected behavior:**
- sql_agent aggregates by chromosome
- coder applies the length normalization and explains the reference build used

---

## Analytical Queries (Standard / Deep Mode)

### 12. **Pleiotropy Candidates**
```
Find variants associated with more than five distinct traits at genome-wide
significance. Which are the strongest pleiotropy candidates?
```
**Expected behavior:**
- Group by variant, count distinct traits
- Answer caveats that catalog-level trait labels are not curated ontologies

### 13. **Publication Traceability**
```
For the top 10 associations by significance, report the PubMed ID of the study
that reported them.
```
**Expected behavior:**
- Carries `PUBMEDID` through into the result so each row stays traceable

### 14. **Study Size vs Effect Size**
```
Is there a relationship between reported sample size and effect size among
significant associations? Quantify it.
```
**Expected behavior:**
- coder runs a correlation and reports the coefficient with an n
- Mentions winner's-curse as the expected explanation for an inverse trend

---

# Ensembl Questions

> **Setup:** Set `DB_REGISTRY_ENSEMBL_ENABLED=true` and
> `DB_REGISTRY_ACTIVE_DATABASE=ensembl`. Requires outbound MySQL access to the
> public mirror, which many networks block.

### 15. **Gene Annotation Lookup**
```
What are the genomic coordinates, biotype, and transcript count for TP53?
```
**Expected behavior:**
- Joins `gene`, `transcript`, and the xref/name tables
- Stays inside the allowed-tables whitelist

### 16. **Biotype Census**
```
How many genes of each biotype are annotated in the current human core schema?
```
**Expected behavior:**
- Aggregation over `gene.biotype`
- Notes the assembly / schema version it queried

---

# Visualization Requests

### 17. **Manhattan Plot**
```
Draw a Manhattan plot of GWAS associations for type 2 diabetes.
```
**Expected behavior:**
- sql_agent pulls chromosome, position, and p-value
- coder renders with `qqman` (R) or matplotlib and returns an artifact

### 18. **Significance Histogram**
```
Plot the distribution of -log10(p) for all GWAS associations.
```

### 19. **Clinical Significance Bar Chart**
```
Make a bar chart of ClinVar variant counts by clinical significance.
```

### 20. **Gene Burden Scatter**
```
Scatter plot of pathogenic variant count versus total submission count per
gene, log-scaled on both axes, with the top 10 genes labelled.
```

---

# Edge Cases

### 21. **Empty Result**
```
List pathogenic variants in a gene called ZZZZZ1.
```
**Expected behavior:**
- Returns an explicit "no rows matched", does not invent results

### 22. **Ambiguous Reference**
```
Show me variants in the p53 gene.
```
**Expected behavior:**
- Resolves the common name to the `TP53` symbol, or asks which it meant

### 23. **Large Result Guard**
```
Show me every variant in ClinVar.
```
**Expected behavior:**
- Refuses to dump the full table; offers an aggregate or an S3 export instead

### 24. **Cross-Database Question**
```
Is BRCA1 associated with any traits in the GWAS Catalog, and what does ClinVar
say about its pathogenic variants?
```
**Expected behavior:**
- Recognizes only one profile is active at a time and says so, rather than
  silently answering half the question

---

## Testing Tips

1. Start with the basic queries to verify the connection and schema context
2. Use `/mode deep` in the CLI, or set `research_mode: "deep_research"` in API
   requests, to exercise multi-step planning
3. Watch for:
   - Multiple agent calls (sql_agent → coder)
   - Follow-up tasks discovered mid-run rather than planned up front
   - Comprehensive synthesis in the final response
4. Compare with standard mode to see the difference in depth

## Quick CLI Test Commands

```bash
# Start the CLI in deep research mode
python cli.py --research-mode deep_research

# Or switch modes during a session
/mode deep

# Verify which database the agent thinks it is connected to
# Ask: "What database am I connected to?"
```
