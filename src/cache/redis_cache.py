"""Redis-backed implementation of :class:`CacheBackend`.

The big design decision in this file is **graceful degradation** (CLAUDE.md
principle #6). Every Redis operation is wrapped in try/except so that:

- A network blip degrades to a cache miss, NOT a 5xx for the user.
- A serialisation error during ``set`` is logged loudly but doesn't break
  the in-flight translation — we already have the result, we just won't be
  able to serve it from cache next time.
- The first failure also flips a flag so we stop spamming the logs (one
  warning per outage, not one per request).

The downside: a misconfigured cache (wrong URL, wrong password) looks the
same as "Redis is down". That's a deliberate trade — the alternative is the
system refusing to serve traffic at all when the cache layer is buggy, which
is strictly worse for the user. Operators see the warnings in logs and the
``health_check`` endpoint reports the state.
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.cache.base import CacheBackend
from src.config.logging import get_logger

log = get_logger(__name__)

# 30 days — translations are stable per (profile_version, model_id) so we
# keep them around long enough to amortise the API cost. When the profile
# bumps version the key changes and old entries quietly expire.
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 30


class RedisCache(CacheBackend):
    """Async Redis cache. Constructed with a redis URL or an existing client."""

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        client: Redis[bytes] | None = None,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        if client is None:
            if redis_url is None:
                raise ValueError("Either redis_url or client must be provided")
            # ``decode_responses=False`` so we get bytes back from ``get`` and
            # can json.loads on our own terms — encoding decisions stay in
            # one place. The ``Redis[bytes]`` annotation matches what
            # ``decode_responses=False`` produces.
            client = Redis.from_url(redis_url, decode_responses=False)
        self._client: Redis[bytes] = client
        self._default_ttl = default_ttl_seconds
        # Latch flips when we observe an outage so we log "redis.unavailable"
        # once instead of once per request. Reset on the first successful op.
        self._degraded = False

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
        except RedisError as e:
            self._note_degraded("get", e)
            return None

        self._note_recovered()
        if raw is None:
            return None

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            # A corrupted value is functionally a miss. We delete it so the
            # next write can put something readable in its place.
            log.warning("redis.deserialise_failed", key=key, error=str(e))
            await self.delete(key)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        try:
            serialised = json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            # Caller passed something that doesn't survive the round-trip.
            # That's a bug, but not one worth raising — the request the
            # value belongs to has already succeeded; we just can't cache it.
            log.warning("redis.serialise_failed", key=key, error=str(e))
            return

        try:
            await self._client.set(key, serialised, ex=ttl_seconds or self._default_ttl)
        except RedisError as e:
            self._note_degraded("set", e)
            return

        self._note_recovered()

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except RedisError as e:
            self._note_degraded("delete", e)

    async def health_check(self) -> bool:
        try:
            return bool(await self._client.ping())
        except RedisError as e:
            log.warning("redis.health_check_failed", error=str(e))
            return False

    # ---- internal helpers --------------------------------------------------

    def _note_degraded(self, op: str, error: Exception) -> None:
        if not self._degraded:
            log.warning("redis.unavailable", op=op, error=str(error))
            self._degraded = True

    def _note_recovered(self) -> None:
        if self._degraded:
            log.info("redis.recovered")
            self._degraded = False
