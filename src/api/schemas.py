"""HTTP boundary schemas.

These models are what HTTP callers send and receive. They deliberately do
NOT alias domain types directly -- even when shapes match, copying gives us
a versioning seam: changing an internal domain schema shouldn't silently
change the public API response shape, and vice versa.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.providers.base import TranslationOptions

__all__ = [
    "BatchTranslateItem",
    "BatchTranslateRequest",
    "BatchTranslateResponse",
    "BatchTranslateResultItem",
    "DeepHealthResponse",
    "DependencyHealth",
    "ErrorResponse",
    "HealthResponse",
    "TranslateRequest",
    "TranslateResponse",
]


# ---- Translate ------------------------------------------------------------


class TranslateRequest(BaseModel):
    """Single-translation request body."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = Field(min_length=1, description="The source text to translate.")
    target_lang: str = Field(
        min_length=2, max_length=5, description="ISO-639-1 target language code."
    )
    profile_id: str = Field(
        min_length=1, description="ID of the tenant_profile (sub-proyek I) to translate under."
    )
    source_lang: str | None = Field(
        default=None,
        max_length=5,
        description="Source language; omit to let the model auto-detect.",
    )
    options: TranslationOptions | None = Field(
        default=None,
        description="Optional provider knobs (temperature, max_tokens).",
    )


class TranslateResponse(BaseModel):
    """Single-translation response body — flattened :class:`PipelineResult`."""

    translation: str
    source_lang: str
    target_lang: str
    cached: bool
    provider: str
    model: str
    latency_ms: float
    cost_usd: Decimal
    glossary_compliance: float
    metadata: dict[str, Any]
    log_id: uuid.UUID | None = None
    # Full Jinja-rendered system prompt for debugging. Surfaces the exact
    # glossary terms, style examples, tone, and task instructions that the
    # LLM received. None for cache hits from pre-Phase-D entries.
    prompt_applied: str | None = None
    # Agentic activities from all 3 agents (lang_detect_input, translate,
    # lang_detect_output). Each item is the AgenticActivity serialised to a
    # plain dict so the API contract doesn't depend on the internal model.
    # Empty list on cache hits from pre-agentic entries.
    agentic_activities: list[dict[str, Any]] = []
    # Language detection fields populated by the haiku lang-detect agents.
    # None when detection failed or was skipped (e.g. rate-limited haiku).
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    # True when the detected lang differs from the declared source/target lang.
    # None when detection didn't run (so the caller can distinguish "no data"
    # from "no mismatch").
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None


# ---- Batch translate ------------------------------------------------------


class BatchTranslateItem(BaseModel):
    """One item in a batch translation request.

    ``id`` is opaque to the server — it's echoed back in the response so the
    caller can correlate. Useful when items are submitted out-of-order or
    when partial failures mean only some come back successful.
    """

    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1)


class BatchTranslateRequest(BaseModel):
    items: list[BatchTranslateItem] = Field(min_length=1, max_length=100)
    target_lang: str = Field(min_length=2, max_length=5)
    profile_id: str = Field(min_length=1)
    source_lang: str | None = Field(default=None, max_length=5)
    options: TranslationOptions | None = None


class BatchTranslateResultItem(BaseModel):
    """One result in a batch response."""

    id: str
    text: str
    cached: bool
    log_id: uuid.UUID | None = None
    # Full Jinja-rendered system prompt for debugging (same semantics as
    # TranslateResponse.prompt_applied). None on error items.
    prompt_applied: str | None = None
    # Agentic activities (same semantics as TranslateResponse.agentic_activities).
    # Empty list on error items or pre-agentic cache hits.
    agentic_activities: list[dict[str, Any]] = []
    # Language detection fields — same semantics as TranslateResponse equivalents.
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
    # ``error`` is populated when this particular item failed; the rest of the
    # batch may still have succeeded (partial-success semantics).
    error: str | None = None


class BatchTranslateResponse(BaseModel):
    translations: list[BatchTranslateResultItem]


# ---- Health ---------------------------------------------------------------


class HealthResponse(BaseModel):
    """Liveness probe. Used by k8s + uptime monitors."""

    status: str
    timestamp: str


class DependencyHealth(BaseModel):
    """One row in the deep-health table — status + optional human note."""

    name: str
    status: str  # "ok" | "degraded" | "down"
    detail: str | None = None


class DeepHealthResponse(BaseModel):
    """Readiness probe — checks DB + Redis + provider config.

    Returns 200 even when components are degraded so the caller can see the
    breakdown. K8s readiness logic decides whether to remove the pod from
    rotation based on the per-component ``status`` field.
    """

    status: str  # aggregate: "ok" if all deps "ok", "degraded" otherwise
    timestamp: str
    dependencies: list[DependencyHealth]


# ---- Errors ---------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Uniform error envelope.

    Every non-2xx response from the API uses this shape. ``error_code`` is
    machine-readable (e.g. ``"rate_limited"``, ``"profile_not_found"``),
    while ``detail`` is the human message.
    """

    error_code: str
    detail: str
    trace_id: str | None = None
