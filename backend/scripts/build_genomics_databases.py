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


def download_sources() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    log("Downloading public source files...")
    _fetch(CLINVAR_URL, RAW_DIR / "clinvar_variant_summary.txt.gz")
    _fetch(f"{GWAS_BASE}/{GWAS_ASSOC_ZIP}", RAW_DIR / "gwas-assoc.zip")
    _fetch(f"{GWAS_BASE}/{GWAS_STUDIES_TSV}", RAW_DIR / GWAS_STUDIES_TSV)


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
    args = ap.parse_args()

    if args.download:
        download_sources()
    if not args.skip_clinvar:
        build_clinvar(full=args.clinvar_full)
    if not args.skip_gwas:
        build_gwas()
    log("\nDone.")


if __name__ == "__main__":
    main()
