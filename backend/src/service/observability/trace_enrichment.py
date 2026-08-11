"""Trace-level attribute enrichment for Langfuse navigation.

OpenTelemetry has no built-in concept of "session" / "user" — it just has
spans. Langfuse reconstructs its conversation/user views from a set of
magic span attributes on the *root* span of a trace. This module
centralizes the attribute names + the tag list so the enrichment logic
stays in one place and the Workstream C operator guide can reference
stable attribute keys.

Attribute contract (Langfuse-native keys):

  ``langfuse.trace.name``              — human-readable label. Default:
                                          truncated first user message plus a
                                          turn label and a ``[deep]`` suffix
                                          on deep-research turns (so the trace
                                          list stays scannable).
  ``langfuse.session.id``              — conversation thread identifier. All
                                          spans tagged with the same
                                          session_id group into one Langfuse
                                          session view.
  ``user.id``                          — authenticated user id (OTel
                                          convention). Langfuse attributes
                                          the trace to that user.
  ``langfuse.tags``                    — flat list[str] of request-shape
                                          tags: research mode, code language,
                                          active database, anonymous. Powers
                                          the tag filter.
  ``langfuse.observation.input``       — JSON blob with prompt + request
                                          knobs. Populates the trace-level
                                          Input column in Langfuse's UI.
                                          (Without this, child-span
                                          input/output attributes don't roll
                                          up to the trace view.)
  ``langfuse.observation.output``      — set AFTER the stream finishes via
                                          ``build_request_trace_output_attr``
                                          using ``span.set_attribute(...)``.

None of these are required for LangChain/LangGraph correctness; they are
purely navigation aids for whoever is debugging a trace after the fact.
They are only attached when ``settings.otel_enabled`` is True (same gate
as the rest of the tracing pipeline) — when tracing is off, the helpers
return empty dicts and callers become a no-op.

Payload attributes (``langfuse.observation.*``) additionally honor
``settings.trace_capture_payloads`` — off by default so production
traces don't carry raw prompts / completions without explicit opt-in.
Session / user / tag metadata does NOT carry sensitive content so
those are always emitted when OTel is on.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Markdown title extraction regexes — compiled once so repeated use in the
# stream-end path is cheap.
_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BULLET_PREFIX_RE = re.compile(r"^[-*•\d.\s]+")

_NAME_MAX_CHARS = 80


def _truncate_name(raw: str) -> str:
    """Truncate a trace name to a readable length.

    Langfuse's UI shows the full value on hover, so aggressive truncation
    in the list view is fine. 80 chars ≈ two lines in the default table
    density without line-wrap.
    """
    raw = raw.strip().replace("\n", " ").replace("\r", " ")
    if len(raw) <= _NAME_MAX_CHARS:
        return raw
    return raw[: _NAME_MAX_CHARS - 1] + "…"


def _derive_name_from_output(output_text: str) -> str | None:
    """Extract a human-friendly title from the assistant's response.

    Heuristic (first match wins):
      1. First markdown heading (``#`` / ``##`` / ``###``) — our agents
         consistently title responses with ``## Top 10 ...`` or similar,
         so this is the highest-quality signal.
      2. First bolded phrase — for responses that are a paragraph with
         the key finding wrapped in ``**bold**``.
      3. First short line (<= _NAME_MAX_CHARS) that isn't blank —
         catches "Hi Samuel, here's the result" style openers.

    Returns ``None`` if no usable title is found (e.g. empty response,
    or a response that's one long unstructured paragraph). The caller
    falls back to the prompt-based name in that case.

    The returned title is NOT truncated here — the caller composes it
    with the turn/mode suffix first and truncates the whole string so the
    suffix isn't sacrificed for title length.
    """
    if not output_text:
        return None
    text = output_text.strip()
    if not text:
        return None

    # 1. Markdown heading — strip the leading `#`s and any trailing `#`s.
    m = _MARKDOWN_HEADING_RE.search(text)
    if m:
        heading = m.group(2).strip()
        # Strip markdown bolding/italics inside the heading for a cleaner title.
        heading = _MARKDOWN_BOLD_RE.sub(r"\1", heading).replace("*", "")
        if heading:
            return heading

    # 2. Bolded phrase within the first few lines.
    #    Skip lines that are pure prefix noise ("Here's the result:").
    first_chunk = "\n".join(text.splitlines()[:5])
    m = _MARKDOWN_BOLD_RE.search(first_chunk)
    if m:
        bold = m.group(1).strip()
        if bold and len(bold) >= 3:
            return bold

    # 3. First short non-blank line.
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Strip leading markdown bullets / numbering so "- **Foo**" becomes "**Foo**"
        stripped = _BULLET_PREFIX_RE.sub("", stripped).strip()
        stripped = _MARKDOWN_BOLD_RE.sub(r"\1", stripped).replace("*", "")
        if stripped and len(stripped) <= _NAME_MAX_CHARS:
            return stripped
        break  # first non-blank line only; don't scan past

    return None


def _turn_label(turn_index: int | None) -> str | None:
    """Return the short turn label (``t0``, ``t1``, …) for display.

    None or negative values return None so callers can skip the label
    rather than render ``tNone`` / ``t-1``. Defensive — under normal
    flow ``turn_index`` is a non-negative integer computed from the
    LangGraph checkpointer state.
    """
    if turn_index is None or turn_index < 0:
        return None
    return f"t{turn_index}"


def _compose_trace_name(
    first_user_message: str,
    *,
    research_mode: str | None,
    output_text: str | None = None,
    turn_index: int | None = None,
) -> str:
    """Compose a scannable trace name from best-available source + knobs.

    Name-source priority:
      1. ``output_text`` (heading / bold / first line) if provided and
         extractable — by far the best title for post-hoc trace browsing
         because it reflects what was ACTUALLY computed.
      2. ``first_user_message`` — the fallback used while the stream is
         still running and no output exists yet.

    Turn label (``· t0``, ``· t1``, …) is appended whenever
    ``turn_index`` is a valid non-negative integer. Always shown (even
    on the first turn) so the trace list has a uniform column width and
    operators can spot follow-up turns at a glance.

    A ``[deep]`` suffix is appended when deep_research is active, so the
    two research modes stay distinguishable in the trace list.

    Examples::

        # First turn, defaults, name derived from response heading
        "Top 10 Most Frequently Reported Genes in ClinVar · t0"

        # Second turn, deep research
        "Top 10 Genes in ClinVar · t1 [deep]"

        # Mid-stream fallback — turn index known, output not yet
        "What are the most frequently used V genes? · t0"

    Truncation at ``_NAME_MAX_CHARS`` is applied to the whole result so
    the turn + mode suffix isn't clipped before the title is.
    """
    derived: str | None = None
    if output_text:
        derived = _derive_name_from_output(output_text)

    base = derived or (first_user_message or "").strip() or "(empty prompt)"

    turn = _turn_label(turn_index)
    if turn:
        base = f"{base} · {turn}"

    suffix_parts: list[str] = []
    if research_mode == "deep_research":
        suffix_parts.append("deep")

    if suffix_parts:
        name = f"{base} [{', '.join(suffix_parts)}]"
    else:
        name = base
    return _truncate_name(name)


def _serialize_for_span(value: Any) -> str:
    """Serialize + cap a payload for span attribute consumption.

    Uses ``default=str`` to coerce Pydantic / datetime / Path values
    without raising. Capped at ``settings.trace_payload_max_chars``
    (default 8000) to keep OTel exports under typical batch-exporter
    limits. Oversized payloads are truncated with a marker so the
    reader sees that clipping occurred.
    """
    try:
        s = json.dumps(value, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        s = str(value)
    cap = settings.trace_payload_max_chars
    if len(s) > cap:
        return s[:cap] + f"…[truncated {len(s) - cap} chars]"
    return s


def build_request_trace_attrs(
    *,
    user_id: str | None,
    thread_id: str,
    first_user_message: str,
    research_mode: str | None = None,
    code_language: str | None = None,
    database_id: str | None = None,
) -> dict[str, Any]:
    """Return the trace-level attribute dict for the request's root span.

    All keys use the Langfuse-native attribute names documented in the
    Langfuse OTel integration guide (``langfuse.trace.name`` /
    ``langfuse.session.id`` / ``user.id`` / ``langfuse.tags`` /
    ``langfuse.observation.input``). See
    docs/backend/phase2_operator_guide.md §7 for how these surface in the
    Langfuse UI.

    Returns an empty dict when ``settings.otel_enabled`` is False so
    callers can unconditionally ``span.set_attributes(...)`` with it —
    set_attributes({}) is a no-op and keeps the call-site tidy.

    ``langfuse.observation.input`` is only included when BOTH OTel and
    ``trace_capture_payloads`` are enabled — same contract as the node/tool
    decorators so operators have one switch for "attach raw payloads to
    spans" instead of two.

    Args:
        user_id: authenticated user id, or None for anonymous. Non-None
            values flow into ``user.id`` so Langfuse attributes the trace.
        thread_id: conversation thread id (``{user_id}:{conversation_id}``
            format used everywhere else in the codebase). Flows into
            ``langfuse.session.id`` so all turns of one conversation
            group into a single Langfuse session view.
        first_user_message: the prompt text from the incoming request —
            becomes the trace's human-readable title after truncation.
        research_mode: ``"standard"`` | ``"deep_research"`` | None.
        code_language: ``"python"`` | ``"r"`` | ``"auto"`` | None.
        database_id: active database profile, or None.
    """
    if not settings.otel_enabled:
        return {}

    tags: list[str] = []
    if research_mode:
        tags.append(f"research_mode:{research_mode}")
    if code_language:
        tags.append(f"code_language:{code_language}")
    if database_id:
        tags.append(f"database:{database_id}")
    if user_id is None:
        tags.append("anonymous")

    attrs: dict[str, Any] = {
        "langfuse.trace.name": _compose_trace_name(
            first_user_message,
            research_mode=research_mode,
        ),
        "langfuse.session.id": thread_id,
        "langfuse.tags": tags,
    }
    if user_id:
        attrs["user.id"] = user_id

    # Attach the raw request payload so Langfuse's trace-list Input
    # column populates. Gated on trace_capture_payloads — the same
    # opt-in that controls node/tool/LLM-span payload capture.
    if settings.trace_capture_payloads:
        attrs["langfuse.observation.input"] = _serialize_for_span(
            {
                "message": first_user_message or "",
                "research_mode": research_mode,
                "code_language": code_language,
                "database_id": database_id,
            }
        )
    return attrs


def build_request_trace_finalize_attrs(
    *,
    first_user_message: str,
    output: Any,
    turn_index: int | None,
    existing_tags: list[str] | None = None,
    research_mode: str | None = None,
) -> dict[str, Any]:
    """Return the end-of-stream enrichment dict for the root span.

    One call collects the three things we only learn after the graph
    finishes:

    - **Updated trace name** — heading/bold/line extracted from the
      response, plus the turn label (``· tN``) and mode suffix.
    - **Output payload** — ``langfuse.observation.output`` with the
      synthesized assistant response (gated on
      ``trace_capture_payloads``).
    - **Turn metadata + tags** — ``langfuse.metadata.turn_index`` as a
      numeric attribute (for Langfuse dashboard aggregations), plus
      ``turn:tN`` and ``turn:followup`` tags appended to the existing
      ``langfuse.tags`` list in the Langfuse UI's filter surface.

    Tag-merge semantics: OTel ``span.set_attribute("langfuse.tags", …)``
    OVERWRITES — there is no native list-merge. To add the turn tags
    without losing the research_mode / anonymous tags set at
    stream-open, the caller passes the original tag list via
    ``existing_tags`` and this helper returns the concatenated list.

    Returns an empty dict when OTel is off. Returns a partial dict with
    whatever IS safe to emit when payload capture is off — the name
    update and turn tags carry no raw prompt/completion text so they
    are always safe.

    The caller applies via ``span.set_attributes(...)`` on the root
    ``agent.request`` span before it closes.
    """
    if not settings.otel_enabled:
        return {}

    attrs: dict[str, Any] = {}

    # Updated trace name — always emitted (doesn't carry raw payload).
    attrs["langfuse.trace.name"] = _compose_trace_name(
        first_user_message,
        research_mode=research_mode,
        output_text=output if isinstance(output, str) else None,
        turn_index=turn_index,
    )

    # Turn metadata — always emitted (just an integer).
    if turn_index is not None and turn_index >= 0:
        attrs["langfuse.metadata.turn_index"] = turn_index
        # Rebuild the full tag list with turn tags appended, because
        # OTel set_attribute overwrites the previous value rather than
        # merging lists. Tag uses the bare integer (``turn:0``) — the
        # ``turn:`` namespace already signals meaning, and keeping it
        # numeric makes Langfuse's tag filter sort correctly. The
        # trace NAME keeps the ``tN`` form for scan-at-a-glance
        # readability.
        merged_tags = list(existing_tags or [])
        merged_tags.append(f"turn:{turn_index}")
        if turn_index >= 1:
            merged_tags.append("turn:followup")
        attrs["langfuse.tags"] = merged_tags

    # Output payload — gated on payload capture.
    if settings.trace_capture_payloads:
        attrs["langfuse.observation.output"] = _serialize_for_span(output)

    return attrs


def build_request_trace_output_attr(output: Any) -> dict[str, Any]:
    """Return the ``langfuse.observation.output`` attribute for the request.

    .. deprecated:: Phase 2 Workstream C refinement
        Superseded by :func:`build_request_trace_finalize_attrs`, which
        bundles name update + turn metadata + output payload in one
        stream-end call. This helper is kept only for callers that
        want output-only and already compute name/turn elsewhere.

    Called AFTER the stream finishes (the output isn't known when the
    root span opens). The caller assigns this via
    ``span.set_attributes(...)`` on the root ``agent.request`` span so
    Langfuse's trace-list Output column populates.

    Returns an empty dict when OTel is off or payload capture is off —
    callers stay clean with ``span.set_attributes(build_..._attr(...))``.
    """
    if not settings.otel_enabled or not settings.trace_capture_payloads:
        return {}
    return {
        "langfuse.observation.output": _serialize_for_span(output),
    }


__all__ = [
    "build_request_trace_attrs",
    "build_request_trace_output_attr",
]
