# Ensembl Database Context

## Database Overview

The Ensembl human core database holds the reference gene annotation for the human genome: genes, their transcripts, exons, translations, and cross-references to external identifier systems. This profile queries the **public read-only MySQL mirror** at `ensembldb.ensembl.org` — no data is stored locally.

## Key Characteristics

- **Database Type**: MySQL (remote, read-only, anonymous login)
- **Primary Focus**: Reference genome annotation
- **SQL Dialect**: MySQL (use MySQL-compatible syntax — backticks, `LIMIT n`, `GROUP_CONCAT`)
- **Assembly**: GRCh38
- **Latency**: queries cross the public internet and are shared with other users

## ⚠️ Performance Rules — Read First

This is a shared public server, not a local file. Unqualified scans are slow and antisocial.

1. **Always** include a `LIMIT` unless the query is a pure aggregate.
2. Filter on indexed columns: `gene.stable_id`, `gene.biotype`, `seq_region.name`, `xref.display_label`.
3. Avoid `SELECT *` on `exon` or `transcript` without a `WHERE` clause — these are multi-million-row tables.
4. Prefer one targeted query over several exploratory ones.
5. `karyotype` and `meta` are tiny and safe to scan freely.

## Schema Overview

Only these tables are exposed to the SQL agent (whitelisted in the profile):

### Core annotation hierarchy

The model is `gene` → `transcript` → `translation`, with exons attached to transcripts through a link table.

| Table | What it holds | Key columns |
|---|---|---|
| `gene` | One row per gene | `gene_id` (PK), `stable_id` (ENSG…), `biotype`, `seq_region_id`, `seq_region_start`, `seq_region_end`, `seq_region_strand`, `description`, `canonical_transcript_id` |
| `transcript` | One row per transcript | `transcript_id` (PK), `gene_id` (FK), `stable_id` (ENST…), `biotype`, `seq_region_start/end/strand` |
| `translation` | Protein products | `translation_id` (PK), `transcript_id` (FK), `stable_id` (ENSP…), `seq_start`, `seq_end` |
| `exon` | Exon coordinates | `exon_id` (PK), `seq_region_start`, `seq_region_end`, `seq_region_strand`, `phase`, `end_phase` |
| `exon_transcript` | **Link table** exon↔transcript | `exon_id`, `transcript_id`, `rank` (exon order within the transcript) |

### Coordinates

| Table | Purpose |
|---|---|
| `seq_region` | Chromosomes/scaffolds. `seq_region_id` (PK), `name` (`1`, `2`, `X`, `MT`), `length`, `coord_system_id` |
| `coord_system` | Assembly levels. `coord_system_id`, `name` (`chromosome`, `scaffold`), `version` (`GRCh38`), `rank` |
| `assembly` | Maps components to assembled sequence |
| `karyotype` | Cytogenetic bands: `seq_region_id`, `seq_region_start/end`, `band`, `stain` |

**Genomic position always requires joining `seq_region`** — the `gene` table stores only a numeric `seq_region_id`, not a chromosome name.

### Cross-references

Ensembl's xref system is a three-table pattern that trips people up:

| Table | Purpose |
|---|---|
| `xref` | The external identifier itself: `xref_id`, `external_db_id`, `dbprimary_acc`, `display_label`, `description` |
| `object_xref` | Links an xref to a gene/transcript/translation: `xref_id`, `ensembl_id`, `ensembl_object_type` (`Gene`\|`Transcript`\|`Translation`) |
| `external_db` | Names the source: `external_db_id`, `db_name` (`HGNC`, `RefSeq_mRNA`, `Uniprot/SWISSPROT`, `EntrezGene`) |
| `external_synonym` | Alternative names for an xref |

To go from a **gene symbol** to an Ensembl gene you join all three. See the pattern below.

### `meta`

Key–value table describing the database itself. `SELECT * FROM meta WHERE meta_key LIKE 'assembly%'` confirms the assembly version and is a cheap sanity check.

## Query Patterns

**Gene counts by biotype** — safe aggregate, no limit needed
```sql
SELECT biotype, COUNT(*) AS n
FROM gene
GROUP BY biotype
ORDER BY n DESC;
```

**Look up a gene by symbol** — the canonical xref join
```sql
SELECT g.stable_id, g.biotype, sr.name AS chromosome,
       g.seq_region_start, g.seq_region_end, g.seq_region_strand,
       g.description
FROM gene g
JOIN seq_region sr    ON sr.seq_region_id = g.seq_region_id
JOIN object_xref ox   ON ox.ensembl_id = g.gene_id
                     AND ox.ensembl_object_type = 'Gene'
JOIN xref x           ON x.xref_id = ox.xref_id
JOIN external_db ed   ON ed.external_db_id = x.external_db_id
WHERE ed.db_name = 'HGNC' AND x.display_label = 'TP53'
LIMIT 10;
```

**Protein-coding genes per chromosome** — restrict to real chromosomes
```sql
SELECT sr.name AS chromosome, COUNT(*) AS genes, sr.length
FROM gene g
JOIN seq_region sr   ON sr.seq_region_id = g.seq_region_id
JOIN coord_system cs ON cs.coord_system_id = sr.coord_system_id
WHERE g.biotype = 'protein_coding'
  AND cs.name = 'chromosome'
  AND sr.name REGEXP '^([0-9]{1,2}|X|Y|MT)$'
GROUP BY sr.name, sr.length
ORDER BY genes DESC;
```

**Transcripts per gene**
```sql
SELECT g.stable_id, g.biotype, COUNT(t.transcript_id) AS n_transcripts
FROM gene g
JOIN transcript t ON t.gene_id = g.gene_id
WHERE g.biotype = 'protein_coding'
GROUP BY g.gene_id, g.stable_id, g.biotype
ORDER BY n_transcripts DESC
LIMIT 20;
```

**Exon structure of a transcript** — note the `exon_transcript` link and `rank`
```sql
SELECT et.rank,
       e.seq_region_start, e.seq_region_end,
       e.seq_region_end - e.seq_region_start + 1 AS length
FROM transcript t
JOIN exon_transcript et ON et.transcript_id = t.transcript_id
JOIN exon e             ON e.exon_id = et.exon_id
WHERE t.stable_id = 'ENST00000380152'
ORDER BY et.rank;
```

**Canonical transcript of a gene**
```sql
SELECT g.stable_id AS gene, t.stable_id AS canonical_transcript, t.biotype
FROM gene g
JOIN transcript t ON t.transcript_id = g.canonical_transcript_id
WHERE g.stable_id = 'ENSG00000141510';
```

## Gotchas

- **`stable_id` vs internal id**: `gene_id` is a database-internal integer that changes between releases. `stable_id` (`ENSG…`) is the stable public identifier. Join on internal ids, report stable ids.
- **Version suffixes**: `stable_id` in the table has no `.N` version suffix, but users often paste `ENSG00000141510.18`. Strip the suffix before matching.
- **Strand**: `seq_region_strand` is `1` or `-1`, not `+`/`-`.
- **Coordinates are 1-based inclusive**, unlike BED.
- **Patches and haplotypes**: `seq_region` includes alt scaffolds. Filter on `coord_system.name = 'chromosome'` plus a name pattern to keep results on the primary assembly.
- **Database name carries the release** (e.g. `homo_sapiens_core_115_38`). If the connection fails, the mirror may have retired that release — `SHOW DATABASES LIKE 'homo_sapiens_core%'` lists what is available, and `DB_REGISTRY_ENSEMBL_DATABASE` overrides the target.

## Domain Context

Ensembl annotation is the reference layer that other genomics datasets hang off. Typical uses here:
- Resolving gene symbols, Ensembl IDs, RefSeq and UniProt accessions to one another
- Getting exact coordinates to intersect with variant positions from ClinVar
- Comparing transcript complexity across genes
- Checking whether a gene of interest is protein-coding, lncRNA, or a pseudogene

Because ClinVar rows carry `gene_symbol` and GWAS associations carry mapped genes, Ensembl is the natural join partner for cross-database questions — though the SQL agent can only query one profile at a time, so such analyses need the coder agent to combine exported results.
