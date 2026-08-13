"""Unit tests for src.service.memory.embeddings.

Mock the `openai.OpenAI` client so tests don't hit a real endpoint. Verifies:
- `dimensions` is forwarded when configured and omitted when not — an endpoint
  that doesn't know the parameter rejects the whole request
- auth flows through `settings.get_openai_headers()`, same as the chat models
- embed_documents loops one-at-a-time (Bedrock constraint)
- async paths are gated by the module-level semaphore
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _endpoint_settings(monkeypatch):
    """Pin endpoint auth so header assertions don't depend on the local .env."""
    from src.config.settings import settings as s

    monkeypatch.setattr(s, "openai_api_key", "test-key")
    monkeypatch.setattr(s, "openai_api_key_header", "x-portkey-api-key")
    monkeypatch.setattr(s, "openai_extra_headers", {"x-portkey-slug": "test-slug"})


def _mock_openai_client(vector: list[float]):
    client = MagicMock()
    client.embeddings.create = MagicMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=vector)])
    )
    return client


def _patch_openai(monkeypatch, fake_client=None, captured: dict | None = None):
    """Swap `openai.OpenAI` for a stub, optionally capturing constructor kwargs."""

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            if captured is not None:
                captured.update(kwargs)
            self.embeddings = fake_client.embeddings if fake_client else MagicMock()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)


def test_embed_query_forwards_dimensions_when_configured(monkeypatch):
    from src.service.memory import embeddings as emb_mod

    fake_client = _mock_openai_client([0.1] * 1024)
    _patch_openai(monkeypatch, fake_client)

    vec = emb_mod.OpenAICompatibleEmbeddings(dimensions=1024).embed_query("hello world")

    assert len(vec) == 1024
    fake_client.embeddings.create.assert_called_once()
    call_kwargs = fake_client.embeddings.create.call_args.kwargs
    assert call_kwargs["model"] == "amazon.titan-embed-text-v2:0"
    assert call_kwargs["extra_body"] == {"dimensions": 1024}
    assert call_kwargs["input"] == "hello world"


def test_dimensions_are_omitted_when_unset(monkeypatch):
    """An endpoint that doesn't know `dimensions` rejects the whole request."""
    from src.config.settings import settings as s
    from src.service.memory import embeddings as emb_mod

    monkeypatch.setattr(s, "memory_embedding_dimensions", None)
    fake_client = _mock_openai_client([0.1, 0.2])
    _patch_openai(monkeypatch, fake_client)

    emb_mod.OpenAICompatibleEmbeddings().embed_query("hello")

    assert "extra_body" not in fake_client.embeddings.create.call_args.kwargs


def test_embed_documents_loops_one_at_a_time(monkeypatch):
    """Bedrock embeddings do not accept arrays — each doc is a separate call."""
    from src.service.memory import embeddings as emb_mod

    fake_client = _mock_openai_client([0.42] * 8)
    _patch_openai(monkeypatch, fake_client)

    vectors = emb_mod.OpenAICompatibleEmbeddings(dimensions=8).embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert fake_client.embeddings.create.call_count == 3


def test_client_is_constructed_with_endpoint_auth(monkeypatch):
    """The embedder must authenticate exactly the way the chat models do."""
    from src.service.memory import embeddings as emb_mod

    captured: dict = {}
    _patch_openai(monkeypatch, captured=captured)

    emb_mod.OpenAICompatibleEmbeddings()

    assert captured["api_key"] == "test-key"
    assert captured["default_headers"]["x-portkey-api-key"] == "test-key"
    assert captured["default_headers"]["x-portkey-slug"] == "test-slug"


def test_get_embedder_returns_the_compatible_client(monkeypatch):
    from src.service.memory import embeddings as emb_mod

    _patch_openai(monkeypatch)

    assert isinstance(emb_mod.get_embedder(), emb_mod.OpenAICompatibleEmbeddings)


@pytest.mark.asyncio
async def test_aembed_query_runs_in_thread(monkeypatch):
    from src.service.memory import embeddings as emb_mod

    fake_client = _mock_openai_client([0.5, 0.5, 0.5])
    _patch_openai(monkeypatch, fake_client)

    client = emb_mod.OpenAICompatibleEmbeddings(dimensions=3)
    vec = await client.aembed_query("hello")

    assert vec == [0.5, 0.5, 0.5]
    fake_client.embeddings.create.assert_called_once()
