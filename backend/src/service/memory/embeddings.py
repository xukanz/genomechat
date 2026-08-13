"""Embedding provider for the memory pipeline.

Talks to whatever OpenAI-compatible endpoint `settings.openai_base_url` points
at, using the same auth as the chat models. Documents go one at a time because
Bedrock's embedding endpoint does not accept arrays — harmless on endpoints that
would have taken a batch, and required on the one we run. A module-level
`asyncio.Semaphore` bounds concurrency against endpoint TPS.

Governance invariant: all auth goes through `settings.get_openai_headers()` —
the same helper `LLMService.create_llm` uses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.embeddings import Embeddings

from src.config.settings import settings

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbeddings(Embeddings):
    """Embeddings via the configured OpenAI-compatible endpoint.

    - Synchronous `embed_documents`/`embed_query` use the OpenAI SDK's blocking
      `embeddings.create(...)` — suitable for `asyncio.to_thread` from the async
      helpers below.
    - Async paths are gated by a module-level semaphore so a single turn cannot
      monopolize endpoint capacity; the cap is `settings.memory_embedding_concurrency`.
    - `dimensions` is forwarded only when configured — see `_request_kwargs`.
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
                "openai is required for OpenAICompatibleEmbeddings. Install with: uv add openai"
            ) from exc

        self._client = openai.OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            default_headers=settings.get_openai_headers(),
            timeout=60.0,
            max_retries=3,
        )
        self._model = model or settings.memory_embedding_model
        self._dimensions = (
            dimensions if dimensions is not None else settings.memory_embedding_dimensions
        )
        if OpenAICompatibleEmbeddings._semaphore is None:
            OpenAICompatibleEmbeddings._semaphore = asyncio.Semaphore(
                settings.memory_embedding_concurrency
            )

    def _request_kwargs(self, text: str) -> dict[str, Any]:
        """Build the request, omitting `dimensions` when it isn't configured.

        Titan V2 and OpenAI's text-embedding-3-* both read `dimensions`, but an
        endpoint that doesn't know the parameter rejects the entire request — so
        it is only sent when someone asked for it.
        """
        kwargs: dict[str, Any] = {"input": text, "model": self._model}
        if self._dimensions is not None:
            kwargs["extra_body"] = {"dimensions": self._dimensions}
        return kwargs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        response = self._client.embeddings.create(**self._request_kwargs(text))
        embedding: list[float] = response.data[0].embedding
        return embedding

    async def aembed_query(self, text: str) -> list[float]:
        assert OpenAICompatibleEmbeddings._semaphore is not None
        async with OpenAICompatibleEmbeddings._semaphore:
            return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return list(await asyncio.gather(*(self.aembed_query(t) for t in texts)))


def get_embedder() -> Embeddings:
    """Return the embeddings client for the configured endpoint.

    There is no provider registry: every endpoint we support speaks the OpenAI
    embeddings API, so the model name (`MEMORY_EMBEDDING_MODEL`) is the only
    thing that varies.
    """
    return OpenAICompatibleEmbeddings()
