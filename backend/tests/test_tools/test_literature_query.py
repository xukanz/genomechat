"""Tests for Europe PMC query construction.

No HTTP here. This is where injection safety and the field-dependent quoting
rules are pinned — both were established against the live API and a regression
in either is silent (wrong results, not an exception).
"""

import pytest

from src.tools.literature._query import (
    VALID_FILTER_KEYS,
    LiteratureQueryError,
    build_query,
)


class TestFreeText:
    def test_single_term_is_quoted_without_parens(self):
        assert build_query("BRCA1") == '"BRCA1"'

    def test_multiple_terms_are_quoted_individually_and_grouped(self):
        # Quoting the whole query would make everything an exact-phrase match
        # and destroy recall.
        assert build_query("BRCA1 variant") == '("BRCA1" "variant")'

    def test_user_quoted_phrase_stays_one_token(self):
        result = build_query('polygenic "risk score" cardiovascular')
        assert '"risk score"' in result
        assert '"polygenic"' in result

    def test_bare_boolean_operators_pass_through_unquoted(self):
        result = build_query("BRCA1 OR BRCA2")
        assert result == '("BRCA1" OR "BRCA2")'

    def test_not_operator_passes_through(self):
        assert "NOT" in build_query("cancer NOT mouse").split()

    def test_lowercase_operator_is_treated_as_a_search_term(self):
        # Europe PMC only honours uppercase operators, so a lowercase "or" is
        # a word the user typed, not syntax.
        assert build_query("BRCA1 or BRCA2") == '("BRCA1" "or" "BRCA2")'


class TestInjectionSafety:
    def test_injected_field_syntax_is_neutralised(self):
        result = build_query('cancer" OR TITLE:"x')
        # The injected field name must be inside a quoted term, and the quote
        # the user supplied must be escaped rather than closing ours.
        assert 'TITLE:\\"x' in result
        assert not result.startswith("TITLE:")

    def test_colons_and_parens_in_free_text_stay_inert(self):
        result = build_query("a: b (c)")
        assert result == '("a:" "b" "(c)")'

    def test_backslash_is_escaped_before_the_quote_char(self):
        assert build_query('a\\"b') == '"a\\\\\\"b"'

    def test_control_characters_are_stripped(self):
        assert "\x00" not in build_query("can\x00cer")


class TestFieldDependentQuoting:
    def test_source_is_written_bare(self):
        # Verified live: SRC:"MED" returns 0 hits, SRC:MED returns results.
        assert build_query("", {"sources": ["MED"]}) == "SRC:MED"

    def test_multiple_sources_or_together_bare(self):
        assert build_query("", {"sources": ["MED", "PMC"]}) == "(SRC:MED OR SRC:PMC)"

    def test_source_is_uppercased(self):
        assert build_query("", {"sources": ["med"]}) == "SRC:MED"

    def test_journal_is_always_quoted(self):
        # Verified live: unquoted multi-word journals silently reinterpret the
        # tail as a free-text term (7639 hits vs 10182).
        assert build_query("", {"journal": ["Nature Genetics"]}) == 'JOURNAL:"Nature Genetics"'

    def test_authors_title_abstract_are_quoted(self):
        assert build_query("", {"authors": ["Smith J"]}) == 'AUTH:"Smith J"'
        assert build_query("", {"title": ["risk score"]}) == 'TITLE:"risk score"'
        assert build_query("", {"abstract": ["cohort"]}) == 'ABSTRACT:"cohort"'


class TestIdentifierFilters:
    def test_single_pmid_scopes_to_med_bare(self):
        assert build_query("", {"pmids": ["35039532"]}) == "(EXT_ID:35039532 AND SRC:MED)"

    def test_multiple_pmids_batch_into_one_clause(self):
        # The batched form is what makes citation traversal usable in one
        # enrichment round-trip instead of one lookup per hit.
        assert build_query("", {"pmids": ["111", "222"]}) == (
            "((EXT_ID:111 OR EXT_ID:222) AND SRC:MED)"
        )

    def test_integer_pmids_are_accepted(self):
        assert build_query("", {"pmids": [35039532]}) == "(EXT_ID:35039532 AND SRC:MED)"

    def test_non_numeric_pmid_rejected(self):
        with pytest.raises(LiteratureQueryError, match="Invalid PMID"):
            build_query("", {"pmids": ["PMC123"]})

    def test_doi_is_quoted(self):
        assert build_query("", {"dois": ["10.1038/x"]}) == 'DOI:"10.1038/x"'

    def test_malformed_doi_rejected(self):
        with pytest.raises(LiteratureQueryError, match="Invalid DOI"):
            build_query("", {"dois": ["not-a-doi"]})


class TestDateRange:
    def test_valid_range_renders_brackets(self):
        result = build_query(
            "", {"publication_date_range": {"start": "2022-01-01", "end": "2024-12-31"}}
        )
        assert result == "FIRST_PDATE:[2022-01-01 TO 2024-12-31]"

    @pytest.mark.parametrize("bad", ["2022", "01-01-2022", "2022-13-01", "yesterday"])
    def test_malformed_dates_rejected(self, bad):
        # Brackets cannot be escaped, so nothing unvalidated may reach them.
        with pytest.raises(LiteratureQueryError, match="Invalid date"):
            build_query("", {"publication_date_range": {"start": bad, "end": "2024-12-31"}})

    def test_missing_edge_rejected(self):
        with pytest.raises(LiteratureQueryError, match="missing 'end'"):
            build_query("", {"publication_date_range": {"start": "2022-01-01"}})


class TestBooleanFilters:
    def test_open_access_only(self):
        assert build_query("", {"open_access_only": True}) == "OPEN_ACCESS:Y"

    def test_exclude_preprints(self):
        assert build_query("", {"exclude_preprints": True}) == "NOT SRC:PPR"

    def test_false_booleans_add_no_clause(self):
        with pytest.raises(LiteratureQueryError):
            build_query("", {"open_access_only": False})


class TestAssembly:
    def test_free_text_is_parenthesised_before_filters(self):
        # Without the parens a user's OR would bind across the filter boundary.
        result = build_query("BRCA1 OR BRCA2", {"open_access_only": True})
        assert result == '("BRCA1" OR "BRCA2") AND OPEN_ACCESS:Y'

    def test_filters_only_search_is_legal(self):
        assert build_query("", {"pmids": ["111"]}) == "(EXT_ID:111 AND SRC:MED)"

    def test_empty_query_and_no_filters_rejected(self):
        with pytest.raises(LiteratureQueryError, match="at least one filter"):
            build_query("")

    def test_multiple_filters_join_with_and(self):
        result = build_query("cancer", {"sources": ["MED"], "open_access_only": True})
        assert result == '"cancer" AND SRC:MED AND OPEN_ACCESS:Y'


class TestUnknownKeys:
    def test_unknown_key_is_an_error_not_a_silent_drop(self):
        # Silently dropping an unrecognised filter lets the agent believe a
        # constraint was applied when it never reached the query.
        with pytest.raises(LiteratureQueryError, match="Unknown filter key"):
            build_query("cancer", {"data_providers": ["Acme Press"]})

    def test_error_enumerates_valid_keys_so_the_agent_can_self_correct(self):
        with pytest.raises(LiteratureQueryError) as exc:
            build_query("cancer", {"nope": 1})
        message = str(exc.value)
        for key in VALID_FILTER_KEYS:
            assert key in message
