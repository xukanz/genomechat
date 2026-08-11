"""Tests for trace-level attribute enrichment (Phase 2 Workstream C).

Pins the Langfuse-native attribute contract:

- ``langfuse.trace.name`` = truncated first user message (<= 80 chars),
  optionally suffixed with a scannable ``[coder=..., orch=..., deep]``
  tag when overrides are active.
- ``langfuse.session.id`` = thread_id.
- ``user.id`` when authenticated; omitted when anonymous.
- ``langfuse.tags`` is a flat list of ``key:value`` strings covering the
  request-shape knobs operators filter on in the Langfuse UI.
- ``langfuse.observation.input`` set when trace_capture_payloads is on.
- ``langfuse.observation.output`` provided by a separate helper so the
  caller can set it AFTER the stream finishes.
- Empty dict from either helper when OTel is disabled globally (no
  accidental emission).
"""

from __future__ import annotations

import pytest

from src.service.observability.trace_enrichment import (
    build_request_trace_attrs,
    build_request_trace_output_attr,
)


@pytest.fixture(autouse=True)
def _enable_otel(monkeypatch):
    """The helpers return {} when OTel is globally disabled. Tests that want
    to exercise the body need otel_enabled=True; the dedicated 'disabled'
    tests opt out of this fixture by re-patching."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "otel_enabled", True)


def test_minimal_inputs_produce_session_name_and_empty_tags():
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="anonymous:abc123",
        first_user_message="hello world",
    )
    assert attrs["langfuse.trace.name"] == "hello world"
    assert attrs["langfuse.session.id"] == "anonymous:abc123"
    # Anonymous gets a tag so the Langfuse UI can filter unauthenticated runs.
    assert attrs["langfuse.tags"] == ["anonymous"]
    # user.id omitted for anonymous.
    assert "user.id" not in attrs


def test_authenticated_user_gets_user_id_and_no_anonymous_tag():
    attrs = build_request_trace_attrs(
        user_id="u-42",
        thread_id="u-42:conv-1",
        first_user_message="hi",
    )
    assert attrs["user.id"] == "u-42"
    assert "anonymous" not in attrs["langfuse.tags"]


def test_all_request_knobs_surface_as_tags():
    attrs = build_request_trace_attrs(
        user_id="u-1",
        thread_id="u-1:c-1",
        first_user_message="analyze the TCR data",
        research_mode="deep_research",
        code_language="python",
        database_id="clinvar_v2",
        coder_backend_override="sdk",
        orchestrator_backend_override="sdk",
    )
    tags = set(attrs["langfuse.tags"])
    assert tags == {
        "research_mode:deep_research",
        "code_language:python",
        "database:clinvar_v2",
        "coder_backend:sdk",
        "orchestrator_backend:sdk",
    }


def test_name_is_truncated_and_newlines_removed():
    long_msg = "Q: " + ("a" * 200) + "\nextra"
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message=long_msg,
    )
    name = attrs["langfuse.trace.name"]
    # Max 80 chars, must end with the truncation marker.
    assert len(name) <= 80
    assert name.endswith("…")
    # No newline survives.
    assert "\n" not in name
    assert "\r" not in name


def test_empty_prompt_falls_back_to_placeholder():
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message="",
    )
    assert attrs["langfuse.trace.name"] == "(empty prompt)"


def test_none_knobs_do_not_produce_empty_tags():
    """A knob explicitly set to None must not produce a ``key:None`` tag."""
    attrs = build_request_trace_attrs(
        user_id="u",
        thread_id="t",
        first_user_message="hi",
        research_mode=None,
        code_language=None,
        database_id=None,
        coder_backend_override=None,
        orchestrator_backend_override=None,
    )
    # No tags at all for an authenticated user with no overrides.
    assert attrs["langfuse.tags"] == []


def test_returns_empty_when_otel_disabled(monkeypatch):
    """Global off switch → empty dict so ``span.set_attributes({})`` is a no-op."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "otel_enabled", False)
    attrs = build_request_trace_attrs(
        user_id="u-1",
        thread_id="u-1:c-1",
        first_user_message="hi",
        research_mode="deep_research",
    )
    assert attrs == {}


# ---------------------------------------------------------------------------
# Name composition — scannable trace list in Langfuse
# ---------------------------------------------------------------------------


def test_trace_name_has_no_suffix_when_all_defaults():
    attrs = build_request_trace_attrs(
        user_id=None, thread_id="t", first_user_message="Top 10 V genes?"
    )
    # Plain prompt, no suffix.
    assert attrs["langfuse.trace.name"] == "Top 10 V genes?"


def test_trace_name_suffix_marks_coder_override():
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message="Top 10 V genes?",
        coder_backend_override="sdk",
    )
    # Suffix makes the A/B run distinguishable at a glance in the trace list.
    assert attrs["langfuse.trace.name"] == "Top 10 V genes? [coder=sdk]"


def test_trace_name_suffix_marks_orchestrator_override_and_deep_research():
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message="Top 10 V genes?",
        orchestrator_backend_override="sdk",
        research_mode="deep_research",
    )
    assert attrs["langfuse.trace.name"] == "Top 10 V genes? [orch=sdk, deep]"


def test_trace_name_suffix_combines_all_three_markers():
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message="hi",
        coder_backend_override="sdk",
        orchestrator_backend_override="sdk",
        research_mode="deep_research",
    )
    assert attrs["langfuse.trace.name"] == "hi [coder=sdk, orch=sdk, deep]"


def test_trace_name_standard_research_mode_does_not_suffix():
    """research_mode='standard' is the default; adding a tag for it would
    pollute the trace list on every request. Only 'deep_research' adds a
    marker because that's the distinguishing case."""
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message="hi",
        research_mode="standard",
    )
    assert attrs["langfuse.trace.name"] == "hi"


def test_trace_name_truncation_preserves_suffix_when_truncated():
    """A very long prompt + a suffix still truncates to the cap."""
    long_prompt = "Q " * 100
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message=long_prompt,
        coder_backend_override="sdk",
    )
    name = attrs["langfuse.trace.name"]
    assert len(name) <= 80
    assert name.endswith("…")


# ---------------------------------------------------------------------------
# Input payload capture (on the root span, for Langfuse's trace-level column)
# ---------------------------------------------------------------------------


def test_input_payload_attached_when_capture_enabled(monkeypatch):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "trace_capture_payloads", True)
    attrs = build_request_trace_attrs(
        user_id="u-1",
        thread_id="u-1:c-1",
        first_user_message="hello",
        research_mode="standard",
        code_language="python",
        database_id="clinvar",
        coder_backend_override="sdk",
    )
    # Input is serialized JSON of the request knobs + prompt.
    raw = attrs["langfuse.observation.input"]
    assert isinstance(raw, str)
    assert '"message": "hello"' in raw
    assert '"database_id": "clinvar"' in raw
    assert '"coder_backend": "sdk"' in raw


def test_input_payload_omitted_when_capture_disabled(monkeypatch):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "trace_capture_payloads", False)
    attrs = build_request_trace_attrs(
        user_id="u-1",
        thread_id="u-1:c-1",
        first_user_message="hello",
    )
    assert "langfuse.observation.input" not in attrs
    # Session/name/tags still present — those never carry raw content.
    assert "langfuse.session.id" in attrs
    assert "langfuse.trace.name" in attrs


def test_input_payload_respects_truncation_cap(monkeypatch):
    """Large prompts get truncated per trace_payload_max_chars so OTel
    batch exporters don't blow up on huge single attributes."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "trace_capture_payloads", True)
    monkeypatch.setattr(settings, "trace_payload_max_chars", 100)
    huge_prompt = "x" * 10_000
    attrs = build_request_trace_attrs(
        user_id=None,
        thread_id="t",
        first_user_message=huge_prompt,
    )
    raw = attrs["langfuse.observation.input"]
    assert len(raw) <= 100 + len("…[truncated 99999 chars]")  # cap + marker
    assert "truncated" in raw


# ---------------------------------------------------------------------------
# Output helper — called after the stream finishes
# ---------------------------------------------------------------------------


def test_output_helper_returns_attr_when_capture_enabled(monkeypatch):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "trace_capture_payloads", True)
    out = build_request_trace_output_attr("the final synthesized answer")
    assert out == {"langfuse.observation.output": '"the final synthesized answer"'}


def test_output_helper_empty_when_capture_disabled(monkeypatch):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "trace_capture_payloads", False)
    out = build_request_trace_output_attr("hello")
    assert out == {}


def test_output_helper_empty_when_otel_disabled(monkeypatch):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "otel_enabled", False)
    monkeypatch.setattr(settings, "trace_capture_payloads", True)
    out = build_request_trace_output_attr("hello")
    assert out == {}


def test_output_helper_serializes_non_string_values(monkeypatch):
    """Accepts dicts / lists / pydantic-ish objects. The output stage
    usually just gets the assistant's string, but the helper must not
    crash on something else."""
    from src.config.settings import settings

    monkeypatch.setattr(settings, "trace_capture_payloads", True)
    out = build_request_trace_output_attr({"reply": "pong"})
    assert out["langfuse.observation.output"] == '{"reply": "pong"}'


# ---------------------------------------------------------------------------
# Content-derived trace name (heading / bold / first-line extraction)
# ---------------------------------------------------------------------------


def test_name_derived_from_first_markdown_heading(monkeypatch):
    """Response starts with ## heading → heading is the trace name."""
    from src.service.observability.trace_enrichment import _compose_trace_name

    response = "## Top 10 Most Frequently Reported Variants in ClinVar\n\nTRBV19*01 ..."
    name = _compose_trace_name(
        "What are the most frequent V genes?",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        output_text=response,
        turn_index=0,
    )
    assert name == "Top 10 Most Frequently Reported Variants in ClinVar · t0"


def test_name_derived_from_bold_phrase_when_no_heading(monkeypatch):
    from src.service.observability.trace_enrichment import _compose_trace_name

    response = "Here's the answer: **The most frequent V gene is TRBV19**. Details below..."
    name = _compose_trace_name(
        "what is the top gene?",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        output_text=response,
        turn_index=0,
    )
    assert name == "The most frequent V gene is TRBV19 · t0"


def test_name_falls_back_to_prompt_when_output_unstructured():
    """A response that's one long flat paragraph doesn't give a clean
    heading/bold/short-line — the prompt becomes the fallback."""
    from src.service.observability.trace_enrichment import _compose_trace_name

    unstructured = "x" * 200  # one long blob, no markdown, one line > 80 chars
    name = _compose_trace_name(
        "brief prompt",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        output_text=unstructured,
        turn_index=0,
    )
    assert name == "brief prompt · t0"


def test_name_strips_bold_from_within_heading():
    """## **Bold Title** → 'Bold Title' (markdown cleaned out)."""
    from src.service.observability.trace_enrichment import _compose_trace_name

    response = "## **Top 10 Variants** in ClinVar"
    name = _compose_trace_name(
        "q",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        output_text=response,
        turn_index=0,
    )
    assert name == "Top 10 Variants in ClinVar · t0"


# ---------------------------------------------------------------------------
# Turn label — uniform t0 / t1 / t2 format always shown
# ---------------------------------------------------------------------------


def test_turn_label_on_first_turn_is_t0():
    attrs = build_request_trace_attrs(user_id=None, thread_id="t", first_user_message="hi")
    # Initial stream-open attrs don't carry turn yet (it's computed at end).
    # Covered in test_finalize_* below.
    assert attrs["langfuse.trace.name"] == "hi"


def test_compose_name_includes_turn_label_t0():
    from src.service.observability.trace_enrichment import _compose_trace_name

    name = _compose_trace_name(
        "hi",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        turn_index=0,
    )
    assert name == "hi · t0"


def test_compose_name_includes_turn_label_t2():
    from src.service.observability.trace_enrichment import _compose_trace_name

    name = _compose_trace_name(
        "follow-up question",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        turn_index=2,
    )
    assert name == "follow-up question · t2"


def test_compose_name_skips_turn_label_when_none():
    """turn_index=None → no label (before stream-end, when unknown)."""
    from src.service.observability.trace_enrichment import _compose_trace_name

    name = _compose_trace_name(
        "hi",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        turn_index=None,
    )
    assert "·" not in name
    assert name == "hi"


def test_compose_name_skips_turn_label_when_negative():
    """Defensive: negative indices are treated as missing."""
    from src.service.observability.trace_enrichment import _compose_trace_name

    name = _compose_trace_name(
        "hi",
        coder_backend_override=None,
        orchestrator_backend_override=None,
        research_mode=None,
        turn_index=-1,
    )
    assert "·" not in name


def test_compose_name_turn_label_before_backend_suffix():
    """Order: base · tN [suffix]. Critical for grepping by turn in a
    list view — turn label always comes before brackets."""
    from src.service.observability.trace_enrichment import _compose_trace_name

    name = _compose_trace_name(
        "hi",
        coder_backend_override="sdk",
        orchestrator_backend_override="sdk",
        research_mode="deep_research",
        turn_index=3,
    )
    assert name == "hi · t3 [coder=sdk, orch=sdk, deep]"


# ---------------------------------------------------------------------------
# Finalize helper — the end-of-stream one-shot enrichment
# ---------------------------------------------------------------------------


def test_finalize_returns_empty_when_otel_disabled(monkeypatch):
    from src.config.settings import settings
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    monkeypatch.setattr(settings, "otel_enabled", False)
    attrs = build_request_trace_finalize_attrs(
        first_user_message="hi",
        output="## Title",
        turn_index=0,
    )
    assert attrs == {}


def test_finalize_updates_trace_name_with_output_heading_and_turn():
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    attrs = build_request_trace_finalize_attrs(
        first_user_message="What are the top V genes?",
        output="## Top 10 Most Frequently Reported Variants in ClinVar\n\nTRBV19*01 ...",
        turn_index=0,
    )
    assert attrs["langfuse.trace.name"] == ("Top 10 Most Frequently Reported Variants in ClinVar · t0")


def test_finalize_attaches_turn_index_metadata():
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    attrs = build_request_trace_finalize_attrs(
        first_user_message="hi",
        output="pong",
        turn_index=2,
    )
    assert attrs["langfuse.metadata.turn_index"] == 2


def test_finalize_merges_turn_tags_with_existing_list():
    """OTel set_attribute overwrites — helper must combine original +
    turn tags so tagnames set at stream-open survive."""
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    existing = ["research_mode:standard", "code_language:python", "anonymous"]
    attrs = build_request_trace_finalize_attrs(
        first_user_message="hi",
        output="pong",
        turn_index=3,
        existing_tags=existing,
    )
    merged = attrs["langfuse.tags"]
    # Original tags preserved
    for t in existing:
        assert t in merged
    # Turn tags appended
    assert "turn:3" in merged
    assert "turn:followup" in merged


def test_finalize_turn_tag_followup_only_after_turn_zero():
    """turn:followup is shorthand for 'not the first turn'. Turn 0
    should get turn:t0 alone."""
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    attrs0 = build_request_trace_finalize_attrs(
        first_user_message="hi", output="pong", turn_index=0, existing_tags=[]
    )
    assert "turn:0" in attrs0["langfuse.tags"]
    assert "turn:followup" not in attrs0["langfuse.tags"]

    attrs1 = build_request_trace_finalize_attrs(
        first_user_message="hi", output="pong", turn_index=1, existing_tags=[]
    )
    assert "turn:1" in attrs1["langfuse.tags"]
    assert "turn:followup" in attrs1["langfuse.tags"]


def test_finalize_output_gated_on_payload_capture(monkeypatch):
    from src.config.settings import settings
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    # Off → name + metadata emitted but output NOT
    monkeypatch.setattr(settings, "trace_capture_payloads", False)
    attrs = build_request_trace_finalize_attrs(
        first_user_message="hi",
        output="secret payload",
        turn_index=0,
    )
    assert "langfuse.trace.name" in attrs
    assert "langfuse.metadata.turn_index" in attrs
    assert "langfuse.observation.output" not in attrs

    # On → output attached
    monkeypatch.setattr(settings, "trace_capture_payloads", True)
    attrs = build_request_trace_finalize_attrs(
        first_user_message="hi",
        output="secret payload",
        turn_index=0,
    )
    assert "langfuse.observation.output" in attrs
    assert "secret payload" in attrs["langfuse.observation.output"]


def test_finalize_handles_missing_turn_index_gracefully():
    """turn_index=None → name has no · tN, no metadata, no turn tags."""
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    attrs = build_request_trace_finalize_attrs(
        first_user_message="hi",
        output="## Title\nbody",
        turn_index=None,
    )
    # Name uses derived heading but no turn label
    assert attrs["langfuse.trace.name"] == "Title"
    assert "langfuse.metadata.turn_index" not in attrs
    # No tag mutation
    assert "langfuse.tags" not in attrs


def test_finalize_combines_all_dimensions():
    """Full integration: heading + turn + backend override + payload capture."""
    from src.config.settings import settings
    from src.service.observability.trace_enrichment import (
        build_request_trace_finalize_attrs,
    )

    # trace_capture_payloads may already be on from the autouse fixture-neighbors;
    # set it explicitly for clarity.
    settings.trace_capture_payloads = True
    existing = ["research_mode:deep_research", "code_language:python"]
    attrs = build_request_trace_finalize_attrs(
        first_user_message="Analyze the TCR data",
        output="## TCR Analysis Complete\n\nKey findings: …",
        turn_index=2,
        existing_tags=existing,
        research_mode="deep_research",
        coder_backend_override="sdk",
        orchestrator_backend_override="sdk",
    )
    # Name = heading + turn + backend suffix
    assert attrs["langfuse.trace.name"] == (
        "TCR Analysis Complete · t2 [coder=sdk, orch=sdk, deep]"
    )
    # Turn metadata + tags merged with originals
    assert attrs["langfuse.metadata.turn_index"] == 2
    merged = attrs["langfuse.tags"]
    assert "research_mode:deep_research" in merged
    assert "code_language:python" in merged
    assert "turn:2" in merged
    assert "turn:followup" in merged
    # Output captured
    assert "TCR Analysis Complete" in attrs["langfuse.observation.output"]
