"""Provider factory — single source of truth for how a provider is wired.

Right now there's exactly one provider (Claude). The factory exists anyway
because:

1. The pipeline (Phase 4) shouldn't reach into ``ClaudeProvider`` directly.
   That would couple business logic to a specific SDK — exactly what ADR-001
   says to avoid.

2. The retry wrapper is opinionated. Anyone constructing a provider by hand
   would forget to wrap it, the pipeline would catch raw transient errors,
   and we'd be one outage away from finding out. The factory makes the
   wrapped form the only thing you can get.

3. When we add NLLB / OpenAI / a router, ``get_provider("router")`` will be
   the migration path — callers don't change.
"""

from __future__ import annotations

from src.config.settings import get_settings
from src.providers.base import TranslationProvider
from src.providers.claude import ClaudeProvider
from src.providers.errors import CapabilityError
from src.providers.retrying import RetryingProvider

# Friendly name → (factory function) registry. Adding a provider is a one-line
# change here. ``"claude-sonnet"`` is the alias we use everywhere; the actual
# model id (``claude-sonnet-4-6``) is a Settings concern so we can bump it via
# env without code changes.
_PROVIDER_ALIASES = {"claude", "claude-sonnet"}


def get_provider(
    name: str = "claude-sonnet",
    *,
    max_retries: int = 3,
    model_id_override: str | None = None,
) -> TranslationProvider:
    """Construct the provider identified by ``name``, wrapped in retry logic.

    ``model_id_override`` replaces the default model_id from settings when set.
    This lets callers build a Haiku-backed provider without a separate settings
    entry — ``get_provider("claude-sonnet", model_id_override="claude-haiku-...")``
    returns the same retrying wrapper but with Haiku as the default model.

    Raises :class:`CapabilityError` for unknown names so the caller gets a
    typed error from our own hierarchy rather than a ``KeyError`` leak from
    the registry implementation.
    """
    if name not in _PROVIDER_ALIASES:
        raise CapabilityError(
            f"No provider registered under {name!r}. Known providers: {sorted(_PROVIDER_ALIASES)}"
        )

    settings = get_settings()
    # Use the override when provided; fall back to settings.anthropic_model.
    # This keeps settings as the single source of truth for the default model
    # while allowing callers (e.g. lang-detect agents) to opt into a cheaper
    # model without a separate config field.
    default_model = model_id_override if model_id_override is not None else settings.anthropic_model
    inner = ClaudeProvider(
        anthropic_api_key=settings.anthropic_api_key,
        default_model=default_model,
    )
    return RetryingProvider(inner, max_retries=max_retries)
