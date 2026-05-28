"""Pydantic schemas for translation log persistence.

``TranslationLogCreate`` is the write boundary: the ``record_log`` stage
builds one of these from ``PipelineContext`` and hands it to the repository.

The schema mirrors the post-sub-proyek-I ``translation_logs`` table — leaner
than the pre-I schema (denormalised stats like profile_slug/quality_mode/
text-length/hash and prompt-template-version are dropped; tenant_id and
profile_id are custom-format strings, not UUIDs).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TranslationLogCreate(BaseModel):
    """All fields needed to insert one row into ``translation_logs``."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Identity / correlation
    trace_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    batch_index: int | None = None

    # Multi-tenancy (custom-ID format strings per ADR-040; FK SET NULL on delete)
    tenant_id: str | None = None
    profile_id: str | None = None

    # Request
    source_lang: str | None = Field(default=None, max_length=8)
    target_lang: str = Field(min_length=1, max_length=8)
    source_text: str

    # Response (nullable on error)
    translated_text: str | None = None

    # Model & cost
    model_id: str | None = Field(default=None, max_length=100)
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None

    # Pipeline outcome
    status: Literal["success", "failed"]
    cached: bool = False
    cache_key: str | None = Field(default=None, max_length=64)
    latency_ms: Decimal | None = None
    error_code: str | None = Field(default=None, max_length=60)
    error_detail: str | None = None

    # Prompt (Jinja-rendered system prompt actually sent to the LLM)
    rendered_prompt: str | None = None

    # Language detection (sub-proyek C)
    detected_source_lang: str | None = Field(default=None, max_length=8)
    detected_output_lang: str | None = Field(default=None, max_length=8)
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None

    # Full agent activities list (sub-proyek G+C). JSONB-serialised.
    agentic_activities: list[dict[str, Any]] | None = None

    # Open-ended metadata
    request_metadata: dict[str, Any] | None = None

    # Timing
    started_at: datetime
    completed_at: datetime | None = None


class TranslationLogRead(BaseModel):
    """Read shape - placeholder; future dashboard sub-proyek implements read methods."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    log_id: uuid.UUID
    trace_id: uuid.UUID | None
    batch_id: uuid.UUID | None
    batch_index: int | None

    tenant_id: str | None
    profile_id: str | None

    source_lang: str | None
    target_lang: str
    source_text: str
    translated_text: str | None

    model_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None

    status: Literal["success", "failed"]
    cached: bool
    cache_key: str | None
    latency_ms: Decimal | None

    rendered_prompt: str | None
    detected_source_lang: str | None
    detected_output_lang: str | None
    source_lang_mismatch: bool | None
    output_lang_mismatch: bool | None
    agentic_activities: list[dict[str, Any]] | None
    request_metadata: dict[str, Any] | None
    error_code: str | None
    error_detail: str | None
    started_at: datetime
    completed_at: datetime | None
