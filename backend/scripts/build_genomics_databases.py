#!/usr/bin/env python3
"""Build the local genomics databases from public sources.

Produces two artifacts under ``backend/databases/``:

  clinvar/clinvar.db          SQLite — ClinVar variant/condition assertions
  gwas/*.parquet              Parquet — GWAS Catalog associations + studies

Both sources are public and redistributable:

  ClinVar       — NCBI, public domain (US Government work)
                  https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/
  GWAS Catalog  — EMBL-EBI, CC BY 4.0
                  https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/

Raw downloads live in ``backend/databases/_raw/`` and are gitignored. Run
``--download`` to fetch them, or place them there yourself first.

Sizes to expect. ClinVar's variant_summary ships one row per assembly; we
keep GRCh38 only, which halves 9.0M source rows to ~4.5M and lands the SQLite
file at roughly **1.5 GB** with indexes. That is comfortable for local use but
too large to commit, so ``backend/databases/clinvar/*.db`` is gitignored and
every checkout rebuilds it from source. Pass ``--clinvar-full`` to keep all
assemblies (roughly double). The GWAS Parquet files come to a few hundred MB.

Usage:
    uv run python scripts/build_genomics_databases.py --download
    uv run python scripts/build_genomics_databases.py            # build only
    uv run python scripts/build_genomics_databases.py --clinvar-full
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

# backend/scripts/build_genomics_databases.py -> backend/
BACKEND_ROOT = Path(__file__).resolve().parent.parent
DB_ROOT = BACKEND_ROOT / "databases"
RAW_DIR = DB_ROOT / "_raw"

CLINVAR_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
)
GWAS_BASE = "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest"
GWAS_ASSOC_ZIP = "gwas-catalog-associations_ontology-annotated-full.zip"
GWAS_STUDIES_TSV = "gwas-catalog-studies.tsv"

# Ensembl ships one GTF per release and the release number is baked into the
# filename, so there is no stable "current" URL to build against. Pinning also
# keeps the row counts quoted in the schema description honest — bump this and
# rebuild rather than silently tracking upstream.
ENSEMBL_RELEASE = "116"
ENSEMBL_ASSEMBLY = "GRCh38"


def _ensembl_urls(release: str) -> tuple[str, str]:
    """Return (gtf_url, fasta_index_url) for an Ensembl release.

    The FASTA index is only read for its sequence lengths, which the GTF does
    not carry — without it, "genes per megabase" is unanswerable.
    """
    base = f"https://ftp.ensembl.org/pub/release-{release}"
    gtf = (
        f"{base}/gtf/homo_sapiens/"
        f"Homo_sapiens.{ENSEMBL_ASSEMBLY}.{release}.gtf.gz"
    )
    fai = (
        f"{base}/fasta/homo_sapiens/dna_index/"
        f"Homo_sapiens.{ENSEMBL_ASSEMBLY}.dna.toplevel.fa.gz.fai"
    )
    return gtf, fai


def _ensembl_raw_paths(release: str) -> tuple[Path, Path]:
    """Local names for the Ensembl sources. Release-tagged so a bump refetches."""
    return (
        RAW_DIR / f"Homo_sapiens.{ENSEMBL_ASSEMBLY}.{release}.gtf.gz",
        RAW_DIR / f"Homo_sapiens.{ENSEMBL_ASSEMBLY}.{release}.dna.toplevel.fa.gz.fai",
    )

# Columns kept from variant_summary.txt. The full file has 39; these are the
# ones the schema description exposes and the SQL agent can reason about.
CLINVAR_COLUMNS = [
    "VariationID",
    "Type",
    "Name",
    "GeneID",
    "GeneSymbol",
    "ClinicalSignificance",
    "ClinSigSimple",
    "RS# (dbSNP)",
    "PhenotypeIDS",
    "PhenotypeList",
    "Origin",
    "Assembly",   # read for filtering only; not stored
    "Chromosome",
    "Start",
    "Stop",
    "ReferenceAlleleVCF",
    "AlternateAlleleVCF",
    "ReviewStatus",
    "NumberSubmitters",
    "LastEvaluated",
]

# (source column, sqlite column, sqlite type)
CLINVAR_SCHEMA = [
    ("VariationID", "variation_id", "INTEGER"),
    ("Type", "variant_type", "TEXT"),
    ("Name", "name", "TEXT"),
    ("GeneID", "gene_id", "INTEGER"),
    ("GeneSymbol", "gene_symbol", "TEXT"),
    ("ClinicalSignificance", "clinical_significance", "TEXT"),
    ("ClinSigSimple", "clin_sig_simple", "INTEGER"),
    ("RS# (dbSNP)", "rsid", "TEXT"),
    ("PhenotypeIDS", "phenotype_ids", "TEXT"),
    ("PhenotypeList", "phenotype_list", "TEXT"),
    ("Origin", "origin", "TEXT"),
    # Assembly is deliberately absent: after the GRCh38 filter every row would
    # carry the same literal, costing ~27 MB to store a constant.
    ("Chromosome", "chromosome", "TEXT"),
    ("Start", "start_pos", "INTEGER"),
    ("Stop", "stop_pos", "INTEGER"),
    ("ReferenceAlleleVCF", "ref_allele", "TEXT"),
    ("AlternateAlleleVCF", "alt_allele", "TEXT"),
    ("ReviewStatus", "review_status", "TEXT"),
    ("NumberSubmitters", "num_submitters", "INTEGER"),
    ("LastEvaluated", "last_evaluated", "TEXT"),
]


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def _expected_total(resp: Any, already_have: int) -> int | None:
    """Total size of the resource, or None if the server did not say.

    For a 206 the authoritative value is the ``/total`` suffix of
    Content-Range; Content-Length on a partial response only describes the
    remaining slice.
    """
    cr = resp.headers.get("Content-Range")
    if cr and "/" in cr:
        tail = cr.rsplit("/", 1)[1].strip()
        if tail.isdigit():
            return int(tail)
    cl = resp.headers.get("Content-Length")
    if cl and cl.isdigit():
        return already_have + int(cl) if resp.status == 206 else int(cl)
    return None


def _fetch(url: str, dest: Path, attempts: int = 6) -> None:
    """Download `url` to `dest`, resuming across attempts.

    The EBI mirror is prone to stalling mid-transfer and to closing the
    connection early without an error, so this does two things beyond a
    plain urlretrieve:

    - a read timeout on the socket, because urllib has no default and a
      stalled connection otherwise blocks forever;
    - a size check against Content-Length / Content-Range before promoting
      the ``.part`` file. A truncated transfer that ends cleanly looks like
      success to ``copyfileobj``, and silently shipping a half a TSV is far
      worse than failing loudly.
    """
    if dest.exists() and dest.stat().st_size > 0:
        log(f"  exists, skipping: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return

    tmp = dest.with_suffix(dest.suffix + ".part")
    log(f"  downloading {url}")
    total: int | None = None

    for attempt in range(1, attempts + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        if total is not None and have >= total:
            break

        req = urllib.request.Request(url)
        if have:
            req.add_header("Range", f"bytes={have}-")

        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                # 206 => server honoured the range; 200 => it ignored it and
                # is resending everything, so restart rather than appending a
                # duplicate onto what we already have.
                resuming = bool(have) and r.status == 206
                if not resuming:
                    have = 0
                total = _expected_total(r, have) or total
                with tmp.open("ab" if resuming else "wb") as f:
                    shutil.copyfileobj(r, f, length=1 << 20)
        except Exception as e:  # noqa: BLE001 — network flakiness is expected
            # 416 means the Range start is at or past EOF: the .part file
            # already holds the whole resource. This is what a run that
            # downloaded everything but died before the rename leaves behind.
            # Confirm with a HEAD rather than trusting the local size, then
            # fall through to the rename.
            if isinstance(e, urllib.error.HTTPError) and e.code == 416 and have:
                try:
                    head = urllib.request.Request(url, method="HEAD")
                    with urllib.request.urlopen(head, timeout=60) as h:
                        total = _expected_total(h, 0) or total
                except Exception:  # noqa: BLE001 — fall back to the retry path
                    total = total
                if total is not None and have == total:
                    log(f"  already complete on disk ({have:,} bytes)")
                    break

            got = tmp.stat().st_size if tmp.exists() else 0
            if attempt == attempts:
                raise SystemExit(
                    f"  failed after {attempts} attempts ({got / 1e6:.1f} MB "
                    f"downloaded): {e}\n"
                    f"  The partial file is kept at {tmp}; rerun to resume."
                ) from e
            log(f"  attempt {attempt} failed at {got / 1e6:.1f} MB ({e}); resuming")
            continue

        got = tmp.stat().st_size
        if total is None or got >= total:
            break
        if attempt == attempts:
            raise SystemExit(
                f"  incomplete after {attempts} attempts: got {got:,} of "
                f"{total:,} bytes.\n"
                f"  The partial file is kept at {tmp}; rerun to resume."
            )
        log(f"  short read: {got:,} of {total:,} bytes; resuming")

    got = tmp.stat().st_size
    if total is not None and got != total:
        raise SystemExit(f"  size mismatch for {dest.name}: {got:,} != {total:,}")

    tmp.rename(dest)
    log(f"  saved {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")


def download_sources(ensembl_release: str = ENSEMBL_RELEASE) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    log("Downloading public source files...")
    _fetch(CLINVAR_URL, RAW_DIR / "clinvar_variant_summary.txt.gz")
    _fetch(f"{GWAS_BASE}/{GWAS_ASSOC_ZIP}", RAW_DIR / "gwas-assoc.zip")
    _fetch(f"{GWAS_BASE}/{GWAS_STUDIES_TSV}", RAW_DIR / GWAS_STUDIES_TSV)
    gtf_url, fai_url = _ensembl_urls(ensembl_release)
    gtf_dest, fai_dest = _ensembl_raw_paths(ensembl_release)
    _fetch(gtf_url, gtf_dest)
    _fetch(fai_url, fai_dest)


# ---------------------------------------------------------------------------
# ClinVar -> SQLite
# ---------------------------------------------------------------------------


def build_clinvar(full: bool = False) -> Path:
    src = RAW_DIR / "clinvar_variant_summary.txt.gz"
    if not src.exists():
        sys.exit(f"missing {src} — run with --download first")

    out_dir = DB_ROOT / "clinvar"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "clinvar.db"
    if out.exists():
        out.unlink()

    log(f"Building {out.relative_to(BACKEND_ROOT)} (full={full})")

    conn = sqlite3.connect(out)
    cur = conn.cursor()
    # Bulk-load pragmas; the file is rebuilt from scratch each run so
    # durability during the load buys us nothing.
    cur.execute("PRAGMA journal_mode = OFF")
    cur.execute("PRAGMA synchronous = OFF")

    cols_ddl = ",\n  ".join(f"{c} {t}" for _, c, t in CLINVAR_SCHEMA)
    cur.execute(f"CREATE TABLE variants (\n  {cols_ddl}\n)")

    insert_sql = "INSERT INTO variants VALUES ({})".format(
        ",".join("?" * len(CLINVAR_SCHEMA))
    )

    int_cols = {c for _, c, t in CLINVAR_SCHEMA if t == "INTEGER"}
    col_out_names = [c for _, c, _ in CLINVAR_SCHEMA]

    read = written = 0
    batch: list[tuple] = []

    with gzip.open(src, "rt", encoding="utf-8", errors="replace") as fh:
        header = fh.readline().lstrip("#").rstrip("\n").split("\t")
        try:
            idx = [header.index(sc) for sc, _, _ in CLINVAR_SCHEMA]
        except ValueError as e:
            sys.exit(f"ClinVar header changed upstream: {e}\nheader={header}")
        assembly_i = header.index("Assembly")

        for line in fh:
            read += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            # GRCh38 only unless --clinvar-full. ClinVar ships one row per
            # assembly, so this halves the row count without losing variants.
            if not full and parts[assembly_i] != "GRCh38":
                continue

            row = []
            for out_name, i in zip(col_out_names, idx):
                v = parts[i].strip()
                if v in ("", "-", "na", "NA", "-1"):
                    row.append(None)
                elif out_name in int_cols:
                    try:
                        row.append(int(v))
                    except ValueError:
                        row.append(None)
                else:
                    row.append(v)
            batch.append(tuple(row))
            written += 1

            if len(batch) >= 50_000:
                cur.executemany(insert_sql, batch)
                batch.clear()
                if written % 500_000 == 0:
                    log(f"    {written:,} rows...")

    if batch:
        cur.executemany(insert_sql, batch)

    log(f"  read {read:,} rows, wrote {written:,}")

    log("  creating indexes")
    for stmt in (
        "CREATE INDEX idx_variants_gene ON variants(gene_symbol)",
        "CREATE INDEX idx_variants_sig ON variants(clinical_significance)",
        "CREATE INDEX idx_variants_pos ON variants(chromosome, start_pos)",
        "CREATE INDEX idx_variants_rsid ON variants(rsid)",
        "CREATE INDEX idx_variants_varid ON variants(variation_id)",
        # Composite covering indexes. "count variants per gene, and how many of
        # them are VUS" is the single most common shape the SQL agent writes,
        # and with only the single-column gene index it degrades to 4.5M row
        # lookups — measured at >300s versus 0.6s once covered. Same reasoning
        # for the review-status/classification cross-tab.
        "CREATE INDEX idx_variants_gene_sig ON variants(gene_symbol, clinical_significance)",
        "CREATE INDEX idx_variants_review_sig ON variants(review_status, clinical_significance)",
    ):
        cur.execute(stmt)

    conn.commit()
    cur.execute("VACUUM")
    # Without stats the planner sometimes picks the narrower single-column
    # index over the covering one.
    cur.execute("ANALYZE")
    conn.commit()
    conn.close()

    log(f"  done: {out.stat().st_size / 1e6:.1f} MB")
    return out


# ---------------------------------------------------------------------------
# GWAS Catalog -> Parquet
# ---------------------------------------------------------------------------


def build_gwas() -> Path:
    try:
        import duckdb
    except ImportError:
        sys.exit("duckdb not installed — run `uv sync` in backend/")

    out_dir = DB_ROOT / "gwas"
    out_dir.mkdir(parents=True, exist_ok=True)

    assoc_zip = RAW_DIR / "gwas-assoc.zip"
    studies_tsv = RAW_DIR / GWAS_STUDIES_TSV
    if not assoc_zip.exists() or not studies_tsv.exists():
        sys.exit("missing GWAS source files — run with --download first")

    # The zip holds a single TSV whose name carries the release version.
    with zipfile.ZipFile(assoc_zip) as z:
        names = [n for n in z.namelist() if n.endswith((".tsv", ".txt"))]
        if not names:
            sys.exit(f"no TSV inside {assoc_zip.name}: {z.namelist()}")
        assoc_name = names[0]
        log(f"Extracting {assoc_name}")
        z.extract(assoc_name, RAW_DIR)
    assoc_tsv = RAW_DIR / assoc_name

    con = duckdb.connect()
    # GWAS Catalog TSVs carry unquoted free text (study titles with quotes,
    # embedded commas). all_varchar + quote='' keeps the sniffer from
    # mangling rows; typing happens in the schema description instead.
    read_opts = "delim='\\t', header=true, quote='', all_varchar=true, ignore_errors=true"

    log("Building gwas/associations.parquet")
    con.execute(
        f"COPY (SELECT * FROM read_csv('{assoc_tsv}', {read_opts})) "
        f"TO '{out_dir / 'associations.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    log("Building gwas/studies.parquet")
    con.execute(
        f"COPY (SELECT * FROM read_csv('{studies_tsv}', {read_opts})) "
        f"TO '{out_dir / 'studies.parquet'}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )

    for f in sorted(out_dir.glob("*.parquet")):
        n = con.execute(f"SELECT count(*) FROM '{f}'").fetchone()[0]
        log(f"  {f.name}: {n:,} rows, {f.stat().st_size / 1e6:.1f} MB")

    con.close()
    return out_dir


# ---------------------------------------------------------------------------
# Ensembl GTF -> Parquet
# ---------------------------------------------------------------------------

# Everything else in GRCh38 is an unplaced scaffold, patch or alt haplotype.
# Genes on those are kept — dropping them would make COUNT(*) disagree with
# Ensembl's published gene count — but flagged so per-chromosome queries can
# exclude them.
PRIMARY_CHROMOSOMES = (
    *(str(i) for i in range(1, 23)),
    "X",
    "Y",
    "MT",
)
_PRIMARY_SQL = ", ".join(f"'{c}'" for c in PRIMARY_CHROMOSOMES)


def build_ensembl(
    gtf_path: Path | None = None,
    fai_path: Path | None = None,
    out_dir: Path | None = None,
    scratch_path: Path | None = None,
    release: str = ENSEMBL_RELEASE,
) -> Path:
    """Parse an Ensembl GTF into four Parquet tables.

    Unlike the other builders this one takes explicit paths so it can be
    exercised against a synthetic GTF in tests. All default to the usual
    locations.

    Deliberate divergences from ``build_gwas``:

    * Real integer types instead of ``all_varchar``. The GWAS TSVs mix free
      text into numeric fields; a GTF is machine-generated and regular, so the
      agent never needs TRY_CAST and range predicates can prune row groups.
    * CDS and UTR records are folded into derived transcript columns rather
      than becoming tables. Per-exon coding rows make "how long is the CDS" a
      GROUP BY that is easy to get silently wrong.
    """
    try:
        import duckdb
    except ImportError:
        sys.exit("duckdb not installed — run `uv sync` in backend/")

    default_gtf, default_fai = _ensembl_raw_paths(release)
    gtf_path = gtf_path or default_gtf
    fai_path = fai_path or default_fai
    out_dir = out_dir or (DB_ROOT / "ensembl")
    scratch_path = scratch_path or (RAW_DIR / f"ensembl_gtf_features_{release}.parquet")

    for src in (gtf_path, fai_path):
        if not src.exists():
            sys.exit(f"missing {src} — run with --download first")

    out_dir.mkdir(parents=True, exist_ok=True)
    scratch_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    # Stage 0 — the only pass over the gzipped GTF. Decompression is
    # single-threaded, so the later stages read this columnar scratch file
    # instead of re-scanning the source four times.
    log(f"Parsing Ensembl {release} GTF (this is the slow part)...")
    con.execute(
        f"""
        COPY (
          SELECT
            seqname AS chromosome,
            source,
            feature,
            CAST(start AS INTEGER) AS start,
            CAST("end" AS INTEGER) AS "end",
            strand,
            regexp_extract(attributes, 'gene_id "([^"]*)"', 1) AS gene_id,
            TRY_CAST(regexp_extract(attributes, 'gene_version "([^"]*)"', 1)
                     AS INTEGER) AS gene_version,
            nullif(regexp_extract(attributes, 'gene_name "([^"]*)"', 1), '')
              AS gene_name,
            regexp_extract(attributes, 'gene_biotype "([^"]*)"', 1) AS gene_biotype,
            nullif(regexp_extract(attributes, 'transcript_id "([^"]*)"', 1), '')
              AS transcript_id,
            nullif(regexp_extract(attributes, 'transcript_name "([^"]*)"', 1), '')
              AS transcript_name,
            nullif(regexp_extract(attributes, 'transcript_biotype "([^"]*)"', 1), '')
              AS transcript_biotype,
            nullif(regexp_extract(attributes, 'exon_id "([^"]*)"', 1), '') AS exon_id,
            TRY_CAST(regexp_extract(attributes, 'exon_number "([^"]*)"', 1)
                     AS INTEGER) AS exon_number,
            nullif(regexp_extract(attributes, 'protein_id "([^"]*)"', 1), '')
              AS protein_id,
            nullif(regexp_extract(attributes, 'ccds_id "([^"]*)"', 1), '') AS ccds_id,
            -- TSL is sometimes '1 (assigned to previous version 3)'; the
            -- character class stops at the space so only the level survives.
            nullif(regexp_extract(
              attributes, 'transcript_support_level "([^" (]*)', 1), '')
              AS transcript_support_level,
            -- `tag` repeats within one attribute string, so regexp_extract
            -- would only ever see the first one. Substring match instead.
            attributes LIKE '%tag "Ensembl_canonical"%' AS is_canonical,
            attributes LIKE '%tag "MANE_Select"%'       AS is_mane_select,
            attributes LIKE '%tag "gencode_basic"%'     AS is_gencode_basic
          FROM read_csv(
            '{gtf_path}',
            delim='\t', header=false, comment='#',
            -- The attributes column is full of literal double quotes; without
            -- quote='' the reader treats them as field quoting and mangles it.
            quote='',
            -- Required explicitly: supplying `columns` does NOT disable the
            -- sniffer, and sniffing a headerless 9-column file with quoting
            -- turned off fails outright.
            auto_detect=false,
            columns={{
              'seqname':'VARCHAR','source':'VARCHAR','feature':'VARCHAR',
              'start':'BIGINT','end':'BIGINT','score':'VARCHAR',
              'strand':'VARCHAR','frame':'VARCHAR','attributes':'VARCHAR'
            }}
          )
          WHERE feature IN ('gene','transcript','exon','CDS')
        ) TO '{scratch_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    con.execute(f"CREATE OR REPLACE VIEW gtf AS SELECT * FROM '{scratch_path}'")

    exons_out = out_dir / "exons.parquet"
    transcripts_out = out_dir / "transcripts.parquet"
    genes_out = out_dir / "genes.parquet"
    chroms_out = out_dir / "chromosomes.parquet"

    # ORDER BY chromosome, start on every table gives Parquet row groups tight
    # min/max stats, so coordinate-range filters prune instead of full-scanning.
    log("  exons...")
    con.execute(
        f"""
        COPY (
          SELECT exon_id, transcript_id, gene_id, exon_number,
                 chromosome, start, "end",
                 ("end" - start + 1)::INTEGER AS length, strand
          FROM gtf WHERE feature = 'exon'
          ORDER BY chromosome, start
        ) TO '{exons_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    log("  transcripts...")
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE cds_agg AS
        SELECT transcript_id,
               any_value(protein_id)           AS protein_id,
               SUM("end" - start + 1)::INTEGER AS cds_length,
               MIN(start)::INTEGER             AS cds_start,
               MAX("end")::INTEGER             AS cds_end
        FROM gtf WHERE feature = 'CDS' GROUP BY 1
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE exon_agg AS
        SELECT transcript_id,
               COUNT(*)::INTEGER    AS exon_count,
               SUM(length)::INTEGER AS spliced_length
        FROM '{exons_out}' GROUP BY 1
        """
    )
    con.execute(
        f"""
        COPY (
          SELECT t.transcript_id, t.gene_id, t.gene_name, t.transcript_name,
                 t.transcript_biotype, t.chromosome, t.start, t."end", t.strand,
                 (t."end" - t.start + 1)::INTEGER AS genomic_length,
                 e.exon_count, e.spliced_length,
                 c.cds_length, c.cds_start, c.cds_end, c.protein_id,
                 t.transcript_support_level, t.ccds_id,
                 t.is_canonical, t.is_mane_select, t.is_gencode_basic,
                 t.source AS transcript_source,
                 t.chromosome IN ({_PRIMARY_SQL}) AS is_primary_chromosome
          FROM gtf t
          LEFT JOIN exon_agg e USING (transcript_id)
          LEFT JOIN cds_agg  c USING (transcript_id)
          WHERE t.feature = 'transcript'
          ORDER BY t.chromosome, t.start
        ) TO '{transcripts_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    log("  genes...")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE tx_agg AS
        SELECT gene_id,
               COUNT(*)::INTEGER AS transcript_count,
               COUNT(*) FILTER (WHERE transcript_biotype = 'protein_coding')::INTEGER
                 AS coding_transcript_count,
               any_value(transcript_id) FILTER (WHERE is_canonical)
                 AS canonical_transcript_id,
               any_value(transcript_id) FILTER (WHERE is_mane_select)
                 AS mane_select_transcript_id
        FROM '{transcripts_out}' GROUP BY 1
        """
    )
    con.execute(
        f"""
        COPY (
          SELECT g.gene_id, g.gene_version, g.gene_name, g.gene_biotype,
                 g.source AS gene_source,
                 g.chromosome, g.start, g."end", g.strand,
                 (g."end" - g.start + 1)::INTEGER AS genomic_length,
                 COALESCE(a.transcript_count, 0)        AS transcript_count,
                 COALESCE(a.coding_transcript_count, 0) AS coding_transcript_count,
                 a.canonical_transcript_id, a.mane_select_transcript_id,
                 g.chromosome IN ({_PRIMARY_SQL}) AS is_primary_chromosome
          FROM gtf g LEFT JOIN tx_agg a USING (gene_id)
          WHERE g.feature = 'gene'
          ORDER BY g.chromosome, g.start
        ) TO '{genes_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    log("  chromosomes...")
    con.execute(
        f"""
        COPY (
          SELECT f.name AS chromosome, f.length,
                 f.name IN ({_PRIMARY_SQL}) AS is_primary_chromosome
          FROM read_csv(
            '{fai_path}', delim='\t', header=false, null_padding=true,
            columns={{'name':'VARCHAR','length':'BIGINT','offset':'BIGINT',
                     'linebases':'BIGINT','linewidth':'BIGINT'}}
          ) f
          WHERE f.name IN (SELECT DISTINCT chromosome FROM '{genes_out}')
          ORDER BY is_primary_chromosome DESC, f.length DESC
        ) TO '{chroms_out}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    for f in sorted(out_dir.glob("*.parquet")):
        n = con.execute(f"SELECT count(*) FROM '{f}'").fetchone()[0]
        log(f"  {f.name}: {n:,} rows, {f.stat().st_size / 1e6:.1f} MB")
        if n == 0:
            sys.exit(f"{f.name} is empty — the GTF parse produced nothing")

    con.close()
    return out_dir


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--download", action="store_true", help="fetch source files first")
    ap.add_argument(
        "--clinvar-full",
        action="store_true",
        help="keep all assemblies (much larger output)",
    )
    ap.add_argument("--skip-clinvar", action="store_true")
    ap.add_argument("--skip-gwas", action="store_true")
    ap.add_argument("--skip-ensembl", action="store_true")
    ap.add_argument(
        "--ensembl-release",
        default=ENSEMBL_RELEASE,
        help="Ensembl release to build from (default: %(default)s)",
    )
    args = ap.parse_args()

    if args.download:
        download_sources(ensembl_release=args.ensembl_release)
    if not args.skip_clinvar:
        build_clinvar(full=args.clinvar_full)
    if not args.skip_gwas:
        build_gwas()
    if not args.skip_ensembl:
        build_ensembl(release=args.ensembl_release)
    log("\nDone.")


if __name__ == "__main__":
    main()
