"""Cache-key tests.

These pin two properties of ``compute_cache_key``:

1. **Determinism**: same inputs → same key. Without this, the cache is
   useless (every request would be a miss).
2. **Sensitivity**: a change in ANY input field changes the key. Without
   this, two different requests could collide and the second caller would
   get the first caller's translation — a correctness bug, not a perf bug.

The "namespace" assertion guards the ``translation:`` prefix because the
future router will share Redis with other prefixes (``profile:``, ``rate:``)
and we need to be able to flush just one of them.
"""

from __future__ import annotations

import pytest
from src.cache.key import CACHE_KEY_PREFIX, compute_cache_key


def _key(**overrides) -> str:
    defaults = dict(
        text="hello",
        source_lang="en",
        target_lang="id",
        profile_slug="general",
        profile_version=1,
        model_id="claude-sonnet-4-6",
    )
    defaults.update(overrides)
    return compute_cache_key(**defaults)


def test_namespace_prefix() -> None:
    key = _key()
    assert key.startswith(f"{CACHE_KEY_PREFIX}:")


def test_determinism_same_input_same_key() -> None:
    assert _key() == _key()


@pytest.mark.parametrize(
    "field",
    ["text", "source_lang", "target_lang", "profile_slug", "profile_version", "model_id"],
)
def test_sensitivity_each_field_changes_key(field: str) -> None:
    base = _key()
    # Pick a value that differs from the default for the chosen field.
    nudge = {
        "text": "different text",
        "source_lang": "fr",
        "target_lang": "ja",
        "profile_slug": "asuransi",
        "profile_version": 2,
        "model_id": "claude-opus-4-7",
    }[field]
    assert _key(**{field: nudge}) != base


def test_concatenation_collision_resistance() -> None:
    """Without a separator, ``text='ab' + lang='c'`` would hash the same as
    ``text='a' + lang='bc'``. With our unit-separator joining, they don't.
    """
    a = compute_cache_key(
        text="ab",
        source_lang="c",
        target_lang="id",
        profile_slug="p",
        profile_version=1,
        model_id="m",
    )
    b = compute_cache_key(
        text="a",
        source_lang="bc",
        target_lang="id",
        profile_slug="p",
        profile_version=1,
        model_id="m",
    )
    assert a != b


def test_truncation_length() -> None:
    # prefix (11 chars: "translation") + ":" + 32 hex chars = 44 total
    assert len(_key()) == len(CACHE_KEY_PREFIX) + 1 + 32
