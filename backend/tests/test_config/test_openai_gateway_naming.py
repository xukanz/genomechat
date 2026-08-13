"""Guards for the OpenAI-compatible gateway configuration.

Two promises are pinned here:

1. The gateway settings were renamed from `portkey*` to `openai*`. Deployed
   environments still carry the old `PORTKEY_*` secrets, so every old name has
   to keep resolving — otherwise the rename is a silent breaking change that
   only shows up at container start.
2. Wire header names are configuration, not hardcoded vendor assumptions, and
   their defaults must not drift (deployed envs set no overrides).
"""

from __future__ import annotations

import pytest

from src.config.settings import Settings, _LEGACY_SECRET_KEYS, settings

# Every required field, so a Settings() built in-test doesn't fail on unrelated
# config. Values are throwaway.
_REQUIRED = {
    "JWT_SECRET_KEY": "test-jwt-secret",
    "OPENAI_BEDROCK_API_KEY": "test-bedrock-key",
    "OPENAI_BEDROCK_SLUG": "test-bedrock-slug",
}


def _settings_from_env(monkeypatch, **env: str) -> Settings:
    """Build a Settings purely from env, ignoring the developer's local .env."""
    for key, value in {**_REQUIRED, **env}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


class TestLegacyEnvVars:
    def test_legacy_portkey_env_vars_populate_openai_fields(self, monkeypatch):
        # Not via _REQUIRED — the point is that the legacy names alone suffice.
        monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
        monkeypatch.setenv("PORTKEY_BASE_URL", "https://gateway.example/v1")
        monkeypatch.setenv("PORTKEY_BEDROCK_API_KEY", "legacy-bedrock-key")
        monkeypatch.setenv("PORTKEY_BEDROCK_SLUG", "legacy-bedrock-slug")
        s = Settings(_env_file=None)  # type: ignore[call-arg]

        assert s.openai_gateway_base_url == "https://gateway.example/v1"
        assert s.openai_bedrock_api_key == "legacy-bedrock-key"
        assert s.openai_bedrock_slug == "legacy-bedrock-slug"

    def test_new_env_vars_win_over_legacy_ones(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch,
            PORTKEY_BEDROCK_API_KEY="legacy-bedrock-key",
            OPENAI_BEDROCK_API_KEY="new-bedrock-key",
        )

        assert s.openai_bedrock_api_key == "new-bedrock-key"

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
        headers = settings.get_openai_headers()

        assert set(headers) == {"x-portkey-api-key", "x-portkey-slug"}

    def test_header_names_are_configurable(self, monkeypatch):
        monkeypatch.setattr(settings, "openai_gateway_api_key_header", "authorization-key")
        monkeypatch.setattr(settings, "openai_gateway_slug_header", "x-route")
        monkeypatch.setattr(settings, "openai_bedrock_api_key", "k")
        monkeypatch.setattr(settings, "openai_bedrock_slug", "s")

        headers = settings.get_openai_headers()

        assert headers == {"authorization-key": "k", "x-route": "s"}
        assert not any(name.startswith("x-portkey-") for name in headers)


class TestSingleGatewayRoute:
    """The direct-vendor providers and the second route were removed.

    `openai` / `anthropic` / `openai_gcp` and the Azure route all had no
    callers, and the anthropic branch was already broken (`langchain_anthropic`
    is not a dependency). Nothing should reintroduce a provider concept without
    also reintroducing the credentials it needs.
    """

    def test_create_llm_takes_no_provider(self):
        import inspect

        from src.service.llm import LLMService

        assert "provider" not in inspect.signature(LLMService.create_llm).parameters

    def test_removed_azure_settings_are_gone(self):
        assert "openai_azure_api_key" not in Settings.model_fields
        assert "openai_azure_slug" not in Settings.model_fields

    def test_bedrock_credentials_are_required(self, monkeypatch):
        """The only live route must be the one that fails fast when unset."""
        monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
        monkeypatch.delenv("OPENAI_BEDROCK_API_KEY", raising=False)
        monkeypatch.delenv("PORTKEY_BEDROCK_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BEDROCK_SLUG", raising=False)
        monkeypatch.delenv("PORTKEY_BEDROCK_SLUG", raising=False)

        with pytest.raises(ValueError, match="openai_bedrock_api_key"):
            Settings(_env_file=None)  # type: ignore[call-arg]
