"""Provider abstraction — the only contract the rest of the codebase sees.

Per ADR-001 (CLAUDE.md), we own this abstraction instead of pulling in LiteLLM.
The trade-off: a bit more code to maintain, but full control over error types,
retry semantics, and cost accounting — all of which we need to expose to the
pipeline and the evaluation harness.

Per the same ADR, the rule of thumb is: if a file outside ``src/providers/`` ever
needs to import an SDK (``anthropic``, ``openai``, etc.), the abstraction is
leaking. Use ``TranslationProvider`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

# Language codes are ISO 639-1 strings (``"en"``, ``"id"``, ...) by convention. We
# don't enforce that with an Enum because the set of languages a router might one
# day support is open, and a typo will surface immediately as a translation error.
LanguageCode = str


@dataclass(slots=True)
class TranslationOptions:
    """Per-request knobs the caller can tweak.

    Defaults are tuned for translation specifically — low temperature so the
    output is faithful to the source rather than creative, and a generous
    ``max_tokens`` so we don't truncate long passages. Pipeline stages override
    these when they have stronger context (e.g. summarisation might want higher
    temperature).
    """

    temperature: float = 0.0
    max_tokens: int = 4096
    # When a stage already has a fully-rendered system prompt (with glossary, tone,
    # examples), it can inject it here and the provider will use it verbatim.
    system_prompt_override: str | None = None


@dataclass(slots=True)
class TranslationRequest:
    """The input contract for ``TranslationProvider.translate``.

    ``profile`` is a plain dict in Phase 2 because the Profile schema doesn't
    exist yet (Phase 3). When Phase 3 lands we'll replace the dict with the
    typed ``ResolvedProfile`` model — callers using the dict form will continue
    to work because TypedDict access patterns map cleanly.
    """

    text: str
    source_lang: LanguageCode
    target_lang: LanguageCode
    profile: dict[str, Any] = field(default_factory=dict)
    options: TranslationOptions = field(default_factory=TranslationOptions)


@dataclass(slots=True)
class TranslationResult:
    """The output contract.

    Every field is set on every successful translate call. Callers downstream
    (cache, eval harness, billing) depend on the full shape, so the provider
    is responsible for filling these in even when the SDK doesn't return them
    explicitly (e.g. ``latency_ms`` is measured by us, not reported by Claude).
    """

    translation: str
    provider: str
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: Decimal
    latency_ms: float
    # ``raw_response`` is the SDK's response object converted to a plain dict.
    # Useful for debugging unexpected behaviour without re-running the call.
    raw_response: dict[str, Any] = field(default_factory=dict)
    # ``metadata`` is an open-ended channel for provider-specific extras the
    # caller might want to log (stop_reason, system_fingerprint, ...).
    metadata: dict[str, Any] = field(default_factory=dict)


CostTier = Literal["low", "medium", "high"]


@dataclass(slots=True, frozen=True)
class ProviderCapabilities:
    """A static description of what a provider can do.

    Frozen because capabilities don't change per-request. The router (future)
    will use these to pick a provider for a given request shape.
    """

    supports_streaming: bool
    max_context_tokens: int
    supports_system_prompt: bool
    # True if the provider has acceptable quality on under-resourced languages
    # (e.g. Acehnese, Buginese). Sets expectations for the router; the router
    # may also enforce a hard skip via ``supports_language_pair``.
    supports_low_resource_langs: bool
    cost_tier: CostTier
    typical_latency_ms: int


@runtime_checkable
class TranslationProvider(Protocol):
    """The Protocol every provider implements.

    We use ``Protocol`` (structural typing) rather than ``ABC`` (nominal typing)
    so that wrappers like ``RetryingProvider`` satisfy the interface without
    needing to inherit from a common base. ``runtime_checkable`` lets factory
    code do an ``isinstance`` sanity-check at startup.
    """

    @property
    def name(self) -> str:
        """A stable identifier used in logs, cache keys, and the result's
        ``provider`` field (e.g. ``"claude"``).
        """
        ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def translate(self, request: TranslationRequest) -> TranslationResult: ...

    def supports_language_pair(self, source: LanguageCode, target: LanguageCode) -> bool:
        """Pre-flight check the router uses to skip providers that can't handle
        a given language pair (or handle it poorly). Cheap; no I/O.
        """
        ...

    def estimate_cost(self, text: str) -> Decimal:
        """Coarse pre-flight estimate in USD. The actual cost in
        ``TranslationResult.cost_usd`` is what we charge against — this is for
        budget gates / quota checks before we commit to a real call.
        """
        ...
