"""Tests for ChatRequest coder_backend field (Phase 2, Workstream A).

Pins the per-request coder backend override contract:
- Defaults to None (backward compatible with all existing clients).
- Accepts 'sdk' and 'langchain'.
- Rejects any other string at the pydantic boundary (422 at the API layer).
"""

import pytest
from pydantic import ValidationError

from src.models.api import ChatRequest


def test_chat_request_coder_backend_defaults_to_none():
    """Field is optional — omitting it leaves None so the resolver falls back to settings."""
    req = ChatRequest(message="hi")
    assert req.coder_backend is None


def test_chat_request_coder_backend_accepts_sdk():
    req = ChatRequest(message="hi", coder_backend="sdk")
    assert req.coder_backend == "sdk"


def test_chat_request_coder_backend_accepts_langchain():
    req = ChatRequest(message="hi", coder_backend="langchain")
    assert req.coder_backend == "langchain"


def test_chat_request_coder_backend_accepts_explicit_none():
    """Explicit null from the wire is equivalent to omitting the field."""
    req = ChatRequest.model_validate({"message": "hi", "coder_backend": None})
    assert req.coder_backend is None


def test_chat_request_coder_backend_rejects_invalid():
    """Any non-enum value must be rejected at the request boundary."""
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", coder_backend="anthropic")  # type: ignore[arg-type]


def test_chat_request_coder_backend_rejects_empty_string():
    """Empty string is not a valid backend — pydantic rejects."""
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", coder_backend="")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Phase 2 Workstream B — orchestrator_backend mirrors the coder_backend contract
# ---------------------------------------------------------------------------


def test_chat_request_orchestrator_backend_defaults_to_none():
    req = ChatRequest(message="hi")
    assert req.orchestrator_backend is None


def test_chat_request_orchestrator_backend_accepts_sdk():
    req = ChatRequest(message="hi", orchestrator_backend="sdk")
    assert req.orchestrator_backend == "sdk"


def test_chat_request_orchestrator_backend_accepts_langchain():
    req = ChatRequest(message="hi", orchestrator_backend="langchain")
    assert req.orchestrator_backend == "langchain"


def test_chat_request_orchestrator_backend_rejects_invalid():
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", orchestrator_backend="anthropic")  # type: ignore[arg-type]


def test_chat_request_both_backends_independent():
    """coder_backend and orchestrator_backend must be settable independently."""
    req = ChatRequest(message="hi", coder_backend="sdk", orchestrator_backend="langchain")
    assert req.coder_backend == "sdk"
    assert req.orchestrator_backend == "langchain"
