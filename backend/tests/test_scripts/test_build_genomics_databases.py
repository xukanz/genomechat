"""Tests for the Ensembl GTF parser in scripts/build_genomics_databases.py.

The GTF parse is the one part of the build where a wrong answer is plausible
*and* silent: attribute extraction is regex-driven, several fields are
legitimately absent, and coordinate/ordering conventions are easy to invert.
A synthetic GTF pins the cases that would otherwise only surface as a
confidently wrong answer from the agent months later.

The fixture deliberately contains:
  - a ``#!`` header line
  - a gene with NO ``gene_name`` (novel lncRNAs carry no HGNC symbol)
  - repeated ``tag`` attributes, including Ensembl_canonical and MANE_Select
  - a transcript_support_level of the "1 (assigned to previous version 3)" form
  - a MINUS-strand transcript whose exon_number order is the reverse of
    coordinate order
  - CDS records spanning two exons
  - a gene on an unplaced scaffold
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

GTF_LINES = [
    "#!genome-build GRCh38.p14",
    # Gene with no gene_name at all.
    "1\thavana\tgene\t1000\t2000\t.\t+\t.\t"
    'gene_id "ENSG0001"; gene_version "1"; gene_source "havana"; '
    'gene_biotype "lncRNA";',
    "1\thavana\ttranscript\t1000\t2000\t.\t+\t.\t"
    'gene_id "ENSG0001"; transcript_id "ENST0001"; gene_biotype "lncRNA"; '
    'transcript_biotype "lncRNA"; tag "gencode_basic";',
    "1\thavana\texon\t1000\t1100\t.\t+\t.\t"
    'gene_id "ENSG0001"; transcript_id "ENST0001"; exon_number "1"; '
    'exon_id "ENSE0001";',
    # Minus-strand protein-coding gene: 3 exons, CDS over the first two.
    "2\tensembl_havana\tgene\t5000\t9000\t.\t-\t.\t"
    'gene_id "ENSG0002"; gene_version "3"; gene_name "TESTG"; '
    'gene_source "ensembl_havana"; gene_biotype "protein_coding";',
    "2\tensembl_havana\ttranscript\t5000\t9000\t.\t-\t.\t"
    'gene_id "ENSG0002"; transcript_id "ENST0002"; gene_name "TESTG"; '
    'transcript_name "TESTG-201"; transcript_biotype "protein_coding"; '
    'tag "gencode_basic"; tag "Ensembl_canonical"; tag "MANE_Select"; '
    'transcript_support_level "1 (assigned to previous version 3)"; '
    'ccds_id "CCDS1";',
    "2\tensembl_havana\texon\t8801\t9000\t.\t-\t.\t"
    'gene_id "ENSG0002"; transcript_id "ENST0002"; exon_number "1"; '
    'exon_id "ENSE0002";',
    "2\tensembl_havana\texon\t7001\t7100\t.\t-\t.\t"
    'gene_id "ENSG0002"; transcript_id "ENST0002"; exon_number "2"; '
    'exon_id "ENSE0003";',
    "2\tensembl_havana\texon\t5000\t5049\t.\t-\t.\t"
    'gene_id "ENSG0002"; transcript_id "ENST0002"; exon_number "3"; '
    'exon_id "ENSE0004";',
    "2\tensembl_havana\tCDS\t8801\t8900\t.\t-\t0\t"
    'gene_id "ENSG0002"; transcript_id "ENST0002"; exon_number "1"; '
    'protein_id "ENSP0002"; protein_version "1";',
    "2\tensembl_havana\tCDS\t7001\t7050\t.\t-\t1\t"
    'gene_id "ENSG0002"; transcript_id "ENST0002"; exon_number "2"; '
    'protein_id "ENSP0002"; protein_version "1";',
    # Unplaced scaffold.
    "KI270728.1\thavana\tgene\t10\t60\t.\t+\t.\t"
    'gene_id "ENSG0003"; gene_version "1"; gene_name "SCAF1"; '
    'gene_source "havana"; gene_biotype "processed_pseudogene";',
]

FAI_LINES = [
    "1\t248956422\t112\t60\t61",
    "2\t242193529\t1\t60\t61",
    "KI270728.1\t1872759\t2\t60\t61",
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Run the real build against the synthetic GTF once."""
    from build_genomics_databases import build_ensembl

    src = tmp_path_factory.mktemp("ensembl_src")
    out = tmp_path_factory.mktemp("ensembl_out")
    gtf = src / "test.gtf.gz"
    with gzip.open(gtf, "wt") as fh:
        fh.write("\n".join(GTF_LINES) + "\n")
    fai = src / "test.fa.gz.fai"
    fai.write_text("\n".join(FAI_LINES) + "\n")

    build_ensembl(
        gtf_path=gtf,
        fai_path=fai,
        out_dir=out,
        scratch_path=src / "scratch.parquet",
    )
    return out


@pytest.fixture(scope="module")
def con(built):
    import duckdb

    connection = duckdb.connect()
    for name in ("genes", "transcripts", "exons", "chromosomes"):
        connection.execute(f"CREATE VIEW {name} AS SELECT * FROM '{built / f'{name}.parquet'}'")
    yield connection
    connection.close()


def test_all_four_tables_are_written(built):
    for name in ("genes", "transcripts", "exons", "chromosomes"):
        assert (built / f"{name}.parquet").exists(), name


class TestGenes:
    def test_missing_gene_name_becomes_null_not_empty_string(self, con):
        """`nullif` on the regex result — an empty string would silently pass
        an `IS NOT NULL` filter and produce blank rows in every symbol query."""
        assert (
            con.execute("SELECT gene_name FROM genes WHERE gene_id = 'ENSG0001'").fetchone()[0]
            is None
        )

    def test_gene_name_is_extracted_when_present(self, con):
        assert (
            con.execute("SELECT gene_name FROM genes WHERE gene_id = 'ENSG0002'").fetchone()[0]
            == "TESTG"
        )

    def test_scaffold_is_kept_but_flagged(self, con):
        """Scaffold genes stay in — dropping them would make COUNT(*) disagree
        with Ensembl's published gene count."""
        chrom, primary = con.execute(
            "SELECT chromosome, is_primary_chromosome FROM genes WHERE gene_id = 'ENSG0003'"
        ).fetchone()
        assert chrom == "KI270728.1"
        assert primary is False

    def test_real_chromosome_is_flagged_primary(self, con):
        assert (
            con.execute(
                "SELECT is_primary_chromosome FROM genes WHERE gene_id = 'ENSG0002'"
            ).fetchone()[0]
            is True
        )

    def test_transcript_counts_are_precomputed(self, con):
        total, coding = con.execute(
            "SELECT transcript_count, coding_transcript_count FROM genes WHERE gene_id = 'ENSG0002'"
        ).fetchone()
        assert (total, coding) == (1, 1)

    def test_gene_with_no_transcripts_counts_zero_not_null(self, con):
        """COALESCE on the LEFT JOIN; NULL here would break ORDER BY and SUM."""
        assert (
            con.execute("SELECT transcript_count FROM genes WHERE gene_id = 'ENSG0003'").fetchone()[
                0
            ]
            == 0
        )

    def test_canonical_and_mane_are_resolved_from_repeated_tags(self, con):
        canonical, mane = con.execute(
            "SELECT canonical_transcript_id, mane_select_transcript_id "
            "FROM genes WHERE gene_id = 'ENSG0002'"
        ).fetchone()
        assert canonical == "ENST0002"
        assert mane == "ENST0002"

    def test_genomic_length_is_inclusive(self, con):
        # 9000 - 5000 + 1
        assert (
            con.execute("SELECT genomic_length FROM genes WHERE gene_id = 'ENSG0002'").fetchone()[0]
            == 4001
        )


class TestTranscripts:
    def test_spliced_length_sums_exons_and_differs_from_genomic(self, con):
        """The distinction the schema exists to make explicit: 200+100+50
        of mature RNA inside a 4001 bp locus."""
        genomic, spliced = con.execute(
            "SELECT genomic_length, spliced_length FROM transcripts "
            "WHERE transcript_id = 'ENST0002'"
        ).fetchone()
        assert spliced == 350
        assert genomic == 4001

    def test_cds_length_sums_only_cds_records(self, con):
        # (8900-8801+1) + (7050-7001+1) = 100 + 50
        assert (
            con.execute(
                "SELECT cds_length FROM transcripts WHERE transcript_id = 'ENST0002'"
            ).fetchone()[0]
            == 150
        )

    def test_cds_bounds_span_the_coding_region(self, con):
        start, end = con.execute(
            "SELECT cds_start, cds_end FROM transcripts WHERE transcript_id = 'ENST0002'"
        ).fetchone()
        assert (start, end) == (7001, 8900)

    def test_noncoding_transcript_has_null_cds(self, con):
        """`cds_length IS NOT NULL` is the documented coding test."""
        length, protein = con.execute(
            "SELECT cds_length, protein_id FROM transcripts WHERE transcript_id = 'ENST0001'"
        ).fetchone()
        assert length is None
        assert protein is None

    def test_protein_id_is_carried_over(self, con):
        assert (
            con.execute(
                "SELECT protein_id FROM transcripts WHERE transcript_id = 'ENST0002'"
            ).fetchone()[0]
            == "ENSP0002"
        )

    def test_support_level_keeps_only_the_level(self, con):
        """Source value is '1 (assigned to previous version 3)'."""
        assert (
            con.execute(
                "SELECT transcript_support_level FROM transcripts WHERE transcript_id = 'ENST0002'"
            ).fetchone()[0]
            == "1"
        )

    def test_repeated_tags_all_resolve(self, con):
        canonical, mane, basic = con.execute(
            "SELECT is_canonical, is_mane_select, is_gencode_basic "
            "FROM transcripts WHERE transcript_id = 'ENST0002'"
        ).fetchone()
        assert (canonical, mane, basic) == (True, True, True)

    def test_absent_tags_are_false_not_null(self, con):
        assert (
            con.execute(
                "SELECT is_canonical FROM transcripts WHERE transcript_id = 'ENST0001'"
            ).fetchone()[0]
            is False
        )

    def test_gene_name_is_denormalised_onto_transcripts(self, con):
        assert (
            con.execute(
                "SELECT gene_name FROM transcripts WHERE transcript_id = 'ENST0002'"
            ).fetchone()[0]
            == "TESTG"
        )


class TestExons:
    def test_exon_number_is_transcription_order_not_coordinate_order(self, con):
        """On the minus strand exon 1 has the HIGHEST coordinates. Getting this
        backwards silently reverses every reported exon structure."""
        rows = con.execute(
            "SELECT exon_number, start FROM exons "
            "WHERE transcript_id = 'ENST0002' ORDER BY exon_number"
        ).fetchall()
        assert [r[0] for r in rows] == [1, 2, 3]
        starts = [r[1] for r in rows]
        assert starts == sorted(starts, reverse=True)

    def test_length_is_inclusive(self, con):
        assert (
            con.execute("SELECT length FROM exons WHERE exon_id = 'ENSE0002'").fetchone()[0] == 200
        )

    def test_strand_uses_gtf_representation(self, con):
        """'+'/'-', not Ensembl core's 1/-1."""
        assert set(r[0] for r in con.execute("SELECT DISTINCT strand FROM exons").fetchall()) <= {
            "+",
            "-",
        }


class TestChromosomes:
    def test_lengths_come_from_the_fasta_index(self, con):
        assert (
            con.execute("SELECT length FROM chromosomes WHERE chromosome = '1'").fetchone()[0]
            == 248956422
        )

    def test_only_sequences_with_genes_are_kept(self, con):
        """The real toplevel index has 706 rows of patches and haplotypes."""
        assert con.execute("SELECT count(*) FROM chromosomes").fetchone()[0] == 3

    def test_scaffold_is_flagged(self, con):
        assert (
            con.execute(
                "SELECT is_primary_chromosome FROM chromosomes WHERE chromosome = 'KI270728.1'"
            ).fetchone()[0]
            is False
        )
