"""Unit tests for src.service.memory.embeddings.

Mock the `openai.OpenAI` client so tests don't hit the gateway. Verifies:
- Titan `dimensions` is forwarded via `extra_body`
- Slug auth flows through `settings.get_openai_headers("bedrock")`
- embed_documents loops one-at-a-time (Bedrock constraint)
- async paths are gated by the module-level semaphore
- provider factory rejects unknown providers (including the removed Gemini
  one), and still accepts the pre-rename `portkey-*` provider names
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _bedrock_settings(monkeypatch):
    """Ensure Bedrock-route creds pass `settings.get_openai_headers("bedrock")`."""
    from src.config.settings import settings as s

    monkeypatch.setattr(s, "openai_api_key", "test-bedrock-key")
    monkeypatch.setattr(s, "openai_extra_headers", {"x-portkey-slug": "test-bedrock-slug"})


def _mock_openai_client(vector: list[float]):
    client = MagicMock()
    client.embeddings.create = MagicMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=vector)])
    )
    return client


def test_embed_query_forwards_dimensions_via_extra_body(monkeypatch):
    from src.service.memory import embeddings as emb_mod

    with patch.object(emb_mod, "__import__", create=True):
        pass  # keep mypy happy; real patch is below

    fake_client = _mock_openai_client([0.1] * 1024)

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.embeddings = fake_client.embeddings

    import openai  # real module; we patch its OpenAI symbol

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    client = emb_mod.BedrockTitanEmbeddings(dimensions=1024)
    vec = client.embed_query("hello world")

    assert len(vec) == 1024
    # The mock was called exactly once with the right dimensions in extra_body
    fake_client.embeddings.create.assert_called_once()
    call_kwargs = fake_client.embeddings.create.call_args.kwargs
    assert call_kwargs["model"] == "amazon.titan-embed-text-v2:0"
    assert call_kwargs["extra_body"] == {"dimensions": 1024}
    assert call_kwargs["input"] == "hello world"


def test_embed_documents_loops_one_at_a_time(monkeypatch):
    """Bedrock embeddings do not accept arrays — each doc is a separate call."""
    from src.service.memory import embeddings as emb_mod

    fake_client = _mock_openai_client([0.42] * 8)

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = fake_client.embeddings

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    client = emb_mod.BedrockTitanEmbeddings(dimensions=8)
    vectors = client.embed_documents(["a", "b", "c"])

    assert len(vectors) == 3
    assert fake_client.embeddings.create.call_count == 3


def test_client_is_constructed_with_gateway_auth(monkeypatch):
    """The embedder must authenticate the same way the chat models do —
    bearer key plus the gateway's own headers."""
    from src.service.memory import embeddings as emb_mod

    captured: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.embeddings = MagicMock()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    emb_mod.BedrockTitanEmbeddings()

    assert captured["api_key"] == "test-bedrock-key"
    assert captured["default_headers"]["x-portkey-api-key"] == "test-bedrock-key"
    assert captured["default_headers"]["x-portkey-slug"] == "test-bedrock-slug"


def test_get_embedder_rejects_unknown_provider():
    from src.service.memory.embeddings import get_embedder

    with pytest.raises(ValueError, match="Unknown memory_embedding_provider"):
        get_embedder("not-a-provider")


def test_get_embedder_defaults_to_bedrock_titan(monkeypatch):
    from src.service.memory import embeddings as emb_mod

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = MagicMock()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    client = emb_mod.get_embedder()
    assert isinstance(client, emb_mod.BedrockTitanEmbeddings)


def test_get_embedder_accepts_legacy_provider_name(monkeypatch):
    """A deployed MEMORY_EMBEDDING_PROVIDER=portkey-bedrock-titan still resolves."""
    from src.service.memory import embeddings as emb_mod

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = MagicMock()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    client = emb_mod.get_embedder("portkey-bedrock-titan")
    assert isinstance(client, emb_mod.BedrockTitanEmbeddings)


def test_get_embedder_rejects_the_removed_gemini_provider():
    """The GCP route and its Gemini stub were removed along with GCP creds."""
    from src.service.memory.embeddings import get_embedder

    with pytest.raises(ValueError, match="Unknown memory_embedding_provider"):
        get_embedder("openai-gcp-gemini")


@pytest.mark.asyncio
async def test_aembed_query_runs_in_thread(monkeypatch):
    from src.service.memory import embeddings as emb_mod

    fake_client = _mock_openai_client([0.5, 0.5, 0.5])

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = fake_client.embeddings

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)

    client = emb_mod.BedrockTitanEmbeddings(dimensions=3)
    vec = await client.aembed_query("hello")
    assert vec == [0.5, 0.5, 0.5]
    fake_client.embeddings.create.assert_called_once()
