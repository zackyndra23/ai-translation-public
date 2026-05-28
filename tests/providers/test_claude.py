"""Tests for ClaudeProvider.

Per ADR-001 the only place the ``anthropic`` SDK may be imported in *source* is
``src/providers/claude.py``. Tests are allowed to import it — they need the
real exception classes to verify the translation layer maps them correctly.

The mocking strategy is dependency injection rather than ``patch``: the
``ClaudeProvider`` constructor accepts an optional pre-built ``AsyncAnthropic``
client. Production code lets the constructor build its own; tests pass a
``MagicMock`` whose ``messages.create`` is an ``AsyncMock``.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import pytest
from src.providers.base import TranslationOptions, TranslationRequest
from src.providers.claude import ClaudeProvider
from src.providers.errors import (
    AuthError,
    PermanentError,
    RateLimitError,
    TransientError,
)

# ---- helpers ---------------------------------------------------------------

# Anthropic SDK status errors require a real httpx Response. Building these once
# at module scope avoids cluttering each test with the same boilerplate.
_FAKE_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _anthropic_status_error(
    exc_cls: type[anthropic.APIStatusError],
    status_code: int,
    headers: dict[str, str] | None = None,
    message: str = "boom",
) -> anthropic.APIStatusError:
    response = httpx.Response(status_code, headers=headers or {}, request=_FAKE_REQUEST)
    return exc_cls(message, response=response, body=None)


def _fake_message(
    text: str,
    *,
    input_tokens: int,
    output_tokens: int,
    model: str = "claude-sonnet-4-6",
) -> SimpleNamespace:
    """Mimic the shape of ``anthropic.types.Message`` that the provider reads.

    We use ``SimpleNamespace`` rather than ``MagicMock`` so attribute access is
    *strict* — if the provider reads a field we don't set here, the test fails
    loudly instead of getting a silent ``MagicMock`` back.
    """
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model=model,
        stop_reason="end_turn",
        id="msg_test_123",
        model_dump=lambda: {
            "id": "msg_test_123",
            "model": model,
            "content": [{"type": "text", "text": text}],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "stop_reason": "end_turn",
        },
    )


def _make_provider_with_mock(
    *, create_side_effect: object | None = None, create_return_value: object | None = None
) -> tuple[ClaudeProvider, AsyncMock]:
    client = MagicMock()
    create_mock = AsyncMock()
    if create_side_effect is not None:
        create_mock.side_effect = create_side_effect
    if create_return_value is not None:
        create_mock.return_value = create_return_value
    client.messages.create = create_mock
    provider = ClaudeProvider(anthropic_api_key="test-key", client=client)
    return provider, create_mock


# ---- happy path ------------------------------------------------------------


async def test_translate_happy_path_parses_response() -> None:
    fake = _fake_message("halo, apa kabar?", input_tokens=12, output_tokens=8)
    provider, create_mock = _make_provider_with_mock(create_return_value=fake)

    result = await provider.translate(
        TranslationRequest(text="hello, how are you?", source_lang="en", target_lang="id")
    )

    assert result.translation == "halo, apa kabar?"
    assert result.provider == "claude"
    assert result.model == "claude-sonnet-4-6"
    assert result.tokens_input == 12
    assert result.tokens_output == 8
    # Cost should be computed from the pricing table, not zero.
    assert result.cost_usd > Decimal("0")
    assert result.latency_ms >= 0
    assert result.raw_response  # populated with model_dump output
    assert result.metadata["stop_reason"] == "end_turn"
    create_mock.assert_awaited_once()


async def test_translate_uses_system_prompt_override_when_provided() -> None:
    fake = _fake_message("halo", input_tokens=1, output_tokens=1)
    provider, create_mock = _make_provider_with_mock(create_return_value=fake)

    custom_prompt = "You are a formal translator for legal documents."
    await provider.translate(
        TranslationRequest(
            text="hi",
            source_lang="en",
            target_lang="id",
            options=TranslationOptions(system_prompt_override=custom_prompt),
        )
    )

    call_kwargs = create_mock.await_args.kwargs
    assert call_kwargs["system"] == custom_prompt


async def test_translate_passes_temperature_and_max_tokens() -> None:
    fake = _fake_message("halo", input_tokens=1, output_tokens=1)
    provider, create_mock = _make_provider_with_mock(create_return_value=fake)

    await provider.translate(
        TranslationRequest(
            text="hi",
            source_lang="en",
            target_lang="id",
            options=TranslationOptions(temperature=0.3, max_tokens=200),
        )
    )

    call_kwargs = create_mock.await_args.kwargs
    assert call_kwargs["temperature"] == 0.3
    assert call_kwargs["max_tokens"] == 200


# ---- error translation -----------------------------------------------------


async def test_rate_limit_error_translated_with_retry_after() -> None:
    err = _anthropic_status_error(anthropic.RateLimitError, 429, headers={"retry-after": "7"})
    provider, _ = _make_provider_with_mock(create_side_effect=err)

    with pytest.raises(RateLimitError) as ei:
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))
    assert ei.value.retry_after_seconds == 7
    # The original SDK error should be attached so logs can show the upstream message.
    assert isinstance(ei.value.__cause__, anthropic.RateLimitError)


async def test_rate_limit_without_header_defaults_to_zero() -> None:
    err = _anthropic_status_error(anthropic.RateLimitError, 429, headers={})
    provider, _ = _make_provider_with_mock(create_side_effect=err)

    with pytest.raises(RateLimitError) as ei:
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))
    # 0 signals "no upstream hint, retry policy decides".
    assert ei.value.retry_after_seconds == 0


async def test_timeout_translated_to_transient() -> None:
    err = anthropic.APITimeoutError(request=_FAKE_REQUEST)
    provider, _ = _make_provider_with_mock(create_side_effect=err)
    with pytest.raises(TransientError):
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))


async def test_connection_error_translated_to_transient() -> None:
    err = anthropic.APIConnectionError(request=_FAKE_REQUEST)
    provider, _ = _make_provider_with_mock(create_side_effect=err)
    with pytest.raises(TransientError):
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))


async def test_authentication_error_translated_to_auth() -> None:
    err = _anthropic_status_error(anthropic.AuthenticationError, 401)
    provider, _ = _make_provider_with_mock(create_side_effect=err)
    with pytest.raises(AuthError):
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))


async def test_bad_request_translated_to_permanent() -> None:
    err = _anthropic_status_error(anthropic.BadRequestError, 400)
    provider, _ = _make_provider_with_mock(create_side_effect=err)
    with pytest.raises(PermanentError) as ei:
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))
    # And it must NOT be the transient subclass — otherwise retrying would loop.
    assert not isinstance(ei.value, TransientError)


async def test_unexpected_exception_wrapped_as_permanent() -> None:
    # Anything we don't have a specific handler for: log loudly, don't retry,
    # surface as a permanent error so the caller sees something rather than
    # raw SDK internals.
    err = RuntimeError("something the SDK didn't document")
    provider, _ = _make_provider_with_mock(create_side_effect=err)
    with pytest.raises(PermanentError) as ei:
        await provider.translate(TranslationRequest(text="hi", source_lang="en", target_lang="id"))
    assert ei.value.__cause__ is err


# ---- capabilities & language support --------------------------------------


def test_capabilities_static_values_make_sense() -> None:
    provider = ClaudeProvider(anthropic_api_key="x", client=MagicMock())
    caps = provider.capabilities
    assert caps.supports_system_prompt is True
    # 200k context is Anthropic's documented limit for current models.
    assert caps.max_context_tokens >= 200_000


@pytest.mark.parametrize("lang", ["btk", "bug", "ace", "min"])
def test_low_resource_indonesian_langs_unsupported(lang: str) -> None:
    """These are bahasa lokal Indonesia where Claude's quality dips. Returning
    False here is a signal for the future router to pick NLLB or similar.
    """
    provider = ClaudeProvider(anthropic_api_key="x", client=MagicMock())
    assert provider.supports_language_pair("en", lang) is False
    assert provider.supports_language_pair(lang, "en") is False


@pytest.mark.parametrize(
    "source,target",
    [("en", "id"), ("id", "en"), ("en", "ja"), ("zh", "en")],
)
def test_mainstream_pairs_supported(source: str, target: str) -> None:
    provider = ClaudeProvider(anthropic_api_key="x", client=MagicMock())
    assert provider.supports_language_pair(source, target) is True


def test_estimate_cost_returns_positive_decimal_for_nonempty_text() -> None:
    provider = ClaudeProvider(anthropic_api_key="x", client=MagicMock())
    cost = provider.estimate_cost("hello world, this is a sample sentence")
    assert isinstance(cost, Decimal)
    assert cost > Decimal("0")
