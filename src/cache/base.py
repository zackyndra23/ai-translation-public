"""Cache backend Protocol — the only contract the pipeline sees.

A cache is a *performance* primitive, not a correctness one. Per CLAUDE.md
principle #6 ("Graceful degradation"), the system must keep working when the
cache is unreachable; everything that uses ``CacheBackend`` therefore treats
``get`` returning ``None`` as a normal outcome and ``set`` never as a failure
the caller has to react to.

The Protocol stays small for this reason. Anything more elaborate (atomic
counters, pub/sub) is provider-specific and lives behind a separate interface
in whichever module actually needs it.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """The narrow surface every cache implementation exposes."""

    async def get(self, key: str) -> Any | None:
        """Return the cached value for ``key``, or ``None`` if absent / on error.

        Errors MUST NOT propagate. A cache hiccup degrades to a miss; the
        caller transparently falls through to the uncached path.
        """
        ...

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Store ``value`` under ``key`` with optional TTL.

        Like ``get``, errors are swallowed. The next read just won't find the
        entry — which is the same as the network blip never happening.
        """
        ...

    async def delete(self, key: str) -> None:
        """Remove ``key`` if present. No-op (and no error) if absent."""
        ...

    async def health_check(self) -> bool:
        """Cheap liveness probe.

        Used by ``/ready`` (future) so the orchestrator can route around a
        broken cache node. NOT used inside the hot path — we don't want to
        pay a roundtrip per request just to find out the cache is down; we
        find out on the first failed ``get`` and degrade from there.
        """
        ...
