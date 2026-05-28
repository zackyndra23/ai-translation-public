"""Cache key composition.

Per ADR-003 in CLAUDE.md the cache key is::

    sha256(text + source_lang + target_lang + profile_slug + profile_version + model_id)

The profile_version in the input is what gives us automatic invalidation:
when a profile's glossary or tone changes, ``ProfileRepository.update_profile``
bumps the version, the next request gets a *different* cache key, and the
stale entry simply becomes unreachable (it'll expire on its own TTL).

We truncate the hex digest to 32 characters — that's 128 bits of entropy,
enough that the probability of a collision across the lifetime of the cache
is functionally zero, while halving the bytes-per-key in Redis vs. the full
64-character digest.
"""

from __future__ import annotations

import hashlib

CACHE_KEY_PREFIX = "translation"
_HASH_LENGTH = 32  # 128 bits — see module docstring


def compute_cache_key(
    text: str,
    source_lang: str,
    target_lang: str,
    profile_slug: str,
    profile_version: int,
    model_id: str,
) -> str:
    """Return a stable, well-namespaced cache key.

    The components are joined with a separator that cannot appear in any
    legitimate field (``\\x1f``, the ASCII unit separator). That keeps
    "translate ``ab`` with target ``c``" cleanly distinct from "translate
    ``a`` with target ``bc``" — otherwise concatenation alone could collide
    those two inputs.
    """
    separator = "\x1f"
    payload = separator.join(
        (text, source_lang, target_lang, profile_slug, str(profile_version), model_id)
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    return f"{CACHE_KEY_PREFIX}:{digest}"
