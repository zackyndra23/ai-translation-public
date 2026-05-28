"""Token pricing for cost accounting.

Source of truth: https://docs.anthropic.com/en/docs/about-claude/pricing
Last refreshed: 2026-05-20. If you update the table, also update this date.

We use ``Decimal`` everywhere because money should never be ``float``: even a
$0.0001-per-token error compounds across millions of tokens, and ``float``
arithmetic doesn't have associativity guarantees the way ``Decimal`` does.

The table is intentionally a plain ``dict``, not a Pydantic model: callers
should never mutate it, and the simpler shape makes it easy to import in unit
tests for parameterised assertions.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict


class PricePerMillionTokens(TypedDict):
    """Anthropic publishes per-1M-token rates in USD. We keep the same unit so
    a price table copied from their docs stays recognisable.
    """

    input: Decimal
    output: Decimal


# Per ADR-001 we own this table. When Anthropic releases a new model we add a
# row here; the cost will then start flowing through ``calculate_cost`` without
# any provider-code changes.
#
# Note: prices are USD per 1,000,000 tokens. The numbers below are list prices
# (no enterprise / committed-spend discount). If a deployment qualifies for a
# discount, override this table via dependency injection rather than editing it
# globally — different envs may negotiate different rates.
PRICING_TABLE: dict[str, PricePerMillionTokens] = {
    "claude-opus-4-7": {"input": Decimal("15.00"), "output": Decimal("75.00")},
    "claude-sonnet-4-6": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-haiku-4-5": {"input": Decimal("1.00"), "output": Decimal("5.00")},
}

# Rule-of-thumb used in pre-flight estimates: ~4 characters per token for
# English/Romance text. Asian / Indonesian text tends to compress better
# (fewer tokens per character), so estimates will *over*-budget for those,
# which is the safer direction for budget gates.
_CHARS_PER_TOKEN_ESTIMATE = 4


class UnknownModelError(KeyError):
    """Raised when ``calculate_cost`` is asked about a model we don't price.

    A ``KeyError`` subclass so it integrates with normal ``dict``-shaped error
    handling, but distinguishable from a generic missing-key bug.
    """


def _per_million_to_per_token(price_per_million: Decimal) -> Decimal:
    return price_per_million / Decimal(1_000_000)


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Exact post-call cost in USD.

    Use this from inside a provider after the SDK has returned actual usage.
    Raises :class:`UnknownModelError` rather than returning ``0`` so a missing
    pricing entry is loud, not silent.
    """
    try:
        rates = PRICING_TABLE[model_id]
    except KeyError as e:
        raise UnknownModelError(
            f"No pricing entry for model {model_id!r}. "
            f"Add it to PRICING_TABLE in src/providers/pricing.py."
        ) from e

    input_cost = _per_million_to_per_token(rates["input"]) * Decimal(input_tokens)
    output_cost = _per_million_to_per_token(rates["output"]) * Decimal(output_tokens)
    return input_cost + output_cost


def estimate_cost(model_id: str, text: str, output_ratio: float = 1.0) -> Decimal:
    """Pre-flight estimate in USD before any API call.

    ``output_ratio`` is the expected ratio of output tokens to input tokens.
    Translation typically lands near 1.0 (output is the same length as input).
    Summarisation would use <<1; chain-of-thought would use >>1.
    """
    estimated_input_tokens = max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)
    estimated_output_tokens = int(estimated_input_tokens * output_ratio)
    return calculate_cost(model_id, estimated_input_tokens, estimated_output_tokens)
