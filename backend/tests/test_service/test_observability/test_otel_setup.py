"""Unit tests for observability/otel_setup.py."""

import src.service.observability.otel_setup as otel_setup_mod
from src.service.observability.otel_setup import setup_tracing, shutdown_tracing


def test_setup_tracing_is_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(otel_setup_mod.settings, "otel_enabled", False)
    # Should not raise and should return without doing anything
    setup_tracing(None)


def test_setup_tracing_idempotent(monkeypatch):
    # Reset the module-level sentinel
    monkeypatch.setattr(otel_setup_mod, "_CONFIGURED", False)
    monkeypatch.setattr(otel_setup_mod.settings, "otel_enabled", True)
    monkeypatch.setattr(otel_setup_mod.settings, "trace_storage_enabled", False)
    monkeypatch.setattr(otel_setup_mod.settings, "langfuse_enabled", False)
    # First call configures
    setup_tracing(None)
    assert otel_setup_mod._CONFIGURED is True
    # Second call returns early without error
    setup_tracing(None)
    shutdown_tracing()
