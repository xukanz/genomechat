"""Unit tests for observability/callbacks.py."""

from types import SimpleNamespace
from uuid import uuid4

from src.service.observability.callbacks import OTelCallbackHandler


def _fake_llm_response(input_tokens: int, output_tokens: int):
    """Simulate a LangChain LLMResult carrying usage_metadata on a ChatGeneration message."""
    message = SimpleNamespace(
        usage_metadata={"input_tokens": input_tokens, "output_tokens": output_tokens},
        response_metadata={},
    )
    generation = SimpleNamespace(message=message)
    return SimpleNamespace(generations=[[generation]], llm_output={})


def test_callback_emits_single_span_with_tokens_and_cost(in_memory_span_exporter):
    handler = OTelCallbackHandler()
    run_id = uuid4()
    handler.on_llm_start(
        serialized={"name": "ChatBedrock"},
        prompts=["hi"],
        run_id=run_id,
        invocation_params={"model": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
    )
    handler.on_llm_end(_fake_llm_response(100, 50), run_id=run_id)

    spans = in_memory_span_exporter.get_finished_spans()
    assert len(spans) == 1
    s = spans[0]
    assert s.name == "gen_ai.chat"
    assert s.attributes["gen_ai.request.model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert s.attributes["gen_ai.system"] == "anthropic"
    assert s.attributes["gen_ai.usage.input_tokens"] == 100
    assert s.attributes["gen_ai.usage.output_tokens"] == 50
    # Haiku: 100/1M * $1 + 50/1M * $5 = 0.0001 + 0.00025 = 0.00035
    assert abs(s.attributes["gen_ai.usage.cost_usd"] - 0.00035) < 1e-9


def test_callback_handles_error(in_memory_span_exporter):
    handler = OTelCallbackHandler()
    run_id = uuid4()
    handler.on_llm_start(
        serialized={"name": "ChatOpenAI"},
        prompts=["hi"],
        run_id=run_id,
        invocation_params={"model": "gpt-4o-mini"},
    )
    handler.on_llm_error(RuntimeError("fail"), run_id=run_id)
    s = in_memory_span_exporter.get_finished_spans()[0]
    assert s.status.status_code.name == "ERROR"
    assert s.attributes["gen_ai.system"] == "openai"


def test_callback_fallback_to_response_metadata_token_usage(in_memory_span_exporter):
    handler = OTelCallbackHandler()
    run_id = uuid4()
    handler.on_llm_start(
        serialized={"name": "ChatOpenAI"},
        prompts=["hi"],
        run_id=run_id,
        invocation_params={"model": "gpt-4o-mini"},
    )
    message = SimpleNamespace(
        usage_metadata=None,
        response_metadata={"token_usage": {"prompt_tokens": 200, "completion_tokens": 100}},
    )
    response = SimpleNamespace(generations=[[SimpleNamespace(message=message)]], llm_output={})
    handler.on_llm_end(response, run_id=run_id)
    s = in_memory_span_exporter.get_finished_spans()[0]
    assert s.attributes["gen_ai.usage.input_tokens"] == 200
    assert s.attributes["gen_ai.usage.output_tokens"] == 100


def test_end_without_start_is_noop():
    handler = OTelCallbackHandler()
    # Just assert it doesn't raise
    handler.on_llm_end(_fake_llm_response(1, 1), run_id=uuid4())


def test_callback_propagates_thread_id_from_contextvar(in_memory_span_exporter):
    """Regression for Codex Finding 2 — LLM spans must carry `agent.thread_id`.

    Before the fix, tenant scoping in /internal/traces hid every LLM call
    from triage because the exporter couldn't derive tenant_id from an
    empty attribute.
    """
    from src.utils.context import thread_id_context

    handler = OTelCallbackHandler()
    run_id = uuid4()
    token = thread_id_context.set("alice:conv-42")
    try:
        handler.on_llm_start(
            serialized={"name": "ChatBedrock"},
            prompts=["hi"],
            run_id=run_id,
            invocation_params={"model": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
        )
        handler.on_llm_end(_fake_llm_response(10, 5), run_id=run_id)
    finally:
        thread_id_context.reset(token)

    span = in_memory_span_exporter.get_finished_spans()[0]
    assert span.attributes["agent.thread_id"] == "alice:conv-42"
    assert span.attributes["gen_ai.request.model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
