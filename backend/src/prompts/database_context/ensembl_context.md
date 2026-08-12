# Ensembl Database Context

> **Note:** files in this directory are reference documentation for humans.
> They are not injected into any prompt — `load_database_context()` has no
> callers. What the SQL agent actually receives is
> `backend/databases/ensembl/schema_description.yaml`, via the
> `get_database_schema` tool. Keep the two consistent, but change the YAML when
> you want to change agent behaviour.

## Database Overview

Ensembl GRCh38 gene annotation: genes, their transcript isoforms, exon
structure, and chromosome lengths. Built locally into Parquet from the public
release-116 GTF by `scripts/build_genomics_databases.py` and queried through
DuckDB — nothing is fetched at query time.

This profile previously queried the public MySQL mirror at
`ensembldb.ensembl.org`. It was converted to a local build because that mirror
is unreachable from any network that filters the MySQL wire protocol, and
because the other two profiles already worked this way.

## Key Characteristics

- **Database Type**: DuckDB over Parquet, built locally
- **Primary Focus**: Reference gene annotation
- **SQL Dialect**: **PostgreSQL** (DuckDB implements PostgreSQL syntax)
- **Assembly**: GRCh38, Ensembl release 116
- **Coordinates**: 1-based inclusive, so length is `end - start + 1`

## ⚠️ What This Dataset Does Not Have

A GTF carries structure, not annotation prose or identifier mappings. Compared
with the Ensembl core MySQL schema, these are simply absent:

- **Gene description text** — there is no `description` column
- **Cross-references** to RefSeq, UniProt or EntrezGene — no `xref` /
  `object_xref` / `external_db` equivalent
- **Karyotype bands**

Partial compensation: `genes.gene_name` *is* the HGNC symbol, so symbol lookup
is a plain equality filter rather than the three-table join the core schema
needed, and `transcripts.protein_id` gives the Ensembl protein ID (`ENSP…`).

## Schema Overview

Four tables. All are queryable by bare name.

### `genes` (~78k rows)

`gene_id` (ENSG, unversioned), `gene_version`, `gene_name`, `gene_biotype`,
`gene_source`, `chromosome`, `start`, `end`, `strand`, `genomic_length`,
`transcript_count`, `coding_transcript_count`, `canonical_transcript_id`,
`mane_select_transcript_id`, `is_primary_chromosome`.

### `transcripts` (~280k rows)

`transcript_id`, `gene_id`, `gene_name` (denormalised), `transcript_name`,
`transcript_biotype`, coordinates, `genomic_length`, `exon_count`,
`spliced_length`, `cds_length`, `cds_start`, `cds_end`, `protein_id`,
`transcript_support_level`, `ccds_id`, `is_canonical`, `is_mane_select`,
`is_gencode_basic`.

### `exons` (~1.7M rows)

`exon_id`, `transcript_id`, `gene_id`, `exon_number`, coordinates, `length`,
`strand`.

### `chromosomes` (~200 rows)

`chromosome`, `length`, `is_primary_chromosome`. From the Ensembl FASTA index —
the GTF has no sequence lengths.

## Critical Query Guidance

### 1. `gene_name` is NULL for a large fraction of genes

Novel lncRNAs and pseudogenes carry no HGNC symbol. Filter before grouping:

```sql
WHERE gene_name IS NOT NULL
```

Otherwise a "genes by symbol" summary silently reports a large NULL bucket.

### 2. Scaffolds are included

The table holds unplaced scaffolds, patches and alt haplotypes alongside real
chromosomes — deliberately, so `COUNT(*)` matches Ensembl's published figures.
Anything reported per chromosome needs:

```sql
WHERE is_primary_chromosome
```

### 3. `spliced_length` ≠ `genomic_length`

`genomic_length` spans the locus including introns; `spliced_length` is the sum
of exon lengths, i.e. the mature RNA. "Transcript length" almost always means
the latter. No column is called just `length` on `transcripts`, on purpose.

### 4. `exon_number` is transcription order, not coordinate order

On the minus strand exon 1 has the **highest** coordinates. Roughly half of all
genes are on the minus strand, so this is not an edge case.

```sql
ORDER BY exon_number   -- biological order
ORDER BY start         -- genomic order
```

### 5. Exon rows are per-transcript occurrences

An exon shared by five transcripts appears five times. `COUNT(*)` counts
occurrences; `COUNT(DISTINCT exon_id)` counts exons.

### 6. Counts are precomputed — don't re-derive them

`transcript_count`, `coding_transcript_count`, `canonical_transcript_id` and
`mane_select_transcript_id` are computed at build time. Joining `transcripts`
to recompute them is slower and easy to get wrong.

## Query Patterns

**Gene counts by biotype**

```sql
SELECT gene_biotype, COUNT(*) AS n
FROM genes
WHERE is_primary_chromosome
GROUP BY 1 ORDER BY n DESC LIMIT 15;
```

**Look up a gene by symbol** — one table, no joins

```sql
SELECT gene_id, chromosome, start, "end", strand, gene_biotype,
       transcript_count, mane_select_transcript_id
FROM genes WHERE gene_name = 'TP53';
```

**Exon structure of a gene's canonical transcript**

```sql
SELECT e.exon_number, e.start, e."end", e.length
FROM exons e
JOIN genes g ON g.canonical_transcript_id = e.transcript_id
WHERE g.gene_name = 'BRCA2'
ORDER BY e.exon_number;
```

**Gene density per megabase**

```sql
SELECT g.chromosome,
       COUNT(*) AS genes,
       c.length / 1e6 AS mb,
       COUNT(*) / (c.length / 1e6) AS genes_per_mb
FROM genes g
JOIN chromosomes c USING (chromosome)
WHERE g.is_primary_chromosome AND g.gene_biotype = 'protein_coding'
GROUP BY g.chromosome, c.length
ORDER BY genes_per_mb DESC;
```

**Longest coding transcripts**

```sql
SELECT gene_name, transcript_id, cds_length, spliced_length, exon_count
FROM transcripts
WHERE cds_length IS NOT NULL AND is_mane_select
ORDER BY cds_length DESC LIMIT 20;
```

## Gotchas

- **`gene_id` has no `.N` version suffix.** Users paste `ENSG00000141510.18`;
  strip with `split_part(input, '.', 1)`. The version is in `gene_version`.
- **`strand` is `'+'` / `'-'`**, not the `1` / `-1` of the core MySQL schema.
- **`chromosome` is text**, so `ORDER BY chromosome` puts `'10'` before `'2'`.
- **`cds_length IS NULL` means non-coding.** A protein-coding *gene* still has
  non-coding transcripts (retained intron, NMD).
- **Rebuilding to a newer release** changes row counts quoted in the schema
  description: `--ensembl-release NNN`.

## Domain Context

Typical uses: locating a gene and its coordinates, comparing isoform
complexity across biotypes, examining exon structure, and computing
distributions across the genome.

The natural cross-database move is coordinate or symbol overlap — taking a gene
from here and looking up its ClinVar variants, or its GWAS associations. Only
one profile is active at a time, so that is a two-step conversation rather than
a join.
