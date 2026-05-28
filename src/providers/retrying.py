"""Retry decorator that turns flaky upstreams into mostly-reliable ones.

This wrapper implements ``TranslationProvider`` so the rest of the codebase
sees the retry behaviour as part of the provider's normal interface — no
``if needs_retry:`` branching at the call site. The Protocol is structural,
so we don't inherit anything; we just need to expose the same attributes.

Policy in plain English:
- ``RateLimitError``  → sleep ``retry_after_seconds`` (or fall back to the
  exponential schedule if the upstream didn't supply a hint), then retry.
- ``TransientError``  → sleep ``2 ** attempt`` seconds, then retry, up to
  ``max_retries`` retries (so ``max_retries + 1`` total attempts).
- ``PermanentError``  → don't retry. Bad config / bad input shouldn't be
  hammered, and the result will be the same anyway.
- Any other exception → bubble up unchanged. Retrying on unknown error types
  hides bugs; we'd rather see the traceback.

The exponential schedule (1s, 2s, 4s) is intentionally aggressive — short
enough to recover from a single bad packet but not so long that a healthy
caller times out. For more elaborate strategies (jitter, max-delay cap) see
``tenacity``; we keep this hand-rolled because the policy lives close to
where the decisions matter, which is easier to audit than a config dict.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from src.config.logging import get_logger
from src.providers.base import (
    LanguageCode,
    ProviderCapabilities,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)
from src.providers.errors import (
    PermanentError,
    RateLimitError,
    TransientError,
)

log = get_logger(__name__)


class RetryingProvider:
    """Wraps a :class:`TranslationProvider` and re-invokes ``translate`` on
    transient failures.

    Non-translate methods are delegated unchanged — capabilities and language
    support don't depend on network state, so retrying them would be silly.
    """

    def __init__(self, inner: TranslationProvider, *, max_retries: int = 3) -> None:
        self._inner = inner
        self._max_retries = max_retries

    # ---- TranslationProvider protocol -------------------------------------

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._inner.capabilities

    def supports_language_pair(self, source: LanguageCode, target: LanguageCode) -> bool:
        return self._inner.supports_language_pair(source, target)

    def estimate_cost(self, text: str) -> Decimal:
        return self._inner.estimate_cost(text)

    async def translate(self, request: TranslationRequest) -> TranslationResult:
        # ``attempt`` counts retries (NOT total tries). attempt=0 is the first
        # call; attempt=1..max_retries are the retries. So total attempts is
        # max_retries + 1, which matches the test expectations.
        attempt = 0
        while True:
            try:
                return await self._inner.translate(request)
            except PermanentError:
                # Includes AuthError and CapabilityError via the hierarchy.
                # Don't sleep, don't retry — surface immediately.
                raise
            except RateLimitError as e:
                if attempt >= self._max_retries:
                    log.error(
                        "provider.retry.giveup",
                        provider=self._inner.name,
                        reason="rate_limit",
                        attempts=attempt + 1,
                    )
                    raise
                # Honour the upstream hint when present; otherwise fall back to
                # the exponential schedule so we don't hammer a 429.
                sleep_for = e.retry_after_seconds or _backoff_seconds(attempt)
                log.warning(
                    "provider.retry",
                    provider=self._inner.name,
                    reason="rate_limit",
                    attempt=attempt + 1,
                    sleep_seconds=sleep_for,
                    retry_after_hint=e.retry_after_seconds,
                )
                await asyncio.sleep(float(sleep_for))
                attempt += 1
            except TransientError as e:
                if attempt >= self._max_retries:
                    log.error(
                        "provider.retry.giveup",
                        provider=self._inner.name,
                        reason="transient",
                        attempts=attempt + 1,
                        last_error=str(e),
                    )
                    raise
                sleep_for = _backoff_seconds(attempt)
                log.warning(
                    "provider.retry",
                    provider=self._inner.name,
                    reason="transient",
                    attempt=attempt + 1,
                    sleep_seconds=sleep_for,
                    last_error=str(e),
                )
                await asyncio.sleep(float(sleep_for))
                attempt += 1


def _backoff_seconds(attempt: int) -> float:
    """Exponential schedule: 1, 2, 4, 8, ...

    Kept as a function (not a constant list) so callers with custom
    ``max_retries`` aren't constrained to a fixed-length array, and so that
    later we can swap in jitter without changing the call site.
    """
    return float(2**attempt)
