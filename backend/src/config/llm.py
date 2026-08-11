"""LLM Provider Configuration.

Defines supported LLM provider types. LLM instantiation logic has been moved
to src.service.llm for clean architecture separation.
"""

from enum import Enum


class ProviderType(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    PORTKEY_AZURE = "portkey_azure"
    PORTKEY_BEDROCK = "portkey_bedrock"
    PORTKEY_GCP = "portkey_gcp"
