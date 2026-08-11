"""Tests for the ``portkey_anthropic_base_url`` normalization property.

Codifies the Phase 1 diagnostic finding: Portkey+Bedrock rejects requests
to ``/v1/v1/messages`` (AWS Coral ``UnknownOperationException``) because
the Anthropic-SDK-shaped CLI appends ``/v1/messages`` on top of whatever
``ANTHROPIC_BASE_URL`` we hand it. The property strips a trailing ``/v1``
from ``portkey_base_url`` so SDK-shape consumers get the gateway root.

These tests are PURE — no .env loading, no LLM calls — they patch
``portkey_base_url`` and assert the derived property.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Canonical case — repo default
        ("https://gateway.example.com/v1", "https://gateway.example.com"),
        # Trailing slash after /v1
        ("https://gateway.example.com/v1/", "https://gateway.example.com"),
        # Already root — no-op
        ("https://gateway.example.com", "https://gateway.example.com"),
        # Root with trailing slash — slash stripped, no /v1 to strip
        ("https://gateway.example.com/", "https://gateway.example.com"),
        # Non-v1 version suffix — only /v1 is stripped
        ("https://gateway.example.com/v2", "https://gateway.example.com/v2"),
        # Mid-path /v1 — only TRAILING /v1 is stripped
        (
            "https://gateway.example.com/v1/messages",
            "https://gateway.example.com/v1/messages",
        ),
        # Pathological prefix — /v100 must not match /v1 stripping
        ("https://gateway.example.com/v100", "https://gateway.example.com/v100"),
        # Custom path with /v1 suffix (unusual but valid input)
        (
            "https://portkey.example.com/gateway/v1",
            "https://portkey.example.com/gateway",
        ),
    ],
)
def test_portkey_anthropic_base_url_strips_trailing_v1(monkeypatch, raw, expected):
    from src.config.settings import settings

    monkeypatch.setattr(settings, "portkey_base_url", raw)
    assert settings.portkey_anthropic_base_url == expected


def test_portkey_anthropic_base_url_does_not_mutate_source(monkeypatch):
    """Reading the derived property must not modify portkey_base_url itself.

    LangChain paths still read the raw value, which MUST remain intact.
    """
    from src.config.settings import settings

    monkeypatch.setattr(settings, "portkey_base_url", "https://gateway.example.com/v1")

    # Call the property twice — second call must see the same raw value
    _ = settings.portkey_anthropic_base_url
    assert settings.portkey_base_url == "https://gateway.example.com/v1"
    _ = settings.portkey_anthropic_base_url
    assert settings.portkey_base_url == "https://gateway.example.com/v1"
