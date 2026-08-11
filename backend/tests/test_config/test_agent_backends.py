"""Tests for agent_backends resolver."""

import logging

import pytest

from src.config import agent_backends as ab
from src.config.agent_backends import AgentBackend, resolve_agent_backend
from src.config.settings import settings


@pytest.fixture(autouse=True)
def _reset_settings():
    """Snapshot + restore backend settings around each test."""
    original = (
        settings.coder_backend,
        settings.orchestrator_backend,
    )
    yield
    (
        settings.coder_backend,
        settings.orchestrator_backend,
    ) = original


def test_default_is_langchain_for_all_known_agents():
    assert resolve_agent_backend("coder") is AgentBackend.LANGCHAIN
    assert resolve_agent_backend("orchestrator") is AgentBackend.LANGCHAIN


def test_unlisted_agent_returns_langchain():
    # coordinator, sql_agent, summarizer don't have feature flags in Phase 0
    assert resolve_agent_backend("coordinator") is AgentBackend.LANGCHAIN
    assert resolve_agent_backend("sql_agent") is AgentBackend.LANGCHAIN
    assert resolve_agent_backend("summarizer") is AgentBackend.LANGCHAIN


def test_override_via_settings_picks_up_sdk():
    settings.coder_backend = "sdk"
    assert resolve_agent_backend("coder") is AgentBackend.SDK
    # Peer agents unaffected
    assert resolve_agent_backend("orchestrator") is AgentBackend.LANGCHAIN


def test_invalid_value_falls_back_with_warning(caplog):
    settings.coder_backend = "not-a-real-backend"
    with caplog.at_level(logging.WARNING, logger=ab.__name__):
        result = resolve_agent_backend("coder")
    assert result is AgentBackend.LANGCHAIN
    assert any("not-a-real-backend" in rec.message for rec in caplog.records)


def test_enum_is_string_compatible():
    # Important for span attribute serialization
    assert AgentBackend.LANGCHAIN.value == "langchain"
    assert AgentBackend.SDK.value == "sdk"
    assert str(AgentBackend.LANGCHAIN.value) == "langchain"


# ---------------------------------------------------------------------------
# Phase 2 Workstream B — orchestrator_backend_context precedence + isolation
# ---------------------------------------------------------------------------


def test_orchestrator_backend_context_takes_precedence_over_settings():
    """The orchestrator ContextVar must win over settings, like the coder one."""
    from src.config.agent_backends import orchestrator_backend_context

    settings.orchestrator_backend = "langchain"
    token = orchestrator_backend_context.set(AgentBackend.SDK)
    try:
        assert resolve_agent_backend("orchestrator") is AgentBackend.SDK
        # Settings untouched
        assert settings.orchestrator_backend == "langchain"
    finally:
        orchestrator_backend_context.reset(token)

    # After reset, falls back to settings
    assert resolve_agent_backend("orchestrator") is AgentBackend.LANGCHAIN


def test_orchestrator_context_does_not_affect_coder_resolution():
    """Each worker has its own ContextVar; setting orchestrator must not
    leak into ``resolve_agent_backend('coder')`` — regression pin for the
    2x2 eval matrix (coder=LC, orch=SDK) which would otherwise corrupt
    the coder run."""
    from src.config.agent_backends import coder_backend_context, orchestrator_backend_context

    settings.coder_backend = "langchain"
    settings.orchestrator_backend = "langchain"

    orch_token = orchestrator_backend_context.set(AgentBackend.SDK)
    try:
        assert resolve_agent_backend("orchestrator") is AgentBackend.SDK
        assert resolve_agent_backend("coder") is AgentBackend.LANGCHAIN
    finally:
        orchestrator_backend_context.reset(orch_token)

    # Conversely, setting only the coder override must not leak into orchestrator.
    coder_token = coder_backend_context.set(AgentBackend.SDK)
    try:
        assert resolve_agent_backend("coder") is AgentBackend.SDK
        assert resolve_agent_backend("orchestrator") is AgentBackend.LANGCHAIN
    finally:
        coder_backend_context.reset(coder_token)


def test_invalid_orchestrator_setting_falls_back(caplog):
    settings.orchestrator_backend = "bogus"
    with caplog.at_level(logging.WARNING, logger=ab.__name__):
        result = resolve_agent_backend("orchestrator")
    assert result is AgentBackend.LANGCHAIN
    assert any("bogus" in rec.message for rec in caplog.records)
