"""Pin the error hierarchy so retry logic remains correct.

``RetryingProvider`` decides retry vs. give-up purely on the *class* of the
raised error. If someone accidentally re-parents one of these errors (e.g.
moving ``RateLimitError`` out from under ``TransientError``), the retry
behaviour would silently change. These tests catch that.
"""

from __future__ import annotations

from src.providers.errors import (
    AuthError,
    CapabilityError,
    PermanentError,
    RateLimitError,
    TransientError,
    TranslationProviderError,
)


def test_transient_and_permanent_are_siblings_under_base() -> None:
    assert issubclass(TransientError, TranslationProviderError)
    assert issubclass(PermanentError, TranslationProviderError)
    # Critical for the retry decorator: a permanent error must NOT match
    # ``except TransientError`` and vice versa.
    assert not issubclass(TransientError, PermanentError)
    assert not issubclass(PermanentError, TransientError)


def test_rate_limit_is_transient() -> None:
    assert issubclass(RateLimitError, TransientError)


def test_auth_and_capability_are_permanent() -> None:
    assert issubclass(AuthError, PermanentError)
    assert issubclass(CapabilityError, PermanentError)


def test_rate_limit_stores_retry_after() -> None:
    err = RateLimitError("slow down", retry_after_seconds=12)
    assert err.retry_after_seconds == 12
    assert "slow down" in str(err)


def test_rate_limit_default_retry_after_is_zero() -> None:
    # 0 means "no upstream hint, fall back to the retry policy's default backoff."
    err = RateLimitError("rate limited")
    assert err.retry_after_seconds == 0
