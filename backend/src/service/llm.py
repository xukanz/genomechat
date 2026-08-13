"""Centralized LLM service with factory methods.

This service provides centralized LLM instantiation following clean architecture:
- Config layer handles settings and mappings
- Service layer handles instantiation and provider logic
- Agents use service for all LLM access
"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from src.config.agents import resolve_agent_model
from src.config.settings import settings

# The gateway ignores the OpenAI `api_key` field — it authenticates via
# `settings.get_openai_headers()` instead — but the OpenAI client requires the
# field to be non-empty, so pass this inert placeholder.
_GATEWAY_PLACEHOLDER_API_KEY = "unused"


def _observability_callbacks() -> list[BaseCallbackHandler]:
    """Return observability callbacks to attach to every LLM instance.

    Imported lazily so tests that don't touch LLMs don't pay the import cost.
    Returns an empty list when OTel is disabled so the call path is a no-op.
    """
    if not settings.otel_enabled:
        return []
    try:
        from src.service.observability.callbacks import OTelCallbackHandler

        return [OTelCallbackHandler()]
    except Exception:  # pragma: no cover — never break LLM construction
        return []


def _inject_callbacks(llm_kwargs: dict) -> dict:
    """Append observability callbacks to `llm_kwargs['callbacks']` (list)."""
    extra = _observability_callbacks()
    if not extra:
        return llm_kwargs
    existing = llm_kwargs.get("callbacks")
    if existing is None:
        llm_kwargs["callbacks"] = extra
    else:
        llm_kwargs["callbacks"] = list(existing) + extra
    return llm_kwargs


class LLMService:
    """Centralized LLM service with factory methods."""

    # Models that don't support the temperature parameter. Matching is a
    # substring test against the de-hyphenated model id, so "claude-sonnet-5"
    # also covers "us.anthropic.claude-sonnet-5" and any point releases.
    #
    # Sending temperature to one of these is a hard 400 from the provider
    # ("`temperature` is deprecated for this model"), not a silent ignore, so a
    # missing entry takes every agent using that model offline.
    _NO_TEMPERATURE_MODELS = {
        # OpenAI reasoning models
        "o1",
        "o1-mini",
        "o1-preview",
        "o3",
        "o3-mini",
        "o3-preview",
        "o4",
        "o4-mini",
        "o4-preview",
        # Claude 5 family — rejected via Bedrock
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-fable-5",
    }

    @classmethod
    def _supports_temperature(cls, model: str) -> bool:
        """Check if model supports temperature parameter."""
        model_base = model.lower().replace("-", "")
        return not any(
            no_temp_model.replace("-", "") in model_base
            for no_temp_model in cls._NO_TEMPERATURE_MODELS
        )

    # Structured output method for every model we serve.
    #
    # The gateway's Bedrock route serves Anthropic models, which need
    # ``function_calling`` rather than ``json_mode``. ``json_mode`` is not
    # schema-enforced — it asks for JSON in the prompt and parses whatever comes
    # back — so a model that opens with a sentence of explanation raises
    # ``OutputParserException`` instead of routing. That failed intermittently on
    # Claude 5, which is more inclined to narrate. Tool calling is schema-enforced
    # at the provider, so prose cannot leak through.
    #
    # Callers must use ``streaming=False``; Bedrock rejects tool use with
    # streaming enabled.
    STRUCTURED_OUTPUT_METHOD = "function_calling"

    @classmethod
    def create_llm(
        cls, model: str, temperature: float = 0.7, streaming: bool = True, **kwargs
    ) -> BaseChatModel:
        """Low-level factory for LLM instances.

        Every model is served by one route on an OpenAI-compatible gateway, so
        the only thing that varies between calls is the model name.

        Args:
            model: Model name
            temperature: Temperature setting (ignored for reasoning models)
            streaming: Enable streaming responses
            **kwargs: Additional parameters forwarded to ChatOpenAI

        Returns:
            Configured LLM instance
        """
        llm_kwargs = {
            "model": model,
            "base_url": settings.openai_gateway_base_url,
            "default_headers": settings.get_openai_headers(),
            "api_key": _GATEWAY_PLACEHOLDER_API_KEY,
            "streaming": streaming,
            "timeout": 600,  # 10 minutes for long streaming responses
            "max_retries": 3,  # Retry on connection failures
            # Note: LangChain's create_agent and bind_tools automatically handle toolConfig
            # Don't set tool_choice here as it conflicts with LangChain's automatic tool binding
            **kwargs,
        }
        if cls._supports_temperature(model):
            llm_kwargs["temperature"] = temperature
        return ChatOpenAI(**_inject_callbacks(llm_kwargs))

    @classmethod
    def get_llm_by_agent(
        cls, agent_name: str, temperature: Optional[float] = None, streaming: bool = True, **kwargs
    ) -> BaseChatModel:
        """Get LLM for specific agent using config mapping.

        Args:
            agent_name: Name of the agent
            temperature: Temperature setting (uses default if not provided)
            streaming: Enable streaming responses (default: True)
            **kwargs: Additional parameters forwarded to ChatOpenAI

        Returns:
            Configured LLM instance

        Raises:
            ValueError: If agent_name is not found
        """
        model = resolve_agent_model(agent_name)

        # Use default temperature if not provided
        if temperature is None:
            temperature = 0.7

        return cls.create_llm(model=model, temperature=temperature, streaming=streaming, **kwargs)
