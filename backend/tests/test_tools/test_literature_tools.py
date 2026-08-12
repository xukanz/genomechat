"""Tests for the four Europe PMC literature tools.

Patches ``src.tools.literature._client.httpx.AsyncClient`` — the package's only
httpx import site, so one target covers every tool.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.tools.literature import (
    get_literature_stats,
    get_paper_citations,
    search_by_doi,
    search_literature,
)
from src.tools.literature.tools import MAX_SEARCH_LIMIT

PAPER = {
    "id": "35039532",
    "source": "MED",
    "pmid": "35039532",
    "pmcid": "PMC8764043",
    "doi": "10.1038/s41523-021-00361-2",
    "title": "Value of the loss of heterozygosity to BRCA1 variant classification.",
    "authorString": "Santana Dos Santos E.",
    "pubYear": "2022",
    "abstractText": "At least 10% of the BRCA1/2 tests identify variants.",
    "isOpenAccess": "Y",
    "inEPMC": "Y",
    "citedByCount": 10,
    "journalInfo": {"journal": {"title": "NPJ breast cancer"}},
}


def _json_response(payload):
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


def _text_response(text):
    response = MagicMock()
    response.status_code = 200
    response.raise_for_status = MagicMock()
    response.text = text
    return response


def _status_error(code):
    request = httpx.Request("GET", "https://example.org")
    return httpx.HTTPStatusError(
        str(code), request=request, response=httpx.Response(code, request=request)
    )


def _error_response(code):
    response = MagicMock()
    response.status_code = code
    response.raise_for_status.side_effect = _status_error(code)
    return response


def _search_payload(results, hit_count=100, next_cursor="NEXT"):
    payload = {"hitCount": hit_count, "resultList": {"result": results}}
    if next_cursor is not None:
        payload["nextCursorMark"] = next_cursor
    return payload


@contextmanager
def _patched_client(*responses):
    """Patch the shared AsyncClient, sequencing ``responses`` across GET calls."""
    client = AsyncMock()
    client.get.side_effect = list(responses)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("src.tools.literature._client.httpx.AsyncClient") as client_cls:
        client_cls.return_value = client
        yield client


def _sent_params(client, call_index=0):
    return client.get.call_args_list[call_index].kwargs["params"]


def _sent_url(client, call_index=0):
    return client.get.call_args_list[call_index].args[0]


class TestSearchLiterature:
    @pytest.mark.asyncio
    async def test_issues_exactly_one_request_regardless_of_result_count(self):
        # Tier-1 is abstracts only. Ten results must still be one HTTP call --
        # this is the regression guard against per-result full-text enrichment
        # sneaking back in and turning search into an N+1.
        payload = _search_payload([dict(PAPER, id=str(i)) for i in range(10)])
        with _patched_client(_json_response(payload)) as client:
            await search_literature.ainvoke({"query": "BRCA1", "limit": 10})
        assert client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_sends_core_result_type_and_default_cursor(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke({"query": "BRCA1"})
        params = _sent_params(client)
        assert params["format"] == "json"
        assert params["resultType"] == "core"
        assert params["cursorMark"] == "*"
        assert params["pageSize"] == 10

    @pytest.mark.asyncio
    async def test_relevance_sort_omits_the_sort_parameter(self):
        # Omitting it is Europe PMC's own default ordering.
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke({"query": "BRCA1", "sort": "relevance"})
        assert "sort" not in _sent_params(client)

    @pytest.mark.asyncio
    async def test_cited_sort_maps_to_the_api_token(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke({"query": "BRCA1", "sort": "cited"})
        assert _sent_params(client)["sort"] == "CITED desc"

    @pytest.mark.asyncio
    async def test_invalid_sort_is_rejected_before_any_request(self):
        with _patched_client() as client:
            result = await search_literature.ainvoke({"query": "BRCA1", "sort": "magic"})
        assert result.startswith("Error: Invalid sort")
        assert client.get.call_count == 0

    @pytest.mark.asyncio
    async def test_limit_is_clamped_to_the_ceiling(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke({"query": "BRCA1", "limit": 200})
        assert _sent_params(client)["pageSize"] == MAX_SEARCH_LIMIT

    @pytest.mark.asyncio
    async def test_limit_of_zero_becomes_one(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke({"query": "BRCA1", "limit": 0})
        assert _sent_params(client)["pageSize"] == 1

    @pytest.mark.asyncio
    async def test_cursor_is_forwarded(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke({"query": "BRCA1", "cursor": "ABC"})
        assert _sent_params(client)["cursorMark"] == "ABC"

    @pytest.mark.asyncio
    async def test_filters_reach_the_query_string(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_literature.ainvoke(
                {"query": "BRCA1", "filters": {"open_access_only": True}}
            )
        assert "OPEN_ACCESS:Y" in _sent_params(client)["query"]

    @pytest.mark.asyncio
    async def test_zero_hits_is_not_reported_as_an_error(self):
        payload = _search_payload([], hit_count=0, next_cursor=None)
        with _patched_client(_json_response(payload)):
            result = await search_literature.ainvoke({"query": "zzz"})
        assert not result.startswith("Error")
        assert "No results found" in result

    @pytest.mark.asyncio
    async def test_unknown_filter_key_rejected_before_any_request(self):
        with _patched_client() as client:
            result = await search_literature.ainvoke(
                {"query": "BRCA1", "filters": {"data_providers": ["Acme Press"]}}
            )
        assert result.startswith("Error: Unknown filter key")
        assert client.get.call_count == 0


class TestSearchByDoi:
    @pytest.mark.asyncio
    async def test_open_access_paper_fetches_full_text(self):
        with _patched_client(
            _json_response(_search_payload([PAPER])),
            _text_response("<article><body><p>Full narrative.</p></body></article>"),
        ) as client:
            result = await search_by_doi.ainvoke({"doi": PAPER["doi"]})
        assert client.get.call_count == 2
        assert _sent_url(client, 1).endswith("/PMC8764043/fullTextXML")
        assert "Full narrative." in result

    @pytest.mark.asyncio
    async def test_full_text_request_accepts_xml_not_json(self):
        # The full-text endpoint answers 406 to an application/json Accept.
        with _patched_client(
            _json_response(_search_payload([PAPER])),
            _text_response("<article><body><p>x</p></body></article>"),
        ) as client:
            await search_by_doi.ainvoke({"doi": PAPER["doi"]})
        assert client.get.call_args_list[1].kwargs["headers"]["Accept"] == "application/xml"

    @pytest.mark.asyncio
    async def test_non_open_access_paper_makes_only_one_request(self):
        closed = dict(PAPER, isOpenAccess="N", pmcid=None)
        with _patched_client(_json_response(_search_payload([closed]))) as client:
            result = await search_by_doi.ainvoke({"doi": PAPER["doi"]})
        assert client.get.call_count == 1
        assert "[Not open access" in result
        assert not result.startswith("Error")

    @pytest.mark.asyncio
    async def test_full_text_404_keeps_the_abstract_and_is_not_an_error(self):
        # Losing an abstract we already fetched because full text is missing
        # would be a strictly worse outcome than saying so.
        with _patched_client(
            _json_response(_search_payload([PAPER])),
            _error_response(404),
        ):
            result = await search_by_doi.ainvoke({"doi": PAPER["doi"]})
        assert not result.startswith("Error")
        assert "At least 10%" in result
        assert "not retrievable" in result

    @pytest.mark.asyncio
    async def test_full_text_server_error_also_preserves_the_abstract(self):
        with _patched_client(
            _json_response(_search_payload([PAPER])),
            _error_response(500),
        ):
            result = await search_by_doi.ainvoke({"doi": PAPER["doi"]})
        assert not result.startswith("Error")
        assert "At least 10%" in result

    @pytest.mark.asyncio
    async def test_include_full_text_false_skips_the_second_request(self):
        with _patched_client(_json_response(_search_payload([PAPER]))) as client:
            await search_by_doi.ainvoke({"doi": PAPER["doi"], "include_full_text": False})
        assert client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_malformed_doi_rejected_before_any_request(self):
        with _patched_client() as client:
            result = await search_by_doi.ainvoke({"doi": "not-a-doi"})
        assert result.startswith("Error: Invalid DOI format")
        assert client.get.call_count == 0

    @pytest.mark.asyncio
    async def test_unknown_doi_reports_not_found(self):
        payload = _search_payload([], hit_count=0, next_cursor=None)
        with _patched_client(_json_response(payload)):
            result = await search_by_doi.ainvoke({"doi": "10.9999/nope.1"})
        assert result.startswith("Error: No paper found")


class TestGetPaperCitations:
    _PAYLOAD = {
        "hitCount": 8,
        "citationList": {"citation": [{"id": "42235400", "source": "MED", "title": "T"}]},
    }

    @pytest.mark.asyncio
    async def test_builds_the_citations_path(self):
        with _patched_client(_json_response(self._PAYLOAD)) as client:
            await get_paper_citations.ainvoke({"paper_id": "35039532"})
        assert _sent_url(client).endswith("/MED/35039532/citations")

    @pytest.mark.asyncio
    async def test_references_direction_hits_the_other_path(self):
        payload = {"hitCount": 2, "referenceList": {"reference": [{"id": "1", "title": "R"}]}}
        with _patched_client(_json_response(payload)) as client:
            await get_paper_citations.ainvoke(
                {"paper_id": "35039532", "direction": "references"}
            )
        assert _sent_url(client).endswith("/MED/35039532/references")

    @pytest.mark.asyncio
    async def test_pmcid_forces_the_pmc_source(self):
        with _patched_client(_json_response(self._PAYLOAD)) as client:
            await get_paper_citations.ainvoke({"paper_id": "pmc8764043"})
        assert "/PMC/PMC8764043/citations" in _sent_url(client)

    @pytest.mark.asyncio
    async def test_this_endpoint_paginates_by_page_number(self):
        with _patched_client(_json_response(self._PAYLOAD)) as client:
            await get_paper_citations.ainvoke({"paper_id": "35039532", "page": 3})
        assert _sent_params(client)["page"] == 3

    @pytest.mark.asyncio
    async def test_doi_shaped_id_is_rejected_with_a_recovery_hint(self):
        with _patched_client() as client:
            result = await get_paper_citations.ainvoke({"paper_id": "10.1038/x"})
        assert result.startswith("Error:")
        assert "search_by_doi" in result
        assert client.get.call_count == 0

    @pytest.mark.asyncio
    async def test_invalid_source_rejected_before_any_request(self):
        # source is interpolated into a URL path, so the whitelist is a
        # security control.
        with _patched_client() as client:
            result = await get_paper_citations.ainvoke(
                {"paper_id": "35039532", "source": "../../etc"}
            )
        assert result.startswith("Error: Invalid source")
        assert client.get.call_count == 0

    @pytest.mark.asyncio
    async def test_invalid_direction_rejected(self):
        with _patched_client() as client:
            result = await get_paper_citations.ainvoke(
                {"paper_id": "35039532", "direction": "sideways"}
            )
        assert result.startswith("Error: Invalid direction")
        assert client.get.call_count == 0


class TestGetLiteratureStats:
    @pytest.mark.asyncio
    async def test_orientation_mode_queries_the_whole_corpus(self):
        with _patched_client(_json_response({"hitCount": 48_601_969})) as client:
            result = await get_literature_stats.ainvoke({})
        assert _sent_params(client)["query"] == "*"
        assert _sent_params(client)["pageSize"] == 1
        assert "48,601,969" in result

    @pytest.mark.asyncio
    async def test_probe_mode_requests_one_record_and_returns_only_a_count(self):
        with _patched_client(_json_response({"hitCount": 3412})) as client:
            result = await get_literature_stats.ainvoke({"query": "BRCA1"})
        assert _sent_params(client)["pageSize"] == 1
        assert "3,412 records match" in result
        assert "Abstract:" not in result


# Every error return in the package starts with this exact prefix. Consumers
# classify success vs failure by it, so a path that invents its own wording
# would be silently reported to the agent as a successful result.
ERROR_PREFIX = "Error: "


class TestErrorGrammar:
    """Every failure path must share the one error prefix."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "side_effect",
        [
            httpx.TimeoutException("timed out"),
            httpx.ConnectError("no route"),
        ],
    )
    async def test_transport_failures(self, side_effect):
        with _patched_client(side_effect):
            result = await search_literature.ainvoke({"query": "BRCA1"})
        assert result.startswith(ERROR_PREFIX)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [401, 429, 500, 503])
    async def test_http_status_failures(self, code):
        with _patched_client(_error_response(code)):
            result = await search_literature.ainvoke({"query": "BRCA1"})
        assert result.startswith(ERROR_PREFIX)
        assert f"HTTP {code}" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tool,payload",
        [
            (search_literature, {"query": ""}),
            (search_literature, {"query": "x", "sort": "bogus"}),
            (search_literature, {"query": "x", "filters": {"nope": 1}}),
            (
                search_literature,
                {
                    "query": "x",
                    "filters": {"publication_date_range": {"start": "nope", "end": "2024-01-01"}},
                },
            ),
            (search_by_doi, {"doi": "garbage"}),
            (get_paper_citations, {"paper_id": ""}),
            (get_paper_citations, {"paper_id": "abc!"}),
        ],
    )
    async def test_validation_failures(self, tool, payload):
        with _patched_client():
            result = await tool.ainvoke(payload)
        assert result.startswith(ERROR_PREFIX)

    @pytest.mark.asyncio
    async def test_malformed_json_body(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.side_effect = ValueError("not json")
        with _patched_client(response):
            result = await search_literature.ainvoke({"query": "BRCA1"})
        assert result.startswith(ERROR_PREFIX)


class TestTracing:
    @pytest.mark.asyncio
    async def test_span_is_emitted_for_each_tool(self, in_memory_span_exporter):
        with _patched_client(_json_response(_search_payload([PAPER]))):
            await search_literature.ainvoke({"query": "BRCA1"})
        names = {span.name for span in in_memory_span_exporter.get_finished_spans()}
        assert "agent.tool.search_literature" in names
