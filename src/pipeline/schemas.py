"""Pipeline request / result schemas.

These are the public objects every caller of :class:`TranslationPipeline`
deals with. They live in their own module (and not inside ``pipeline.py``)
so that consumers can import them without dragging in the orchestrator's
runtime dependencies — useful for typing the eventual REST layer (Phase 5).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.pipeline.agents.base import AgenticActivity
from src.providers.base import TranslationOptions


class PipelineRequest(BaseModel):
    """Inbound translation request.

    ``source_lang=None`` means "let the model detect it". We pass that hint
    through to the prompt; the model returns a translation and we record
    whatever the request told us into the result (so the cache key remains
    stable for "auto" callers — they all share the same cache namespace).

    ``batch_id`` + ``batch_index`` are populated by the ``/translate/batch``
    endpoint so log rows from one batch share an identifier; for single
    ``/translate`` calls both are ``None``.

    ``request_metadata`` is an open-ended dict echoed through to the log row
    (SDK version, user agent, page url, etc.); not used by the pipeline itself.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    text: str = Field(min_length=1)
    target_lang: str = Field(min_length=2, max_length=5)
    profile_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    source_lang: str | None = Field(default=None, max_length=5)
    options: TranslationOptions = Field(default_factory=TranslationOptions)
    batch_id: uuid.UUID | None = None
    batch_index: int | None = None
    request_metadata: dict[str, Any] | None = None


class PipelineResult(BaseModel):
    """Outbound translation result.

    ``cached=True`` means the result came from Redis. In that case
    ``cost_usd`` is zero (we didn't pay the API for this call) and
    ``latency_ms`` reflects the cache lookup, not the original translation.
    ``metadata`` is the catch-all for diagnostic information that doesn't
    have a fixed schema — trace_id, profile_version, resolution_chain,
    glossary_violation_count, etc.

    ``log_id`` is populated by the pipeline orchestrator after the
    ``record_log`` stage runs. ``None`` means the log write failed (DB
    unavailable) and the response had to be returned without persistent
    correlation — clients can still use ``metadata["trace_id"]`` for that.

    ``prompt_applied`` is the full Jinja-rendered system prompt sent to the
    LLM (includes glossary block, style examples, tone, and task
    instructions). Useful for debugging prompt construction. ``None`` when
    cached from a pre-Phase-D entry that didn't store the prompt.
    """

    translation: str
    source_lang: str
    target_lang: str
    cached: bool
    provider: str
    model: str
    latency_ms: float
    cost_usd: Decimal
    glossary_compliance: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    log_id: uuid.UUID | None = None
    prompt_applied: str | None = None
    agentic_activities: list[AgenticActivity] = Field(default_factory=list)
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None
