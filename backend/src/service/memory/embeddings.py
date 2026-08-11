"""Embedding providers for the memory pipeline.

Phase 0.5 uses Titan V2 via the Portkey Bedrock gateway. The class below wraps
`openai.OpenAI.embeddings.create()` because Bedrock's embedding endpoint does
not accept arrays — each document goes through one at a time. A module-level
`asyncio.Semaphore` bounds concurrency against Portkey TPS.

Governance invariant: all auth goes through `settings.get_portkey_headers()` —
the same helper `LLMService.create_llm` uses. Never call `createHeaders` with
`virtual_key` (deprecated).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.config.settings import settings

logger = logging.getLogger(__name__)


class PortkeyBedrockTitanEmbeddings(Embeddings):
    """Titan V2 embeddings via the Portkey Bedrock gateway.

    - Synchronous `embed_documents`/`embed_query` use the OpenAI SDK's blocking
      `embeddings.create(...)` — suitable for `asyncio.to_thread` from the async
      helpers below.
    - Async paths are gated by a module-level semaphore so a single turn cannot
      monopolize Portkey capacity; the cap is `settings.memory_embedding_concurrency`.
    - Titan V2's `dimensions` parameter is forwarded via `extra_body` since it
      is not a standard OpenAI SDK field.
    """

    _semaphore: asyncio.Semaphore | None = None

    def __init__(
        self,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai is required for PortkeyBedrockTitanEmbeddings. Install with: uv add openai"
            ) from exc

        headers = settings.get_portkey_headers(provider="bedrock")
        self._client = openai.OpenAI(
            api_key="portkey",
            base_url=settings.portkey_base_url,
            default_headers=headers,
            timeout=60.0,
            max_retries=3,
        )
        self._model = model or settings.memory_embedding_model
        self._dimensions = dimensions or settings.memory_embedding_dimensions
        if PortkeyBedrockTitanEmbeddings._semaphore is None:
            PortkeyBedrockTitanEmbeddings._semaphore = asyncio.Semaphore(
                settings.memory_embedding_concurrency
            )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            input=text,
            model=self._model,
            extra_body={"dimensions": self._dimensions},
        )
        return response.data[0].embedding

    async def aembed_query(self, text: str) -> list[float]:
        assert PortkeyBedrockTitanEmbeddings._semaphore is not None
        async with PortkeyBedrockTitanEmbeddings._semaphore:
            return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(await asyncio.gather(*(self.aembed_query(t) for t in texts)))


class _GeminiEmbeddingsStub(Embeddings):
    """Reserved GCP Gemini implementation — emitted for future A/B comparison."""

    def __init__(self, **_: Any) -> None:
        raise NotImplementedError(
            "portkey-gcp-gemini embeddings are reserved for a later phase; "
            "Phase 0.5 ships with portkey-bedrock-titan only"
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:  # pragma: no cover
        raise NotImplementedError


def get_embedder(provider: str | None = None) -> Embeddings:
    """Return the configured embeddings client.

    Default: `settings.memory_embedding_provider`. Unknown providers raise
    ValueError so a mistyped env var fails fast instead of silently substituting.
    """
    provider = (provider or settings.memory_embedding_provider).lower()
    if provider in ("portkey-bedrock-titan", "bedrock-titan", "titan"):
        return PortkeyBedrockTitanEmbeddings()
    if provider in ("portkey-gcp-gemini", "gcp-gemini", "gemini"):
        return _GeminiEmbeddingsStub()
    raise ValueError(
        f"Unknown memory_embedding_provider '{provider}'. Supported: "
        "portkey-bedrock-titan | portkey-gcp-gemini"
    )
