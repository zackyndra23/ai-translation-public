"""Tests for custom ID generator."""

from __future__ import annotations

import re

from src.db.ids import make_id

_ID_PATTERN = re.compile(r"^[a-z]+-[0-9a-f]{8}-[0-9a-f]{4}$")


def test_make_id_format_country() -> None:
    result = make_id("country")
    assert _ID_PATTERN.match(result)
    assert result.startswith("country-")


def test_make_id_unique_across_calls() -> None:
    ids = {make_id("tenant") for _ in range(1000)}
    assert len(ids) == 1000  # 1000 unique IDs, collision-safe


def test_make_id_length_within_30() -> None:
    for prefix in (
        "country",
        "company",
        "department",
        "position",
        "service",
        "tenant",
        "profile",
        "prompt",
    ):
        result = make_id(prefix)
        assert len(result) <= 30, f"{result!r} exceeds VARCHAR(30)"


def test_make_id_rejects_empty_prefix() -> None:
    import pytest

    with pytest.raises(ValueError):
        make_id("")
