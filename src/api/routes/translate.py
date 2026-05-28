"""Translate endpoints.

``POST /translate``       — single translation.
``POST /translate/batch`` — bulk translation with per-item cache hits and
                            partial-success semantics.

Batch parallelism: we use ``asyncio.gather(*, return_exceptions=True)`` so
one bad item doesn't poison the rest of the batch. Per-item failures are
surfaced in ``BatchTranslateResultItem.error`` instead of a 4xx for the
whole request.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends

from src.api.dependencies import get_pipeline
from src.api.schemas import (
    BatchTranslateItem,
    BatchTranslateRequest,
    BatchTranslateResponse,
    BatchTranslateResultItem,
    TranslateRequest,
    TranslateResponse,
)
from src.auth.dependencies import get_current_tenant_id
from src.config.logging import get_logger
from src.pipeline.pipeline import TranslationPipeline
from src.pipeline.schemas import PipelineRequest, PipelineResult
from src.providers.base import TranslationOptions

router = APIRouter(prefix="/translate", tags=["translate"])
log = get_logger(__name__)


def _to_response(result: PipelineResult) -> TranslateResponse:
    return TranslateResponse(
        translation=result.translation,
        source_lang=result.source_lang,
        target_lang=result.target_lang,
        cached=result.cached,
        provider=result.provider,
        model=result.model,
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        glossary_compliance=result.glossary_compliance,
        metadata=result.metadata,
        log_id=result.log_id,
        prompt_applied=result.prompt_applied,
        # Serialise AgenticActivity objects to plain dicts for HTTP transport.
        # Using mode="json" ensures Decimal/datetime fields round-trip cleanly
        # over JSON without the caller needing to know the internal model shape.
        agentic_activities=[a.model_dump(mode="json") for a in result.agentic_activities],
        detected_source_lang=result.detected_source_lang,
        detected_output_lang=result.detected_output_lang,
        source_lang_mismatch=result.source_lang_mismatch,
        output_lang_mismatch=result.output_lang_mismatch,
    )


def _to_pipeline_request(
    *,
    tenant_id: str,
    text: str,
    target_lang: str,
    profile_id: str,
    source_lang: str | None,
    options: TranslationOptions | None,
    batch_id: uuid.UUID | None = None,
    batch_index: int | None = None,
) -> PipelineRequest:
    return PipelineRequest(
        text=text,
        target_lang=target_lang,
        profile_id=profile_id,
        tenant_id=tenant_id,
        source_lang=source_lang,
        options=options or TranslationOptions(),
        batch_id=batch_id,
        batch_index=batch_index,
    )


@router.post("", response_model=TranslateResponse)
async def translate(
    payload: TranslateRequest,
    pipeline: TranslationPipeline = Depends(get_pipeline),
    tenant_id: str = Depends(get_current_tenant_id),
) -> TranslateResponse:
    request = _to_pipeline_request(
        tenant_id=tenant_id,
        text=payload.text,
        target_lang=payload.target_lang,
        profile_id=payload.profile_id,
        source_lang=payload.source_lang,
        options=payload.options,
    )
    result = await pipeline.translate(request)
    return _to_response(result)


@router.post("/batch", response_model=BatchTranslateResponse)
async def translate_batch(
    payload: BatchTranslateRequest,
    pipeline: TranslationPipeline = Depends(get_pipeline),
    tenant_id: str = Depends(get_current_tenant_id),
) -> BatchTranslateResponse:
    """Translate many items in parallel.

    ``asyncio.gather(return_exceptions=True)`` collects exceptions instead of
    short-circuiting, so a single bad item never sinks the whole batch.
    Per-item errors land in ``BatchTranslateResultItem.error``; successful
    items have ``error=None``.

    A single ``batch_id`` is generated once per HTTP request and threaded
    through every item's ``PipelineRequest`` so all log rows from this
    batch share an identifier (with their own ``batch_index`` for ordering).

    Concurrency: we don't currently throttle. With ``max_length=100`` in the
    request schema and the provider's own rate-limit retry behaviour, this
    is fine for MVP; a semaphore + dynamic batching is a Phase-6 optimisation.
    """
    batch_id = uuid.uuid4()

    async def _one(idx: int, item: BatchTranslateItem) -> BatchTranslateResultItem:
        try:
            result = await pipeline.translate(
                _to_pipeline_request(
                    tenant_id=tenant_id,
                    text=item.text,
                    target_lang=payload.target_lang,
                    profile_id=payload.profile_id,
                    source_lang=payload.source_lang,
                    options=payload.options,
                    batch_id=batch_id,
                    batch_index=idx,
                )
            )
            return BatchTranslateResultItem(
                id=item.id,
                text=result.translation,
                cached=result.cached,
                log_id=result.log_id,
                prompt_applied=result.prompt_applied,
                agentic_activities=[a.model_dump(mode="json") for a in result.agentic_activities],
                detected_source_lang=result.detected_source_lang,
                detected_output_lang=result.detected_output_lang,
                source_lang_mismatch=result.source_lang_mismatch,
                output_lang_mismatch=result.output_lang_mismatch,
            )
        except Exception as e:
            # Catch broadly here ON PURPOSE — a per-item failure must NOT
            # break the rest of the batch. The exception type is preserved
            # in the message for the caller to inspect. The log row for this
            # failure has already been written by record_log (in finally).
            log.warning(
                "translate.batch.item_failed",
                item_id=item.id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return BatchTranslateResultItem(
                id=item.id,
                text="",
                cached=False,
                error=f"{type(e).__name__}: {e}",
            )

    results = await asyncio.gather(*(_one(i, item) for i, item in enumerate(payload.items)))
    return BatchTranslateResponse(translations=list(results))
