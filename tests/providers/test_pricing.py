"""Pin the pricing math so a typo in the table doesn't quietly mis-bill.

We pick a couple of round-number inputs and assert the *exact* Decimal output.
``pytest.approx`` would be wrong here — money math is exact.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from src.providers.pricing import (
    PRICING_TABLE,
    UnknownModelError,
    calculate_cost,
    estimate_cost,
)


def test_pricing_table_has_required_models() -> None:
    # If we ever drop one of these, the factory's default falls back to a model
    # that no longer prices — better to fail loudly here than at runtime.
    for model in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"):
        assert model in PRICING_TABLE


def test_calculate_cost_sonnet_known_input() -> None:
    # claude-sonnet-4-6: $3.00 / M input, $15.00 / M output.
    # 1,000,000 input + 1,000,000 output tokens => 3 + 15 = $18.00.
    cost = calculate_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    assert cost == Decimal("18.00")


def test_calculate_cost_small_request() -> None:
    # 100 input + 50 output tokens at sonnet pricing:
    # 100 * 3.00 / 1_000_000 + 50 * 15.00 / 1_000_000 = 0.0003 + 0.00075 = 0.00105
    cost = calculate_cost("claude-sonnet-4-6", 100, 50)
    assert cost == Decimal("0.00105")


def test_calculate_cost_unknown_model_raises() -> None:
    with pytest.raises(UnknownModelError):
        calculate_cost("claude-fictional-99", 1, 1)


def test_estimate_cost_uses_4_chars_per_token_heuristic() -> None:
    # 40 characters => ~10 tokens with the 4-chars-per-token rule.
    # output_ratio=1.0 means 10 output tokens too.
    # Sonnet: 10 * 3.00 / 1_000_000 + 10 * 15.00 / 1_000_000 = 30e-6 + 150e-6 = 0.00018
    text = "a" * 40
    cost = estimate_cost("claude-sonnet-4-6", text)
    assert cost == Decimal("0.00018")


def test_estimate_cost_respects_output_ratio() -> None:
    # output_ratio=0.5 halves output tokens — half of the output cost.
    text = "a" * 40  # 10 input tokens, 5 output tokens at ratio 0.5
    cost = estimate_cost("claude-sonnet-4-6", text, output_ratio=0.5)
    # 10 * 3e-6 + 5 * 15e-6 = 30e-6 + 75e-6 = 0.000105
    assert cost == Decimal("0.000105")
