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

from src.config.llm import GATEWAY_ROUTES, ProviderType, normalize_provider
from src.config.agents import resolve_agent_llm_config
from src.config.settings import settings

# The gateway ignores the OpenAI `api_key` field — every route authenticates via
# `settings.get_openai_headers()` instead — but the OpenAI client requires the
# field to be non-empty, so the routes below pass this inert placeholder.
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

    @classmethod
    def _get_openai_headers(cls, provider: str) -> dict:
        """Get OpenAI-compatible gateway auth headers for the specified route."""
        return settings.get_openai_headers(provider=provider)

    @staticmethod
    def get_structured_output_method(provider: str) -> str:
        """Get the appropriate structured output method for a provider.

        The Bedrock route serves Anthropic models, which use ``function_calling``
        rather than ``json_mode``. ``json_mode`` is not schema-enforced — it asks
        for JSON in the prompt and parses whatever comes back — so a model that
        opens with a sentence of explanation raises ``OutputParserException``
        instead of routing. That failed intermittently on Claude 5, which is more
        inclined to narrate. Tool calling is schema-enforced at the provider, so
        prose cannot leak through.

        Callers must use ``streaming=False``; Bedrock rejects tool use with
        streaming enabled.

        Args:
            provider: Provider type (from ProviderType enum)

        Returns:
            Method string: 'function_calling' for Bedrock, 'json_schema' otherwise
        """
        provider = normalize_provider(provider)

        if provider == ProviderType.OPENAI_BEDROCK:
            return "function_calling"
        # Default to json_schema for the Azure route and anything unrecognized
        return "json_schema"

    @classmethod
    def get_structured_output_method_for_agent(cls, agent_name: str) -> str:
        """Get the appropriate structured output method for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Method string based on agent's configured provider
        """
        provider, _ = resolve_agent_llm_config(agent_name)
        return cls.get_structured_output_method(provider)

    @classmethod
    def create_llm(
        cls, provider: str, model: str, temperature: float = 0.7, streaming: bool = True, **kwargs
    ) -> BaseChatModel:
        """Low-level factory for LLM instances.

        Every provider is a route on the same OpenAI-compatible gateway, so the
        construction is identical apart from which route's auth headers are
        attached.

        Args:
            provider: Provider name (openai_azure, openai_bedrock);
                pre-rename ``portkey_*`` names are still accepted
            model: Model name
            temperature: Temperature setting (ignored for reasoning models)
            streaming: Enable streaming responses
            **kwargs: Additional provider-specific parameters

        Returns:
            Configured LLM instance

        Raises:
            ValueError: If provider is not supported
        """
        provider = normalize_provider(provider)
        try:
            route = GATEWAY_ROUTES[ProviderType(provider)]
        except ValueError:
            supported = ", ".join(sorted(p.value for p in GATEWAY_ROUTES))
            raise ValueError(
                f"Unsupported provider: {provider}. Must be one of: {supported}"
            ) from None

        llm_kwargs = {
            "model": model,
            "base_url": settings.openai_gateway_base_url,
            "default_headers": cls._get_openai_headers(provider=route),
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
    def get_llm_by_provider(
        cls, provider: str, model: str, temperature: float = 0.7, streaming: bool = True, **kwargs
    ) -> BaseChatModel:
        """Get LLM for specific provider and model.

        Convenience wrapper around create_llm with common defaults.

        Args:
            provider: Provider name
            model: Model name
            temperature: Temperature setting (default: 0.7)
            streaming: Enable streaming responses (default: True)
            **kwargs: Additional provider-specific parameters

        Returns:
            Configured LLM instance
        """
        return cls.create_llm(
            provider=provider, model=model, temperature=temperature, streaming=streaming, **kwargs
        )

    @classmethod
    def get_llm_by_agent(
        cls, agent_name: str, temperature: Optional[float] = None, streaming: bool = True, **kwargs
    ) -> BaseChatModel:
        """Get LLM for specific agent using config mapping.

        Args:
            agent_name: Name of the agent
            temperature: Temperature setting (uses default if not provided)
            streaming: Enable streaming responses (default: True)
            **kwargs: Additional provider-specific parameters

        Returns:
            Configured LLM instance

        Raises:
            ValueError: If agent_name is not found
        """
        provider, model = resolve_agent_llm_config(agent_name)

        # Use default temperature if not provided
        if temperature is None:
            temperature = 0.7

        return cls.create_llm(
            provider=provider, model=model, temperature=temperature, streaming=streaming, **kwargs
        )
