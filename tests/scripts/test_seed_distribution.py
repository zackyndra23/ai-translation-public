"""Sub-proyek K seed distribution check.

Verifies the stratified allowed_language distribution across 57 profiles:
  - 12 profiles: ["id", "en"]
  - 12 profiles: ["ms", "en"]
  - 11 profiles: ["th", "en"]
  - 11 profiles: ["id", "ms", "th", "en"]
  - 11 profiles: None (all langs allowed)

And verifies the canonical 3-step prompt_applied order constant lives in
the seed module so any future drift between Pydantic validator and seed
output is impossible (single source of truth).
"""

from __future__ import annotations

import pytest

from scripts.seed_tenant_data import (
    ALLOWED_LANG_PATTERNS,
    EXPECTED_PROMPT_APPLIED_AGENT_TYPES,
    PATTERN_BOUNDARIES,
    _pattern_for_index,
)


def test_pattern_for_index_distribution() -> None:
    """Verify boundary indices map to the correct pattern."""
    assert _pattern_for_index(0) == ["id", "en"]
    assert _pattern_for_index(11) == ["id", "en"]
    assert _pattern_for_index(12) == ["ms", "en"]
    assert _pattern_for_index(23) == ["ms", "en"]
    assert _pattern_for_index(24) == ["th", "en"]
    assert _pattern_for_index(34) == ["th", "en"]
    assert _pattern_for_index(35) == ["id", "ms", "th", "en"]
    assert _pattern_for_index(45) == ["id", "ms", "th", "en"]
    assert _pattern_for_index(46) is None
    assert _pattern_for_index(56) is None


def test_pattern_for_index_out_of_bounds() -> None:
    """Index outside the 57-row range raises ValueError — defensive against caller bugs."""
    with pytest.raises(ValueError):
        _pattern_for_index(57)
    # Negative indices are also off-by-one bugs (Python's ``-1`` would otherwise
    # silently match the first boundary). The function must reject these too.
    with pytest.raises(ValueError):
        _pattern_for_index(-1)


def test_pattern_count_sums_to_57() -> None:
    """Distribution must sum to 57 — derived from boundaries, not hardcoded.

    Deriving counts from ``PATTERN_BOUNDARIES`` (instead of a local literal)
    means any future edit to the boundaries that breaks the 57-row invariant
    fails this test immediately.
    """
    counts = [PATTERN_BOUNDARIES[0]] + [
        PATTERN_BOUNDARIES[i] - PATTERN_BOUNDARIES[i - 1] for i in range(1, len(PATTERN_BOUNDARIES))
    ]
    assert sum(counts) == 57
    assert len(ALLOWED_LANG_PATTERNS) == 5
    assert len(counts) == 5
    assert EXPECTED_PROMPT_APPLIED_AGENT_TYPES == [
        "lang_detect_input",
        "translate",
        "lang_detect_output",
    ]
