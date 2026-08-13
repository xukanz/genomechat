"""Temperature must not be sent to models that reject it.

Providers return a hard 400 ("`temperature` is deprecated for this model")
rather than ignoring the parameter, so a model missing from
``_NO_TEMPERATURE_MODELS`` takes every agent configured to use it offline. That
failure surfaces only at request time, well away from the config change that
caused it, so the mapping is pinned here.
"""

from __future__ import annotations

import pytest

from src.config.agents import AGENT_MODEL_SETTINGS, resolve_agent_model
from src.service.llm import LLMService

NO_TEMPERATURE = [
    "us.anthropic.claude-opus-5",
    "us.anthropic.claude-sonnet-5",
    "claude-fable-5",
    "o1",
    "o3-mini",
    "o4-preview",
]

SUPPORTS_TEMPERATURE = [
    "us.anthropic.claude-sonnet-4-6",
    "us.anthropic.claude-opus-4-6-v1",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "gpt-4o",
    "gpt-5-mini",
]


@pytest.mark.parametrize("model", NO_TEMPERATURE)
def test_temperature_is_withheld(model):
    assert LLMService._supports_temperature(model) is False


@pytest.mark.parametrize("model", SUPPORTS_TEMPERATURE)
def test_temperature_is_sent(model):
    """Guard the blocklist against over-matching — 4.x must be unaffected."""
    assert LLMService._supports_temperature(model) is True


def test_every_configured_agent_model_is_classified_deliberately():
    """Every model actually wired up must resolve without raising."""
    for agent in AGENT_MODEL_SETTINGS:
        model = resolve_agent_model(agent)
        assert isinstance(LLMService._supports_temperature(model), bool), agent


def test_structured_output_never_uses_json_mode():
    """Anthropic models must use schema-enforced structured output.

    ``json_mode`` only asks for JSON in the prompt and parses whatever returns,
    so a model that opens with a sentence of prose raises OutputParserException
    instead of routing. Observed intermittently on Claude 5. Tool calling is
    enforced provider-side, so this is pinned.
    """
    assert LLMService.STRUCTURED_OUTPUT_METHOD == "function_calling"
