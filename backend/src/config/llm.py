"""LLM Provider Configuration.

Defines supported LLM provider types. LLM instantiation logic has been moved
to src.service.llm for clean architecture separation.
"""

from enum import Enum


class ProviderType(str, Enum):
    """Supported LLM providers.

    Every provider is a route on a single OpenAI-compatible gateway — there is
    no direct-vendor path. Both are built as ``ChatOpenAI`` against
    ``settings.openai_gateway_base_url``, with per-route auth passed in headers.
    No vendor SDK is involved.
    """

    OPENAI_AZURE = "openai_azure"
    OPENAI_BEDROCK = "openai_bedrock"


# Provider → the route name `settings.get_openai_headers()` authenticates as.
# Membership here is also what makes a provider supported: `create_llm` rejects
# anything absent, so adding a route means adding one entry.
GATEWAY_ROUTES: dict[ProviderType, str] = {
    ProviderType.OPENAI_AZURE: "azure",
    ProviderType.OPENAI_BEDROCK: "bedrock",
}


# These routes were named after the gateway vendor before the rename. Deployed
# config and external callers may still pass the old strings, so normalize them
# rather than failing with "Unsupported provider".
LEGACY_PROVIDER_ALIASES: dict[str, ProviderType] = {
    "portkey_azure": ProviderType.OPENAI_AZURE,
    "portkey_bedrock": ProviderType.OPENAI_BEDROCK,
}


def normalize_provider(provider: str) -> str:
    """Map a pre-rename provider string onto its current name."""
    return LEGACY_PROVIDER_ALIASES.get(provider, provider)
