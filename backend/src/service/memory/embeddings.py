"""Embedding providers for the memory pipeline.

Phase 0.5 uses Titan V2 via the Bedrock route on the OpenAI-compatible gateway.
The class below wraps `openai.OpenAI.embeddings.create()` because Bedrock's
embedding endpoint does not accept arrays — each document goes through one at a
time. A module-level `asyncio.Semaphore` bounds concurrency against gateway TPS.

Governance invariant: all auth goes through `settings.get_openai_headers()` —
the same helper `LLMService.create_llm` uses.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.embeddings import Embeddings

from src.config.settings import settings

logger = logging.getLogger(__name__)


class BedrockTitanEmbeddings(Embeddings):
    """Titan V2 embeddings via the Bedrock route on the OpenAI-compatible gateway.

    - Synchronous `embed_documents`/`embed_query` use the OpenAI SDK's blocking
      `embeddings.create(...)` — suitable for `asyncio.to_thread` from the async
      helpers below.
    - Async paths are gated by a module-level semaphore so a single turn cannot
      monopolize gateway capacity; the cap is `settings.memory_embedding_concurrency`.
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
                "openai is required for BedrockTitanEmbeddings. Install with: uv add openai"
            ) from exc

        headers = settings.get_openai_headers(provider="bedrock")
        self._client = openai.OpenAI(
            # Inert — the gateway authenticates from `headers`, but the OpenAI
            # client requires a non-empty api_key.
            api_key="unused",
            base_url=settings.openai_gateway_base_url,
            default_headers=headers,
            timeout=60.0,
            max_retries=3,
        )
        self._model = model or settings.memory_embedding_model
        self._dimensions = dimensions or settings.memory_embedding_dimensions
        if BedrockTitanEmbeddings._semaphore is None:
            BedrockTitanEmbeddings._semaphore = asyncio.Semaphore(
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
        assert BedrockTitanEmbeddings._semaphore is not None
        async with BedrockTitanEmbeddings._semaphore:
            return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(await asyncio.gather(*(self.aembed_query(t) for t in texts)))


def get_embedder(provider: str | None = None) -> Embeddings:
    """Return the configured embeddings client.

    Default: `settings.memory_embedding_provider`. Unknown providers raise
    ValueError so a mistyped env var fails fast instead of silently substituting.
    """
    provider = (provider or settings.memory_embedding_provider).lower()
    # `portkey-*` are the pre-rename names, still accepted so a deployed
    # MEMORY_EMBEDDING_PROVIDER keeps resolving.
    if provider in ("openai-bedrock-titan", "portkey-bedrock-titan", "bedrock-titan", "titan"):
        return BedrockTitanEmbeddings()
    raise ValueError(
        f"Unknown memory_embedding_provider '{provider}'. Supported: openai-bedrock-titan"
    )
