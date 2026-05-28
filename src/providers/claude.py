"""Claude provider — the ONLY file in this codebase allowed to import ``anthropic``.

Per ADR-001 in CLAUDE.md, every other module routes through the
``TranslationProvider`` protocol. If you find yourself reaching for
``import anthropic`` somewhere else, that's the signal to expose what you need
on this provider's interface instead.

This module does three jobs:
1. Build the prompt for a translation request.
2. Call the Anthropic Messages API with a measured timeout and latency probe.
3. Map every Anthropic SDK exception into our :mod:`src.providers.errors`
   hierarchy so callers never have to know about ``anthropic.*`` exception
   types. The general rule: SDK timeouts/connection errors are transient; rate
   limits carry their retry hint; everything else surfaces as permanent so it
   doesn't get retried into the ground.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from src.config.logging import get_logger
from src.providers.base import (
    LanguageCode,
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
from src.providers.pricing import calculate_cost, estimate_cost

log = get_logger(__name__)

# Languages Claude handles poorly enough that we'd rather have the router skip
# us. These are minority languages of Indonesia where benchmarks (and our own
# spot checks against the NLLB sibling project) show NLLB is the better choice.
# Sinyal untuk router masa depan — saat ini ``supports_language_pair`` cuma
# mengembalikan False supaya kita gak silently menerjemahkan dengan kualitas
# buruk.
_LOW_RESOURCE_LANGS: frozenset[LanguageCode] = frozenset({"btk", "bug", "ace", "min"})

# Static capability sheet — Claude doesn't change context size mid-request.
# If Anthropic releases a longer-context model we update this constant; the
# router (future) will then start sending longer payloads here.
_CAPABILITIES = ProviderCapabilities(
    # We default to non-streaming per ADR-004: the MVP pipeline is request/response.
    supports_streaming=False,
    # 200k tokens covers all current Claude 4.x models. Newer models with 1M
    # context exist but we cap at 200k until we benchmark the cost trade-off.
    max_context_tokens=200_000,
    supports_system_prompt=True,
    supports_low_resource_langs=False,
    cost_tier="medium",  # Sonnet-tier pricing
    typical_latency_ms=1500,
)


class ClaudeProvider:
    """Async Anthropic Messages API client wrapped in our provider interface.

    The constructor accepts an optional ``client``. In production we let the
    provider construct its own ``AsyncAnthropic`` from the API key; in tests
    we inject a ``MagicMock`` to avoid hitting the real API.
    """

    def __init__(
        self,
        anthropic_api_key: str,
        *,
        default_model: str = "claude-sonnet-4-6",
        timeout: float = 30.0,
        client: AsyncAnthropic | Any | None = None,
    ) -> None:
        # Dependency injection so tests can pass a mock without monkey-patching.
        self._client: AsyncAnthropic = client or AsyncAnthropic(
            api_key=anthropic_api_key, timeout=timeout
        )
        self._default_model = default_model
        self._timeout = timeout

    # ---- TranslationProvider protocol -------------------------------------

    @property
    def name(self) -> str:
        return "claude"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES

    def supports_language_pair(self, source: LanguageCode, target: LanguageCode) -> bool:
        # We return False if EITHER endpoint is in the low-resource list. The
        # router can then route the *pair* (not just one direction) to NLLB.
        return source not in _LOW_RESOURCE_LANGS and target not in _LOW_RESOURCE_LANGS

    def estimate_cost(self, text: str) -> Decimal:
        # Translation output length ≈ input length (ratio 1.0). For target
        # languages that compress badly (e.g. English → German), the real
        # cost will run higher; budget gates should account for that.
        return estimate_cost(self._default_model, text, output_ratio=1.0)

    async def translate(self, request: TranslationRequest) -> TranslationResult:
        prompt = self._build_prompt(request)
        kwargs: dict[str, Any] = {
            "model": self._default_model,
            "max_tokens": request.options.max_tokens,
            "temperature": request.options.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Only set ``system`` when the caller explicitly provided one — passing
        # an empty string to the SDK would still count as "I set a system prompt"
        # and override Claude's defaults.
        if request.options.system_prompt_override:
            kwargs["system"] = request.options.system_prompt_override

        # Latency is measured on our side, not reported by the SDK. ``perf_counter``
        # is monotonic so it's the right clock for short intervals.
        start = time.perf_counter()
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.RateLimitError as e:
            raise RateLimitError(
                f"Anthropic rate limit: {e}",
                retry_after_seconds=_parse_retry_after(e),
            ) from e
        except anthropic.APITimeoutError as e:
            # Network slowness or upstream slowness — worth retrying after backoff.
            raise TransientError(f"Anthropic API timeout: {e}") from e
        except anthropic.APIConnectionError as e:
            # DNS, TLS handshake failure, etc. Transient by nature.
            raise TransientError(f"Anthropic connection error: {e}") from e
        except anthropic.AuthenticationError as e:
            # Bad/expired/missing API key. The operator needs to fix .env;
            # retrying would just hammer auth.
            raise AuthError(f"Anthropic authentication failed: {e}") from e
        except anthropic.BadRequestError as e:
            # Malformed input (prompt too long, invalid parameter). The same
            # request will fail the same way next time — surface immediately.
            raise PermanentError(f"Anthropic bad request: {e}") from e
        except anthropic.APIError as e:
            # Catch-all for documented SDK errors we didn't list above (e.g.
            # APIStatusError subclasses we don't model individually).
            raise PermanentError(f"Anthropic API error: {e}") from e
        except Exception as e:
            # Defensive: anything else (e.g. an httpx-level error escaping the
            # SDK, a bug in the SDK itself) gets wrapped so the pipeline only
            # ever sees our error types. ``from e`` preserves the original
            # traceback for logs.
            log.error("claude.unexpected_error", error=str(e), error_type=type(e).__name__)
            raise PermanentError(f"Unexpected error calling Anthropic: {e}") from e

        latency_ms = (time.perf_counter() - start) * 1000.0
        return self._build_result(response, latency_ms)

    # ---- internal helpers -------------------------------------------------

    @staticmethod
    def _build_prompt(request: TranslationRequest) -> str:
        # Phase 2 keeps this dead simple. Phase 4 swaps in a Jinja template that
        # interpolates profile glossary, tone, and few-shot examples; the
        # provider interface doesn't change, only what gets passed in.
        return (
            f"Translate the following text from {request.source_lang} "
            f"to {request.target_lang}. Output only the translation, no "
            f"explanation.\n\n"
            f"Text: {request.text}"
        )

    def _build_result(self, response: Any, latency_ms: float) -> TranslationResult:
        translation = _extract_text(response)
        input_tokens, output_tokens = _extract_usage(response)
        model = getattr(response, "model", self._default_model)
        cost = calculate_cost(model, input_tokens, output_tokens)

        # ``model_dump`` exists on anthropic's pydantic types; fall back to
        # ``str(response)`` for anything that doesn't serialise (the cost is
        # losing the dict shape, not crashing).
        raw_dump = getattr(response, "model_dump", None)
        raw_response: dict[str, Any] = (
            raw_dump() if callable(raw_dump) else {"_repr": str(response)}
        )

        return TranslationResult(
            translation=translation,
            provider=self.name,
            model=model,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            raw_response=raw_response,
            metadata={
                "stop_reason": getattr(response, "stop_reason", None),
                "message_id": getattr(response, "id", None),
            },
        )


def _parse_retry_after(error: anthropic.RateLimitError) -> int:
    """Pull the upstream ``Retry-After`` hint from a 429.

    Returns 0 when the header is missing or unparseable — the caller's retry
    policy will fall back to its own backoff schedule in that case rather than
    sleeping forever or hitting the API again immediately.
    """
    response = getattr(error, "response", None)
    if response is None:
        return 0
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("retry-after") if hasattr(headers, "get") else None
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _extract_text(response: Any) -> str:
    """Pick the first text content block out of an Anthropic Message.

    Claude can return multiple content blocks (text, tool_use, ...). For
    translation we only ever want text — if there is none, the response is
    structurally broken from our point of view and we treat it as a permanent
    error rather than returning an empty string that would corrupt downstream
    consumers.
    """
    content = getattr(response, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "text":
            text: str = block.text
            return text
    raise PermanentError("Claude returned no text content blocks")


def _extract_usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        # If usage is missing we can't bill — fail loudly rather than charge
        # the wrong customer.
        raise PermanentError("Claude response missing usage block")
    return int(usage.input_tokens), int(usage.output_tokens)
