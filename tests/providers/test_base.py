"""Verify dataclass defaults and the runtime-checkable Protocol.

These tests pin the public *shape* of the provider contract. If a future
refactor accidentally changes a default or renames a field, these break and
flag the breakage as a contract change rather than a quiet behavioural shift.
"""

from __future__ import annotations

from decimal import Decimal

from src.providers.base import (
    ProviderCapabilities,
    TranslationOptions,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)


def test_translation_options_defaults() -> None:
    opts = TranslationOptions()
    assert (
        opts.temperature == 0.0
    )  # deterministic by default — translation is faithful, not creative
    assert opts.max_tokens == 4096
    assert opts.system_prompt_override is None


def test_translation_request_defaults() -> None:
    req = TranslationRequest(text="hi", source_lang="en", target_lang="id")
    assert req.profile == {}
    assert isinstance(req.options, TranslationOptions)
    # ensure the default_factory gives each instance its own dict (no shared state)
    req2 = TranslationRequest(text="bye", source_lang="en", target_lang="id")
    req.profile["touched"] = True
    assert "touched" not in req2.profile


def test_translation_result_required_fields_present() -> None:
    result = TranslationResult(
        translation="halo",
        provider="claude",
        model="claude-sonnet-4-6",
        tokens_input=5,
        tokens_output=3,
        cost_usd=Decimal("0.0001"),
        latency_ms=123.4,
    )
    assert result.raw_response == {}
    assert result.metadata == {}
    assert isinstance(result.cost_usd, Decimal)


def test_provider_capabilities_is_frozen() -> None:
    caps = ProviderCapabilities(
        supports_streaming=False,
        max_context_tokens=200_000,
        supports_system_prompt=True,
        supports_low_resource_langs=False,
        cost_tier="medium",
        typical_latency_ms=1500,
    )
    # frozen=True makes the dataclass immutable — assignment must raise.
    try:
        caps.max_context_tokens = 1  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ProviderCapabilities should be frozen")


def test_translation_provider_is_runtime_checkable() -> None:
    """A stub class satisfying the Protocol structurally should pass isinstance.

    This guards the ``@runtime_checkable`` decorator — without it, the factory's
    sanity-check after wrapping with RetryingProvider would silently pass.
    """

    class StubProvider:
        @property
        def name(self) -> str:
            return "stub"

        @property
        def capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(
                supports_streaming=False,
                max_context_tokens=1,
                supports_system_prompt=False,
                supports_low_resource_langs=False,
                cost_tier="low",
                typical_latency_ms=1,
            )

        async def translate(self, request: TranslationRequest) -> TranslationResult:
            raise NotImplementedError

        def supports_language_pair(self, source: str, target: str) -> bool:
            return True

        def estimate_cost(self, text: str) -> Decimal:
            return Decimal("0")

    assert isinstance(StubProvider(), TranslationProvider)
