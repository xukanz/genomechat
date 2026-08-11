"""Centralized LLM service with factory methods.

This service provides centralized LLM instantiation following clean architecture:
- Config layer handles settings and mappings
- Service layer handles instantiation and provider logic
- Agents use service for all LLM access
"""

import os
from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from src.config.llm import ProviderType
from src.config.agents import resolve_agent_llm_config
from src.config.settings import settings


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

    # Models that don't support temperature parameter
    _NO_TEMPERATURE_MODELS = {
        "o1",
        "o1-mini",
        "o1-preview",
        "o3",
        "o3-mini",
        "o3-preview",
        "o4",
        "o4-mini",
        "o4-preview",
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
    def _get_portkey_headers(cls, provider: str) -> dict:
        """Get Portkey headers for specified provider."""
        return settings.get_portkey_headers(provider=provider)

    @staticmethod
    def get_structured_output_method(provider: str) -> str:
        """Get the appropriate structured output method for a provider.

        Args:
            provider: Provider type (from ProviderType enum)

        Returns:
            Method string: 'json_mode' for Bedrock/Anthropic, 'json_schema' for OpenAI/GCP
        """
        if provider in (ProviderType.PORTKEY_BEDROCK, ProviderType.ANTHROPIC):
            return "json_mode"
        elif provider in (
            ProviderType.PORTKEY_AZURE,
            ProviderType.PORTKEY_GCP,
            ProviderType.OPENAI,
        ):
            return "json_schema"
        else:
            # Default to json_schema for unknown providers
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

        Args:
            provider: Provider name (portkey_azure, portkey_bedrock, etc.)
            model: Model name
            temperature: Temperature setting (ignored for reasoning models)
            streaming: Enable streaming responses
            **kwargs: Additional provider-specific parameters

        Returns:
            Configured LLM instance

        Raises:
            ValueError: If provider is not supported
        """
        # Check if this model supports temperature
        supports_temperature = cls._supports_temperature(model)

        if provider == ProviderType.PORTKEY_AZURE:
            portkey_headers = cls._get_portkey_headers(provider="azure")
            llm_kwargs = {
                "model": model,
                "base_url": settings.portkey_base_url,
                "default_headers": portkey_headers,
                "api_key": "portkey",  # Dummy key, auth in headers
                "streaming": streaming,
                "timeout": 600,  # 10 minutes for long streaming responses
                "max_retries": 3,  # Retry on connection failures
                **kwargs,
            }
            if supports_temperature:
                llm_kwargs["temperature"] = temperature
            return ChatOpenAI(**_inject_callbacks(llm_kwargs))

        elif provider == ProviderType.PORTKEY_BEDROCK:
            portkey_headers = cls._get_portkey_headers(provider="bedrock")
            llm_kwargs = {
                "model": model,
                "base_url": settings.portkey_base_url,
                "default_headers": portkey_headers,
                "api_key": "portkey",
                "streaming": streaming,
                "timeout": 600,  # 10 minutes for long streaming responses
                "max_retries": 3,  # Retry on connection failures
                # Note: LangChain's create_agent and bind_tools automatically handle toolConfig
                # Don't set tool_choice here as it conflicts with LangChain's automatic tool binding
                **kwargs,
            }
            if supports_temperature:
                llm_kwargs["temperature"] = temperature
            return ChatOpenAI(**_inject_callbacks(llm_kwargs))

        elif provider == ProviderType.PORTKEY_GCP:
            portkey_headers = cls._get_portkey_headers(provider="gcp")
            llm_kwargs = {
                "model": model,
                "base_url": settings.portkey_base_url,
                "default_headers": portkey_headers,
                "api_key": "portkey",
                "streaming": streaming,
                "timeout": 600,  # 10 minutes for long streaming responses
                "max_retries": 3,  # Retry on connection failures
                **kwargs,
            }
            if supports_temperature:
                llm_kwargs["temperature"] = temperature
            return ChatOpenAI(**_inject_callbacks(llm_kwargs))

        elif provider == ProviderType.OPENAI:
            llm_kwargs = {
                "model": model,
                "streaming": streaming,
                "timeout": 600,  # 10 minutes for long streaming responses
                "max_retries": 3,  # Retry on connection failures
                **kwargs,
            }
            if supports_temperature:
                llm_kwargs["temperature"] = temperature

            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key
            return ChatOpenAI(**_inject_callbacks(llm_kwargs))

        elif provider == ProviderType.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            llm_kwargs = {
                "model": model,
                "streaming": streaming,
                "timeout": 600,  # 10 minutes for long streaming responses
                "max_retries": 3,  # Retry on connection failures
                **kwargs,
            }
            if supports_temperature:
                llm_kwargs["temperature"] = temperature

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                llm_kwargs["api_key"] = api_key
            return ChatAnthropic(**_inject_callbacks(llm_kwargs))

        else:
            raise ValueError(f"Unsupported provider: {provider}")

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
