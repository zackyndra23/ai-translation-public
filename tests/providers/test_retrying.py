"""Tests for RetryingProvider.

The retry decorator is the only piece of code that decides whether to call the
upstream API again. If its policy drifts, we either burn money (retry storm)
or fail customers we could have served (give up too soon). These tests pin
the policy: backoff schedule, max attempts, sleep durations.

``asyncio.sleep`` is patched so the tests stay sub-second; we assert against
the *arguments* of the sleep call, not wall-clock time.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.providers.base import (
    ProviderCapabilities,
    TranslationRequest,
    TranslationResult,
)
from src.providers.errors import (
    AuthError,
    PermanentError,
    RateLimitError,
    TransientError,
)
from src.providers.retrying import RetryingProvider


def _make_inner(
    *, translate_side_effect: object | None = None, translate_return_value: object | None = None
) -> MagicMock:
    """Build a mock that satisfies the TranslationProvider protocol enough for
    the wrapper to delegate to.
    """
    inner = MagicMock()
    inner.name = "stub"
    inner.capabilities = ProviderCapabilities(
        supports_streaming=False,
        max_context_tokens=1,
        supports_system_prompt=False,
        supports_low_resource_langs=False,
        cost_tier="low",
        typical_latency_ms=1,
    )
    inner.supports_language_pair = MagicMock(return_value=True)
    inner.estimate_cost = MagicMock(return_value=Decimal("0.001"))

    translate = AsyncMock()
    if translate_side_effect is not None:
        translate.side_effect = translate_side_effect
    if translate_return_value is not None:
        translate.return_value = translate_return_value
    inner.translate = translate
    return inner


def _ok_result() -> TranslationResult:
    return TranslationResult(
        translation="halo",
        provider="stub",
        model="stub-model",
        tokens_input=1,
        tokens_output=1,
        cost_usd=Decimal("0.0001"),
        latency_ms=10.0,
    )


def _req() -> TranslationRequest:
    return TranslationRequest(text="hi", source_lang="en", target_lang="id")


# ---- delegation -----------------------------------------------------------


def test_delegates_non_translate_methods() -> None:
    inner = _make_inner(translate_return_value=_ok_result())
    wrapped = RetryingProvider(inner, max_retries=3)

    assert wrapped.name == "stub"
    assert wrapped.capabilities is inner.capabilities
    assert wrapped.supports_language_pair("en", "id") is True
    assert wrapped.estimate_cost("hi") == Decimal("0.001")


# ---- happy path ----------------------------------------------------------


async def test_passes_through_on_first_success() -> None:
    inner = _make_inner(translate_return_value=_ok_result())
    wrapped = RetryingProvider(inner, max_retries=3)

    result = await wrapped.translate(_req())

    assert result.translation == "halo"
    assert inner.translate.await_count == 1


# ---- transient retry & exponential backoff -------------------------------


async def test_retries_transient_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fails twice, then succeeds on the third attempt (= 2 retries).
    inner = _make_inner(
        translate_side_effect=[
            TransientError("blip 1"),
            TransientError("blip 2"),
            _ok_result(),
        ],
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)

    wrapped = RetryingProvider(inner, max_retries=3)
    result = await wrapped.translate(_req())

    assert result.translation == "halo"
    assert inner.translate.await_count == 3
    # Exponential schedule for the two retries: 1s, 2s.
    assert sleeps == [1.0, 2.0]


async def test_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    # Five consecutive transients; max_retries=3 means 4 total attempts.
    inner = _make_inner(
        translate_side_effect=[TransientError(f"blip {i}") for i in range(5)],
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)
    wrapped = RetryingProvider(inner, max_retries=3)

    with pytest.raises(TransientError):
        await wrapped.translate(_req())

    # 1 initial + 3 retries = 4 calls; 3 sleeps between them: 1s, 2s, 4s.
    assert inner.translate.await_count == 4
    assert sleeps == [1.0, 2.0, 4.0]


# ---- rate limit honours upstream retry_after -----------------------------


async def test_rate_limit_uses_retry_after_not_exp_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _make_inner(
        translate_side_effect=[
            RateLimitError("slow down", retry_after_seconds=7),
            _ok_result(),
        ],
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)
    wrapped = RetryingProvider(inner, max_retries=3)

    result = await wrapped.translate(_req())

    assert result.translation == "halo"
    # Slept the upstream hint (7s), not the exponential schedule (1s).
    assert sleeps == [7.0]


async def test_rate_limit_without_hint_falls_back_to_exp_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = _make_inner(
        translate_side_effect=[
            RateLimitError("rl", retry_after_seconds=0),  # no upstream hint
            _ok_result(),
        ],
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)
    wrapped = RetryingProvider(inner, max_retries=3)

    await wrapped.translate(_req())
    # First retry of attempt index 1 uses exponential 2^0 = 1s.
    assert sleeps == [1.0]


# ---- permanent errors never retry ----------------------------------------


async def test_permanent_error_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    inner = _make_inner(translate_side_effect=PermanentError("bad request"))
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)
    wrapped = RetryingProvider(inner, max_retries=3)

    with pytest.raises(PermanentError):
        await wrapped.translate(_req())

    assert inner.translate.await_count == 1
    assert sleeps == []  # we never slept


async def test_auth_error_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    # AuthError is a PermanentError subclass — important to verify it inherits
    # the no-retry behaviour, since retrying on bad creds just hammers auth.
    inner = _make_inner(translate_side_effect=AuthError("bad key"))

    async def fake_sleep(_: float) -> None:
        pytest.fail("sleep must not be called for AuthError")

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)
    wrapped = RetryingProvider(inner, max_retries=3)

    with pytest.raises(AuthError):
        await wrapped.translate(_req())

    assert inner.translate.await_count == 1


# ---- unrelated exceptions surface unchanged ------------------------------


async def test_non_provider_exception_bubbles(monkeypatch: pytest.MonkeyPatch) -> None:
    # Anything outside our error hierarchy should NOT be retried — that's a
    # bug somewhere, and retrying could mask it.
    inner = _make_inner(translate_side_effect=ValueError("not a provider error"))

    async def fake_sleep(_: float) -> None:
        pytest.fail("sleep must not be called for non-provider errors")

    monkeypatch.setattr("src.providers.retrying.asyncio.sleep", fake_sleep)
    wrapped = RetryingProvider(inner, max_retries=3)

    with pytest.raises(ValueError):
        await wrapped.translate(_req())

    assert inner.translate.await_count == 1


# ---- protocol compliance --------------------------------------------------


def test_wrapped_provider_satisfies_protocol() -> None:
    from src.providers.base import TranslationProvider

    inner = _make_inner(translate_return_value=_ok_result())
    wrapped: Any = RetryingProvider(inner, max_retries=3)
    assert isinstance(wrapped, TranslationProvider)
