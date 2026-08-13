"""Back-compat guards for the Portkey → openai rename.

The gateway settings, provider enum values and embedding-provider strings were
all renamed from `portkey*` to `openai*`. Deployed environments still carry the
old `PORTKEY_*` secrets and config values, so every old name has to keep
resolving. These tests pin that promise — without them the rename is a silent
breaking change that only shows up at container start.
"""

from __future__ import annotations

import pytest

from src.config.llm import GATEWAY_ROUTES, ProviderType, normalize_provider
from src.config.settings import Settings, _LEGACY_SECRET_KEYS, settings

# Every required field, so a Settings() built in-test doesn't fail on unrelated
# config. Values are throwaway.
_REQUIRED = {
    "JWT_SECRET_KEY": "test-jwt-secret",
}


def _settings_from_env(monkeypatch, **env: str) -> Settings:
    """Build a Settings purely from env, ignoring the developer's local .env."""
    for key, value in {**_REQUIRED, **env}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


class TestLegacyEnvVars:
    def test_legacy_portkey_env_vars_populate_openai_fields(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch,
            PORTKEY_BASE_URL="https://gateway.example/v1",
            PORTKEY_AZURE_API_KEY="legacy-azure-key",
            PORTKEY_AZURE_SLUG="legacy-azure-slug",
            PORTKEY_BEDROCK_API_KEY="legacy-bedrock-key",
            PORTKEY_BEDROCK_SLUG="legacy-bedrock-slug",
        )

        assert s.openai_gateway_base_url == "https://gateway.example/v1"
        assert s.openai_azure_api_key == "legacy-azure-key"
        assert s.openai_azure_slug == "legacy-azure-slug"
        assert s.openai_bedrock_api_key == "legacy-bedrock-key"
        assert s.openai_bedrock_slug == "legacy-bedrock-slug"

    def test_new_env_vars_win_over_legacy_ones(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch,
            PORTKEY_AZURE_API_KEY="legacy-azure-key",
            PORTKEY_AZURE_SLUG="legacy-azure-slug",
            OPENAI_AZURE_API_KEY="new-azure-key",
            OPENAI_AZURE_SLUG="new-azure-slug",
        )

        assert s.openai_azure_api_key == "new-azure-key"
        assert s.openai_azure_slug == "new-azure-slug"

    def test_every_renamed_field_is_covered_by_the_vault_remap(self):
        """The vault source bypasses AliasChoices, so it needs its own map.

        A field renamed here but forgotten in `_LEGACY_SECRET_KEYS` would read
        fine from env and silently fall back to the default under Vault.
        """
        renamed = {name for name in Settings.model_fields if name.startswith("openai_")} - {
            "openai_gateway_api_key_header",
            "openai_gateway_slug_header",
        }

        assert set(_LEGACY_SECRET_KEYS.values()) == renamed


class TestGatewayHeaders:
    def test_defaults_match_the_deployed_gateway(self):
        """Defaults must not change — deployed envs set no header overrides."""
        headers = settings.get_openai_headers(provider="azure")

        assert set(headers) == {"x-portkey-api-key", "x-portkey-slug"}

    def test_header_names_are_configurable(self, monkeypatch):
        monkeypatch.setattr(settings, "openai_gateway_api_key_header", "authorization-key")
        monkeypatch.setattr(settings, "openai_gateway_slug_header", "x-route")
        monkeypatch.setattr(settings, "openai_azure_api_key", "k")
        monkeypatch.setattr(settings, "openai_azure_slug", "s")

        headers = settings.get_openai_headers(provider="azure")

        assert headers == {"authorization-key": "k", "x-route": "s"}
        assert not any(name.startswith("x-portkey-") for name in headers)


class TestLegacyProviderStrings:
    @pytest.mark.parametrize(
        ("legacy", "expected"),
        [
            ("portkey_azure", ProviderType.OPENAI_AZURE),
            ("portkey_bedrock", ProviderType.OPENAI_BEDROCK),
        ],
    )
    def test_legacy_provider_strings_normalize(self, legacy, expected):
        assert normalize_provider(legacy) == expected

    def test_current_names_pass_through_untouched(self):
        assert normalize_provider(ProviderType.OPENAI_BEDROCK) == ProviderType.OPENAI_BEDROCK
        assert normalize_provider("something-else") == "something-else"

    def test_legacy_provider_reaches_structured_output_routing(self):
        """`create_llm` and friends take raw strings, so routing must normalize."""
        from src.service.llm import LLMService

        assert LLMService.get_structured_output_method("portkey_bedrock") == "function_calling"
        assert LLMService.get_structured_output_method("portkey_azure") == "json_schema"


class TestOnlyGatewayRoutesAreSupported:
    """Direct-vendor providers were removed — only gateway routes remain.

    The `openai` / `anthropic` / `openai_gcp` branches had no callers, and the
    anthropic one was already broken (`langchain_anthropic` is not a dependency).
    Anything that still names them must fail loudly rather than fall through to
    a half-configured client.
    """

    def test_gateway_routes_are_the_whole_enum(self):
        assert set(GATEWAY_ROUTES) == set(ProviderType)

    @pytest.mark.parametrize("removed", ["openai", "anthropic", "openai_gcp", "portkey_gcp"])
    def test_removed_providers_raise(self, removed):
        from src.service.llm import LLMService

        with pytest.raises(ValueError, match="Unsupported provider"):
            LLMService.create_llm(provider=removed, model="whatever")

    def test_removed_routes_raise_in_header_lookup(self):
        with pytest.raises(ValueError, match="Unsupported route"):
            settings.get_openai_headers(provider="gcp")
