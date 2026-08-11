"""Unit tests for observability/cost.py."""

from src.service.observability.cost import compute_cost


def test_haiku_bedrock_cost_maps_to_canonical():
    cost = compute_cost(
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )
    assert cost == 1.00 + 5.00 * 0.5


def test_sonnet_bedrock_cost():
    cost = compute_cost("us.anthropic.claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == 3.00 + 15.00


def test_opus_bedrock_cost():
    cost = compute_cost("us.anthropic.claude-opus-4-6-v1", 1_000_000, 1_000_000)
    assert cost == 15.00 + 75.00


def test_openai_gpt_4o_mini_cost():
    cost = compute_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert abs(cost - (0.15 + 0.60)) < 1e-9


def test_unknown_model_returns_zero():
    assert compute_cost("some-future-model-x", 1000, 1000) == 0.0


def test_zero_tokens():
    assert compute_cost("claude-haiku-4-5", 0, 0) == 0.0
