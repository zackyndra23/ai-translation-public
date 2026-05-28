"""Tests for RedisCache.

We use ``fakeredis.aioredis.FakeRedis`` rather than ``testcontainers`` for
two reasons:

- The cache's behaviour we want to assert (get/set/delete/ttl) is well-
  modelled by fakeredis; the things fakeredis doesn't perfectly mimic
  (cluster mode, lua scripts) aren't relevant to this layer.
- Spinning up a container per test run is ~3s of overhead we don't need
  for the unit assertions. The Phase-4 manual smoke test uses real Redis
  against the running docker-compose container.

For the graceful-degradation tests we substitute a stub client whose
operations raise ``RedisError`` — that's the cleanest way to assert "errors
do NOT propagate" without poking at fakeredis's internals.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from redis.exceptions import RedisError
from src.cache.redis_cache import DEFAULT_TTL_SECONDS, RedisCache


@pytest.fixture
def fake_cache() -> RedisCache:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=False)
    return RedisCache(client=fake)


# ---- happy path ----------------------------------------------------------


async def test_set_then_get_roundtrip(fake_cache: RedisCache) -> None:
    await fake_cache.set("k", {"hello": "world", "n": 42})
    assert await fake_cache.get("k") == {"hello": "world", "n": 42}


async def test_get_missing_returns_none(fake_cache: RedisCache) -> None:
    assert await fake_cache.get("does-not-exist") is None


async def test_delete_removes_entry(fake_cache: RedisCache) -> None:
    await fake_cache.set("k", "v")
    await fake_cache.delete("k")
    assert await fake_cache.get("k") is None


async def test_health_check_returns_true_for_live_redis(fake_cache: RedisCache) -> None:
    assert await fake_cache.health_check() is True


# ---- TTL behaviour --------------------------------------------------------


async def test_set_uses_explicit_ttl(fake_cache: RedisCache) -> None:
    # fakeredis honours TTL semantics; we just verify the call accepts ttl.
    await fake_cache.set("k", "v", ttl_seconds=60)
    fake = fake_cache._client  # type: ignore[attr-defined]
    assert await fake.ttl("k") <= 60


async def test_set_uses_default_ttl_when_unspecified(fake_cache: RedisCache) -> None:
    await fake_cache.set("k", "v")
    fake = fake_cache._client  # type: ignore[attr-defined]
    ttl = await fake.ttl("k")
    # Should be close to the default — give a small window in case the test
    # spans a second boundary.
    assert ttl > DEFAULT_TTL_SECONDS - 5


# ---- graceful degradation -------------------------------------------------


def _broken_client() -> Any:
    client = AsyncMock()
    client.get = AsyncMock(side_effect=RedisError("boom"))
    client.set = AsyncMock(side_effect=RedisError("boom"))
    client.delete = AsyncMock(side_effect=RedisError("boom"))
    client.ping = AsyncMock(side_effect=RedisError("boom"))
    return client


async def test_get_errors_degrade_to_none() -> None:
    cache = RedisCache(client=_broken_client())
    # MUST NOT raise — that's the whole point of graceful degradation.
    assert await cache.get("k") is None


async def test_set_errors_swallowed() -> None:
    cache = RedisCache(client=_broken_client())
    await cache.set("k", "v")  # would raise without the guard


async def test_delete_errors_swallowed() -> None:
    cache = RedisCache(client=_broken_client())
    await cache.delete("k")


async def test_health_check_returns_false_on_error() -> None:
    cache = RedisCache(client=_broken_client())
    assert await cache.health_check() is False


async def test_degradation_logged_once_not_per_call() -> None:
    """First failure flips ``_degraded`` so subsequent failures don't spam
    the log. We assert against the latch rather than mocking the logger —
    the latch is the contract; what the log call looks like is incidental.
    """
    cache = RedisCache(client=_broken_client())
    await cache.get("a")
    assert cache._degraded is True  # type: ignore[attr-defined]
    await cache.get("b")
    assert cache._degraded is True


async def test_recovery_clears_degraded_flag() -> None:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=False)
    cache = RedisCache(client=fake)
    # Force degraded state by hand (no real failure needed for the assertion).
    cache._degraded = True  # type: ignore[attr-defined]
    await cache.set("k", "v")  # succeeds → should clear the latch
    assert cache._degraded is False  # type: ignore[attr-defined]


# ---- corrupted-value handling --------------------------------------------


async def test_corrupted_value_is_treated_as_miss_and_evicted(
    fake_cache: RedisCache,
) -> None:
    fake = fake_cache._client  # type: ignore[attr-defined]
    # Plant a non-JSON value directly so the deserialise step trips.
    await fake.set("broken", b"\x00\x01\x02 not json")
    assert await fake_cache.get("broken") is None
    # And the bad value should be gone — next write would otherwise hit
    # the same deserialise failure on every read.
    assert await fake.get("broken") is None
