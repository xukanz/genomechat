"""Guards for the OpenAI-compatible gateway configuration.

The gateway settings have been renamed twice — off the vendor name, then onto
the conventional OpenAI shape (`OPENAI_BASE_URL` / `OPENAI_API_KEY` /
`OPENAI_EXTRA_HEADERS`). Deployed environments still carry the older names, and
a rename that quietly stops reading them is a breaking change that only surfaces
at container start, or worse, as a gateway rejection at request time. Every old
spelling is pinned here.
"""

from __future__ import annotations

import pytest

from src.config.settings import Settings, _LEGACY_SECRET_KEYS, settings

# Every required field, so a Settings() built in-test doesn't fail on unrelated
# config. Values are throwaway.
_REQUIRED = {
    "JWT_SECRET_KEY": "test-jwt-secret",
    "OPENAI_API_KEY": "test-key",
}

# Env vars a developer's shell or .env might already hold, which would otherwise
# leak into tests that assert on defaults.
_GATEWAY_ENV = (
    "OPENAI_BASE_URL",
    "OPENAI_GATEWAY_BASE_URL",
    "PORTKEY_BASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_BEDROCK_API_KEY",
    "PORTKEY_BEDROCK_API_KEY",
    "OPENAI_SLUG",
    "OPENAI_BEDROCK_SLUG",
    "PORTKEY_BEDROCK_SLUG",
    "OPENAI_EXTRA_HEADERS",
    "OPENAI_API_KEY_HEADER",
    "OPENAI_STRUCTURED_OUTPUT_METHOD",
    "OPENAI_NO_TEMPERATURE_MODELS",
    "OPENAI_MODEL_PRICES",
    "MEMORY_EMBEDDING_DIMENSIONS",
)


def _settings_from_env(monkeypatch, **env: str) -> Settings:
    """Build a Settings from exactly the given env, ignoring the local .env."""
    for key in _GATEWAY_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in {**_REQUIRED, **env}.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


class TestLegacyEnvVars:
    @pytest.mark.parametrize(
        "legacy_key_var", ["OPENAI_BEDROCK_API_KEY", "PORTKEY_BEDROCK_API_KEY"]
    )
    def test_legacy_api_key_names_still_resolve(self, monkeypatch, legacy_key_var):
        # The legacy name alone must satisfy the required field.
        for key in _GATEWAY_ENV:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
        monkeypatch.setenv(legacy_key_var, "legacy-key")
        s = Settings(_env_file=None)  # type: ignore[call-arg]

        assert s.openai_api_key == "legacy-key"

    @pytest.mark.parametrize("legacy_url_var", ["OPENAI_GATEWAY_BASE_URL", "PORTKEY_BASE_URL"])
    def test_legacy_base_url_names_still_resolve(self, monkeypatch, legacy_url_var):
        s = _settings_from_env(monkeypatch, **{legacy_url_var: "https://gw.example/v1"})

        assert s.openai_base_url == "https://gw.example/v1"

    def test_current_names_win_over_legacy_ones(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch,
            PORTKEY_BASE_URL="https://legacy.example/v1",
            OPENAI_BASE_URL="https://current.example/v1",
        )

        assert s.openai_base_url == "https://current.example/v1"

    def test_every_renamed_field_is_covered_by_the_vault_remap(self):
        """The vault source bypasses AliasChoices, so it needs its own map.

        A field renamed without a `_LEGACY_SECRET_KEYS` entry would read fine
        from env and silently fall back to the default under Vault.
        """
        remapped = set(_LEGACY_SECRET_KEYS.values())

        assert remapped == {"openai_base_url", "openai_api_key", "openai_slug"}
        for field in remapped:
            assert field in Settings.model_fields


class TestLegacySlugFolding:
    """The slug moved into OPENAI_EXTRA_HEADERS, but deployments still set it
    the old way. Dropping it would not fail at startup — it would route to the
    wrong upstream, or get rejected, on the first real request."""

    @pytest.mark.parametrize(
        "slug_var", ["OPENAI_SLUG", "OPENAI_BEDROCK_SLUG", "PORTKEY_BEDROCK_SLUG"]
    )
    def test_legacy_slug_becomes_an_extra_header(self, monkeypatch, slug_var):
        s = _settings_from_env(monkeypatch, **{slug_var: "bedrock"})

        assert s.get_openai_headers()["x-portkey-slug"] == "bedrock"

    def test_explicit_extra_headers_win_over_the_legacy_slug(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch,
            PORTKEY_BEDROCK_SLUG="legacy-slug",
            OPENAI_EXTRA_HEADERS='{"x-portkey-slug": "explicit-slug"}',
        )

        assert s.get_openai_headers()["x-portkey-slug"] == "explicit-slug"

    def test_legacy_slug_also_restores_the_api_key_header(self, monkeypatch):
        """The whole legacy shape comes back, not just the slug.

        Restoring only the slug header would let the bearer-only default
        silently 401 every environment that never set OPENAI_API_KEY_HEADER —
        and it would fail on the first request, not at startup.
        """
        s = _settings_from_env(monkeypatch, OPENAI_API_KEY="k", PORTKEY_BEDROCK_SLUG="bedrock")

        assert s.get_openai_headers() == {
            "x-portkey-api-key": "k",
            "x-portkey-slug": "bedrock",
        }

    def test_an_explicitly_empty_key_header_beats_the_legacy_fallback(self, monkeypatch):
        """Anything stated explicitly wins — including an explicit empty value.

        This pins the `model_fields_set` check: "the operator set it to empty"
        and "the operator never mentioned it" must not collapse into the same
        case, or the fallback would be impossible to opt out of.
        """
        s = _settings_from_env(
            monkeypatch,
            OPENAI_API_KEY="k",
            PORTKEY_BEDROCK_SLUG="bedrock",
            OPENAI_API_KEY_HEADER="",
        )

        assert s.get_openai_headers() == {"x-portkey-slug": "bedrock"}


class TestAnyCompatibleEndpoint:
    """Pointing at any OpenAI-compatible endpoint must be pure configuration.

    Each of these covers a spot that used to be hardcoded to the gateway we
    happen to run, where the failure on a different endpoint was either a hard
    400 or — worse — silent.
    """

    def test_default_auth_is_a_plain_bearer(self, monkeypatch):
        """The headline promise: base_url + api_key and nothing else."""
        s = _settings_from_env(monkeypatch, OPENAI_BASE_URL="https://api.openai.com/v1")

        assert s.get_openai_headers() == {}

    def test_structured_output_method_defaults_to_function_calling(self):
        from src.service.llm import LLMService

        assert LLMService.structured_output_method() == "function_calling"

    def test_structured_output_method_is_configurable(self, monkeypatch):
        from src.service.llm import LLMService

        monkeypatch.setattr(settings, "openai_structured_output_method", "json_schema")

        assert LLMService.structured_output_method() == "json_schema"

    def test_unsupported_structured_output_method_fails_at_startup(self, monkeypatch):
        """Not on the first structured-output call, when it's a runtime error."""
        with pytest.raises(ValueError, match="openai_structured_output_method"):
            _settings_from_env(monkeypatch, OPENAI_STRUCTURED_OUTPUT_METHOD="freeform")

    def test_temperature_blocklist_is_extensible(self, monkeypatch):
        """A model outside the built-in list that rejects temperature is a hard
        400 that takes every agent using it offline."""
        from src.service.llm import LLMService

        assert LLMService._supports_temperature("local-reasoner-v2") is True

        monkeypatch.setattr(settings, "openai_no_temperature_models", "local-reasoner, other")

        assert LLMService._supports_temperature("local-reasoner-v2") is False
        # Built-ins survive the union, and unrelated models are untouched.
        assert LLMService._supports_temperature("claude-sonnet-5") is False
        assert LLMService._supports_temperature("claude-sonnet-4-6") is True

    def test_model_prices_can_be_configured(self, monkeypatch):
        """Otherwise every model a new endpoint serves is costed at zero."""
        from src.service.observability.cost import compute_cost

        assert compute_cost("my-local-model", 1_000_000, 1_000_000) == 0.0

        monkeypatch.setattr(settings, "openai_model_prices", {"my-local-model": (2.0, 6.0)})

        assert compute_cost("my-local-model", 1_000_000, 1_000_000) == pytest.approx(8.0)

    def test_configured_prices_override_the_built_in_table(self, monkeypatch):
        from src.service.observability.cost import compute_cost

        monkeypatch.setattr(settings, "openai_model_prices", {"claude-sonnet-4-6": (1.0, 1.0)})

        assert compute_cost("claude-sonnet-4-6", 1_000_000, 0) == pytest.approx(1.0)

    def test_blank_model_prices_do_not_break_startup(self, monkeypatch):
        s = _settings_from_env(monkeypatch, OPENAI_MODEL_PRICES="")

        assert s.openai_model_prices == {}

    def test_blank_embedding_dimensions_mean_omit(self, monkeypatch):
        """Blank must mean "don't send the parameter", not fail int parsing."""
        s = _settings_from_env(monkeypatch, MEMORY_EMBEDDING_DIMENSIONS="")

        assert s.memory_embedding_dimensions is None


class TestGatewayHeaders:
    def test_extra_headers_parse_from_json(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch,
            OPENAI_EXTRA_HEADERS='{"x-tenant": "acme", "x-portkey-slug": "bedrock"}',
        )

        headers = s.get_openai_headers()
        assert headers["x-tenant"] == "acme"
        assert headers["x-portkey-slug"] == "bedrock"

    def test_api_key_is_injected_into_the_configured_header(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch, OPENAI_API_KEY="sk-test", OPENAI_API_KEY_HEADER="x-portkey-api-key"
        )

        assert s.get_openai_headers()["x-portkey-api-key"] == "sk-test"

    def test_blank_extra_headers_do_not_break_startup(self, monkeypatch):
        """Orchestrators inject `OPENAI_EXTRA_HEADERS=` for absent values; an
        empty string must not fail JSON parsing and take the service down."""
        s = _settings_from_env(monkeypatch, OPENAI_EXTRA_HEADERS="   ")

        assert s.openai_extra_headers == {}

    def test_malformed_extra_headers_say_why(self, monkeypatch):
        """Blank is tolerated; genuine garbage still fails, with a usable message."""
        with pytest.raises(ValueError, match="must be a JSON object"):
            _settings_from_env(monkeypatch, OPENAI_EXTRA_HEADERS="x-slug: bedrock")

    def test_api_key_header_name_is_configurable(self, monkeypatch):
        s = _settings_from_env(
            monkeypatch, OPENAI_API_KEY="sk-test", OPENAI_API_KEY_HEADER="x-api-key"
        )

        headers = s.get_openai_headers()
        assert headers == {"x-api-key": "sk-test"}
        assert not any(name.startswith("x-portkey-") for name in headers)


class TestSingleGatewayRoute:
    """The direct-vendor providers and the Azure route were removed.

    `openai` / `anthropic` / `openai_gcp` and Azure all had no callers, and the
    anthropic branch was already broken (`langchain_anthropic` is not a
    dependency). Nothing should reintroduce a provider concept without also
    reintroducing the credentials it needs.
    """

    def test_create_llm_takes_no_provider(self):
        import inspect

        from src.service.llm import LLMService

        assert "provider" not in inspect.signature(LLMService.create_llm).parameters

    def test_removed_route_settings_are_gone(self):
        for field in ("openai_azure_api_key", "openai_azure_slug", "openai_gcp_api_key"):
            assert field not in Settings.model_fields

    def test_api_key_is_required(self, monkeypatch):
        """The gateway is unusable without it, so fail at startup, not at request."""
        for key in _GATEWAY_ENV:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")

        with pytest.raises(ValueError, match="openai_api_key"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_the_key_also_travels_as_the_bearer(self, monkeypatch):
        """The key must reach ChatOpenAI's api_key, not a placeholder.

        It used to be the literal "unused" — the gateway read the key from a
        header instead. Naming the setting `openai_api_key` only makes sense if
        it behaves like one.
        """
        from src.service import llm as llm_mod

        captured: dict = {}
        monkeypatch.setattr(llm_mod, "ChatOpenAI", lambda **kw: captured.update(kw))
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")

        llm_mod.LLMService.create_llm(model="some-model")

        assert captured["api_key"] == "sk-test"
        assert captured["base_url"] == settings.openai_base_url
