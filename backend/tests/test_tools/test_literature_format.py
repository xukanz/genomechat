"""Tests for Europe PMC response formatting.

No HTTP. Two behaviours here are correctness rather than cosmetics: the
pagination footer must not advertise a cursor that leads nowhere (the agent
would loop until it exhausted its turn budget), and every success string must
begin with our own text so the MCP layer's error-prefix check cannot be fooled
by paper content.
"""

import pytest

from src.tools.literature._format import (
    ABSTRACT_MAX_CHARS,
    FULL_TEXT_INLINE_LIMIT,
    FULL_TEXT_PREVIEW_CHARS,
    format_citation,
    format_citation_list,
    format_paper_detail,
    format_search_page,
    format_stats,
)


def _record(**overrides):
    base = {
        "id": "35039532",
        "source": "MED",
        "pmid": "35039532",
        "pmcid": "PMC8764043",
        "doi": "10.1038/s41523-021-00361-2",
        "title": "Value of the loss of heterozygosity to BRCA1 variant classification.",
        "authorString": "Santana Dos Santos E, Spurdle AB.",
        "pubYear": "2022",
        "abstractText": "At least 10% of the BRCA1/2 tests identify variants.",
        "isOpenAccess": "Y",
        "citedByCount": 10,
        "journalInfo": {"journal": {"title": "NPJ breast cancer"}},
    }
    base.update(overrides)
    return base


def _page(results, hit_count=100, next_cursor="NEXT"):
    data = {"hitCount": hit_count, "resultList": {"result": results}}
    if next_cursor is not None:
        data["nextCursorMark"] = next_cursor
    return data


class TestCitation:
    def test_includes_authors_year_title_journal_and_doi_url(self):
        result = format_citation(_record())
        assert "Santana Dos Santos E, Spurdle AB. (2022)." in result
        assert "NPJ breast cancer." in result
        assert "DOI: 10.1038/s41523-021-00361-2" in result
        assert "https://doi.org/10.1038/s41523-021-00361-2" in result

    def test_falls_back_to_pmid_when_doi_absent(self):
        result = format_citation(_record(doi=None))
        assert "PMID: 35039532" in result
        assert "doi.org" not in result

    def test_sparse_record_does_not_raise(self):
        assert format_citation({"id": "1"})

    def test_preprint_uses_publisher_as_venue(self):
        # Preprints carry no journalInfo; the server name is under
        # bookOrReportDetails.publisher.
        record = _record(journalInfo=None, bookOrReportDetails={"publisher": "bioRxiv"})
        assert "bioRxiv" in format_citation(record)

    def test_embedded_html_is_stripped(self):
        record = _record(title="Automated <i>BRCA1</i> classification")
        result = format_citation(record)
        assert "<i>" not in result
        assert "BRCA1" in result

    def test_html_entities_are_unescaped(self):
        assert "&amp;" not in format_citation(_record(title="Cancer &amp; genomics"))


class TestSearchPage:
    def test_header_reports_both_page_size_and_total(self):
        # Without the total the agent cannot tell a narrow topic from "I asked
        # for 10".
        result = format_search_page(_page([_record()], hit_count=3412), "*", "q")
        assert result.startswith("Found 1 of 3,412 matching records:")

    def test_zero_results_is_not_an_error(self):
        # An Error: prefix here would make the MCP layer flag a legitimate
        # negative result as a tool failure and the agent would retry.
        result = format_search_page(_page([], hit_count=0), "*", "obscure")
        assert not result.startswith("Error")
        assert "No results found" in result

    def test_missing_abstract_is_stated_explicitly(self):
        # Omitting the field invites the agent to infer findings from the title.
        result = format_search_page(_page([_record(abstractText=None)]), "*", "q")
        assert "[No abstract available]" in result

    def test_long_abstract_is_truncated(self):
        record = _record(abstractText="x" * (ABSTRACT_MAX_CHARS + 500))
        result = format_search_page(_page([record]), "*", "q")
        assert "[abstract truncated]" in result
        assert len(result) < ABSTRACT_MAX_CHARS + 1200

    def test_abstract_at_the_limit_is_not_truncated(self):
        record = _record(abstractText="x" * ABSTRACT_MAX_CHARS)
        assert "[abstract truncated]" not in format_search_page(_page([record]), "*", "q")

    def test_preprint_is_labelled(self):
        result = format_search_page(_page([_record(source="PPR")]), "*", "q")
        assert "PREPRINT - not peer reviewed" in result


class TestPaginationFooter:
    def test_advertises_cursor_when_a_new_one_is_offered(self):
        result = format_search_page(_page([_record()], next_cursor="ABC123"), "*", "q")
        assert 'cursor="ABC123"' in result
        assert "[End of results]" not in result

    def test_absent_cursor_key_terminates(self):
        # Verified live: the key is omitted when everything fitted in one page.
        result = format_search_page(_page([_record()], next_cursor=None), "*", "q")
        assert "[End of results]" in result
        assert "cursor=" not in result

    def test_echoed_cursor_terminates(self):
        # Verified live: walking off the end echoes the cursor you sent, forever.
        result = format_search_page(_page([_record()], next_cursor="SAME"), "SAME", "q")
        assert "[End of results]" in result

    def test_empty_page_with_echoed_cursor_terminates(self):
        result = format_search_page(_page([], hit_count=5, next_cursor="SAME"), "SAME", "q")
        assert not result.startswith("Error")


class TestCitationList:
    def _citations(self, n=2, hit_count=49):
        return {
            "hitCount": hit_count,
            "citationList": {
                "citation": [
                    {
                        "id": f"1000{i}",
                        "source": "MED",
                        "title": f"Paper {i}",
                        "authorString": "Smith J.",
                        "pubYear": "2020",
                        "journalAbbreviation": "Hum Mutat",
                        "citedByCount": i,
                    }
                    for i in range(n)
                ]
            },
        }

    def test_header_shows_direction_and_total(self):
        result = format_citation_list(self._citations(), "35039532", "MED", "citations", 1)
        assert result.startswith("Found 2 of 49 papers citing MED/35039532 (page 1):")

    def test_references_direction_reads_the_other_key(self):
        data = {"hitCount": 3, "referenceList": {"reference": [{"id": "9", "title": "R"}]}}
        result = format_citation_list(data, "1", "MED", "references", 1)
        assert "referenced by" in result
        assert "R" in result

    def test_footer_teaches_the_batched_enrichment_call(self):
        # Traversal records carry no DOI and no abstract, so without this the
        # agent hops once and stalls.
        result = format_citation_list(self._citations(), "35039532", "MED", "citations", 1)
        assert "search_literature" in result
        assert '"pmids"' in result

    def test_empty_traversal_is_not_an_error(self):
        data = {"hitCount": 0, "citationList": {"citation": []}}
        result = format_citation_list(data, "1", "MED", "citations", 1)
        assert not result.startswith("Error")
        assert "No citations found" in result


class TestPaperDetail:
    def test_short_full_text_is_shown_whole(self):
        text = "y" * (FULL_TEXT_INLINE_LIMIT - 100)
        result = format_paper_detail(_record(), text)
        assert "[Content truncated" not in result
        assert text in result

    def test_long_full_text_is_previewed_and_flagged(self):
        text = "y" * (FULL_TEXT_INLINE_LIMIT + 5000)
        result = format_paper_detail(_record(), text)
        assert f"Preview (first {FULL_TEXT_PREVIEW_CHARS:,} characters)" in result
        assert "[Content truncated" in result

    def test_note_is_shown_when_full_text_is_absent(self):
        result = format_paper_detail(_record(), None, "[Not open access - abstract only.]")
        assert "[Not open access" in result
        assert result.startswith("Paper found:")

    def test_starts_with_our_own_text_not_paper_content(self):
        # The MCP layer classifies by prefix; paper text must never be at
        # offset 0.
        record = _record(title="Error rates in variant calling")
        assert format_paper_detail(record, None).startswith("Paper found:")


class TestStats:
    def test_orientation_mode_lists_coverage_and_filters(self):
        result = format_stats(48_601_969, None, ["journal", "pmids"])
        assert "48,601,969" in result
        assert "PPR" in result
        assert "journal" in result and "pmids" in result

    def test_probe_mode_reports_only_the_count(self):
        result = format_stats(3412, "query", ["journal"])
        assert "3,412 records match" in result
        assert "Coverage:" not in result


@pytest.mark.parametrize(
    "renderer",
    [
        lambda: format_search_page(_page([_record()]), "*", "q"),
        lambda: format_paper_detail(_record(), None),
        lambda: format_stats(1, None, ["journal"]),
    ],
)
def test_success_output_never_starts_with_the_error_prefix(renderer):
    assert not renderer().startswith("Error")
