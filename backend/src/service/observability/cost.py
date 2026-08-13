"""Per-model USD cost calculation.

Prices are in USD per 1M tokens, sourced from provider list prices as of
2026-04. Update alongside model rollouts. Accuracy bounds documented in the
Phase 0 operator guide: ±2% when driven by `response_metadata.usage` (post-call
authoritative), ±15% when driven by `tiktoken` pre-call estimation.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# Canonical model → (input $/1M, output $/1M)
_PRICE_TABLE_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    # Anthropic Claude (list prices via Bedrock; the gateway passes through)
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-6": (15.00, 75.00),
    # OpenAI models (approximate; negotiated enterprise rates may differ). Not
    # currently reachable — every agent runs on the Bedrock route — but kept so
    # a gpt-* rollout doesn't silently report zero cost.
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-mini": (0.25, 2.00),
}


# Bedrock + OpenAI model-id → canonical-name mapping.
_MODEL_ALIASES: dict[str, str] = {
    # Bedrock-flavored Claude model IDs
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "claude-haiku-4-5",
    "anthropic.claude-haiku-4-5-20251001-v1:0": "claude-haiku-4-5",
    "us.anthropic.claude-sonnet-4-6": "claude-sonnet-4-6",
    "anthropic.claude-sonnet-4-6": "claude-sonnet-4-6",
    "us.anthropic.claude-sonnet-4-6-v1": "claude-sonnet-4-6",
    "us.anthropic.claude-opus-4-6-v1": "claude-opus-4-6",
    "anthropic.claude-opus-4-6-v1": "claude-opus-4-6",
    # Anthropic-native aliases
    "claude-haiku-4-5-20251001": "claude-haiku-4-5",
    "claude-sonnet-4-6-20251001": "claude-sonnet-4-6",
}


def _canonicalize(model: str) -> str:
    """Resolve provider-flavored model IDs to a canonical lookup key."""
    if model in _PRICE_TABLE_USD_PER_MTOK:
        return model
    if model in _MODEL_ALIASES:
        return _MODEL_ALIASES[model]
    # Prefix heuristic: strip region and version suffixes
    for alias, canonical in _MODEL_ALIASES.items():
        if model.startswith(alias.split(":")[0]):
            return canonical
    return model


def _lookup_price(model: str, canonical: str) -> tuple[float, float] | None:
    """Resolve a price, letting configuration override the built-in table.

    `OPENAI_MODEL_PRICES` is read here rather than merged at import so it stays
    overridable at runtime and in tests. It is matched against the raw model id
    first: an operator configuring prices for their own endpoint writes the ids
    that endpoint actually reports, not our canonical names.
    """
    from src.config.settings import settings

    overrides = settings.openai_model_prices
    return (
        overrides.get(model) or overrides.get(canonical) or _PRICE_TABLE_USD_PER_MTOK.get(canonical)
    )


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return USD cost for a single LLM call.

    Returns 0.0 if the model is unknown so unknown-model calls don't crash the
    observability path; the caller can detect zero + unknown-model via the logs.
    Point the deployment at a different endpoint and every model it serves is
    unknown until `OPENAI_MODEL_PRICES` names it.
    """
    canonical = _canonicalize(model)
    price = _lookup_price(model, canonical)
    if price is None:
        logger.debug("cost: unknown model '%s' (canonical '%s') -> 0.0 USD", model, canonical)
        return 0.0
    input_price, output_price = price
    cost = (input_tokens / 1_000_000.0) * input_price + (output_tokens / 1_000_000.0) * output_price
    return round(cost, 6)
