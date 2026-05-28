"""Pipeline stages - each one a small, single-purpose async function.

Per CLAUDE.md principle #5 ("Stage isolation"), each stage:

- Takes the shared :class:`PipelineContext` and any dependencies it needs.
- Mutates the context (or sets a single field) and returns ``None`` - except
  ``cache_lookup`` which returns a boolean signalling "short-circuit yes/no".
- Logs a single structured event so a request's journey through the pipeline
  is reconstructible from logs.
- Is independently testable with mocked dependencies.

The orchestrator in :mod:`src.pipeline.pipeline` is what wires them together.
"""

from __future__ import annotations

import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.db.models import GlossaryTerm, StyleExample
    from src.iso_languages.repository import IsoLanguageRepository
    from src.pipeline.agents.base import AgenticActivity
    from src.service.repository import ServiceRepository
    from src.tenant_profile.resolver import ResolvedTenantProfile, TenantProfileResolver

from jinja2 import Environment

from src.cache.base import CacheBackend
from src.cache.key import compute_cache_key
from src.config.logging import get_logger
from src.pipeline.compliance import (
    ComplianceViolation,
    compute_glossary_compliance,
)
from src.pipeline.errors import LanguageNotAllowedError
from src.pipeline.schemas import PipelineRequest, PipelineResult
from src.providers.base import (
    TranslationOptions,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)
from src.translation_logs.repository import TranslationLogRepository
from src.translation_logs.sanitize import sanitize_error
from src.translation_logs.schemas import TranslationLogCreate

log = get_logger(__name__)

# Few-shot cap. Three examples is enough to convey style without ballooning
# the prompt; if a profile has more, we just take the first three after
# language-pair filtering.
MAX_FEW_SHOT_EXAMPLES = 3

# Sentinel used in the cache key + prompt when the caller didn't specify a
# source language. All "auto" callers share the same cache namespace so they
# can amortise each other's translations.
AUTO_LANG_SENTINEL = "auto"


@dataclass
class PipelineContext:
    """Mutable bag of state threaded through the pipeline."""

    request: PipelineRequest
    trace_id: str
    started_at_perf: float  # ``time.perf_counter()`` snapshot for total latency
    started_at: datetime  # wall-clock start for the log row

    # Populated by stages as the pipeline runs.
    normalized_text: str = ""
    # Sub-proyek K: flat ResolvedTenantProfile dataclass — no more joinedload
    # ORM blob; denormalized snapshot fields + service tone/audience.
    resolved_tenant_profile: ResolvedTenantProfile | None = None
    cache_key: str | None = None
    cached_result: PipelineResult | None = None
    selected_glossary: list[GlossaryTerm] = field(default_factory=list)
    selected_examples: list[StyleExample] = field(default_factory=list)
    # Sub-proyek K: flat dict assembled by build_jinja_context, consumed
    # by build_prompt (and future per-agent prompt templates that share
    # the same context surface).
    jinja_context: dict[str, Any] | None = None
    rendered_prompt: str = ""
    translation_result: TranslationResult | None = None
    compliance_score: float = 1.0
    compliance_violations: list[ComplianceViolation] = field(default_factory=list)

    # Populated by the orchestrator/record_log stage.
    status: str = "success"  # 'success' | 'failed', overridden in except block
    error_code: str | None = None
    error_detail: str | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    provider_duration_ms: int | None = None
    log_id: uuid.UUID | None = None

    # Populated by run_agents (sub-proyek G+C).
    agentic_activities: list[AgenticActivity] = field(default_factory=list)
    detected_source_lang: str | None = None
    detected_output_lang: str | None = None
    source_lang_mismatch: bool | None = None
    output_lang_mismatch: bool | None = None


# ---- 1. validate_and_normalize --------------------------------------------


async def validate_and_normalize(ctx: PipelineContext) -> None:
    """Strip whitespace, NFC-normalise unicode, and reject empty text."""
    start = time.perf_counter()
    text = ctx.request.text.strip()
    text = unicodedata.normalize("NFC", text)
    if not text:
        raise ValueError("Translation text is empty after normalization")

    target = ctx.request.target_lang.strip()
    if not target:
        raise ValueError("target_lang must be a non-empty language code")

    ctx.normalized_text = text
    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="validate_and_normalize",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        text_length=len(text),
    )


# ---- 2. load_resolved_tenant_profile --------------------------------------


async def load_resolved_tenant_profile(
    ctx: PipelineContext, resolver: TenantProfileResolver
) -> None:
    """Load the tenant_profile + tenant + service detail.

    Sub-proyek K: resolver returns a flat ``ResolvedTenantProfile`` dataclass
    (no joinedload — denormalized columns + by-name catalog lookups). Done
    BEFORE the cache lookup because the cache key includes ``profile_id``.
    """
    start = time.perf_counter()
    ctx.resolved_tenant_profile = await resolver.resolve(ctx.request.profile_id)
    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="load_resolved_tenant_profile",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        profile_id=ctx.resolved_tenant_profile.profile_id,
        service_name=ctx.resolved_tenant_profile.service_name,
    )


# ---- 2b. validate_target_language -----------------------------------------


async def validate_target_language(ctx: PipelineContext) -> None:
    """Reject ``target_lang`` if not in ``allowed_language``. NULL = all allowed.

    Runs after ``load_resolved_tenant_profile`` so ``ctx.resolved_tenant_profile``
    is populated. Raises :class:`LanguageNotAllowedError`, which the orchestrator's
    try/except logs as ``ctx.error_code = "language_not_allowed"`` and re-raises
    so the API layer surfaces it as HTTP 400.

    Empty list (``[]``) means "no language allowed" — a degenerate seed state
    we still honour by rejecting everything. NULL means "all languages allowed"
    (the seed's most permissive pattern).
    """
    assert (
        ctx.resolved_tenant_profile is not None
    ), "load_resolved_tenant_profile must run before validate_target_language"
    allowed = ctx.resolved_tenant_profile.allowed_language
    if allowed is None:
        log.debug(
            "pipeline.stage",
            trace_id=ctx.trace_id,
            stage="validate_target_language",
            status="skipped",
            reason="allowed_language_null",
        )
        return
    if ctx.request.target_lang not in allowed:
        raise LanguageNotAllowedError(target_lang=ctx.request.target_lang, allowed=allowed)
    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="validate_target_language",
        status="ok",
    )


# ---- 3. cache_lookup ------------------------------------------------------


async def cache_lookup(ctx: PipelineContext, cache: CacheBackend, model_id: str) -> bool:
    """Compute the cache key, probe Redis, and short-circuit on hit.

    The cache key composition includes ``profile_id`` (which encapsulates
    tenant + position + service). When the operator changes the underlying
    service glossary or examples we don't auto-invalidate - that's an
    MVP-accepted limitation; operators can FLUSHDB to force a refresh.
    """
    assert ctx.resolved_tenant_profile is not None, "load_resolved_tenant_profile must run first"
    start = time.perf_counter()

    ctx.cache_key = compute_cache_key(
        text=ctx.normalized_text,
        source_lang=ctx.request.source_lang or AUTO_LANG_SENTINEL,
        target_lang=ctx.request.target_lang,
        profile_slug=ctx.resolved_tenant_profile.profile_id,
        profile_version=1,
        model_id=model_id,
    )

    raw = await cache.get(ctx.cache_key)
    duration_ms = (time.perf_counter() - start) * 1000.0

    if raw is None:
        log.debug(
            "pipeline.stage",
            trace_id=ctx.trace_id,
            stage="cache_lookup",
            duration_ms=duration_ms,
            status="miss",
        )
        return False

    raw = dict(raw)
    raw["cached"] = True
    raw["cost_usd"] = Decimal("0")
    raw["latency_ms"] = duration_ms
    ctx.cached_result = PipelineResult.model_validate(raw)
    log.info(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="cache_lookup",
        duration_ms=duration_ms,
        status="hit",
        cache_key=ctx.cache_key,
    )
    return True


# ---- 4. preprocess ---------------------------------------------------------


async def preprocess(ctx: PipelineContext, service_repo: ServiceRepository) -> None:
    """Fetch service-scoped glossary terms and style examples.

    Sub-proyek K: looks up the service by name (denormalized snapshot)
    instead of relying on a joinedload-attached ORM blob. If the named
    service is missing from the catalog (catalog drift, deleted seed row),
    we log a warning and continue with empty glossary/examples — the
    prompt still renders, just without service-specific guidance.
    """
    assert ctx.resolved_tenant_profile is not None
    start = time.perf_counter()

    source_lang = ctx.detected_source_lang or ctx.request.source_lang or AUTO_LANG_SENTINEL
    target_lang = ctx.request.target_lang
    service_name = ctx.resolved_tenant_profile.service_name

    service = await service_repo.get_by_name(service_name)
    if service is None:
        log.warning(
            "pipeline.preprocess.service_not_found",
            trace_id=ctx.trace_id,
            service_name=service_name,
        )
        ctx.selected_glossary = []
        ctx.selected_examples = []
    else:
        glossary = await service_repo.list_glossary_for_service(
            service.service_id, source_lang, target_lang
        )
        examples = await service_repo.list_examples_for_service(
            service.service_id, source_lang, target_lang
        )
        ctx.selected_glossary = glossary
        ctx.selected_examples = list(examples)[:MAX_FEW_SHOT_EXAMPLES]

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="preprocess",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        selected_glossary=len(ctx.selected_glossary),
        selected_examples=len(ctx.selected_examples),
    )


# ---- 4b. build_jinja_context ----------------------------------------------


async def build_jinja_context(ctx: PipelineContext, iso_repo: IsoLanguageRepository) -> None:
    """Assemble the flat Jinja context dict for ALL prompt templates.

    Single source of truth for the variables every prompt template can rely
    on. Sub-proyek K keeps this flat (no ``tenant.company.x`` deep access)
    because the FK relationships were dropped — values come from the
    denormalized ``ResolvedTenantProfile`` snapshot + a by-code lookup on
    ``iso_languages`` for human-readable language names.

    Source resolution order for ``source_lang_code``:
      1. ``ctx.detected_source_lang`` (set by lang_detect_input agent)
      2. ``ctx.request.source_lang`` (caller-provided)
      3. ``""`` (auto-detect mode, no hint available)

    Fallback for ISO name miss: use the code itself so the prompt is still
    grammatically usable — better than failing on a catalog gap.
    """
    assert (
        ctx.resolved_tenant_profile is not None
    ), "load_resolved_tenant_profile must run before build_jinja_context"
    tp = ctx.resolved_tenant_profile

    source_code = ctx.detected_source_lang or ctx.request.source_lang or ""
    target_code = ctx.request.target_lang

    source_name = ""
    if source_code:
        resolved_source_name = await iso_repo.get_name(source_code)
        source_name = resolved_source_name if resolved_source_name is not None else source_code
    resolved_target_name = await iso_repo.get_name(target_code)
    target_name = resolved_target_name if resolved_target_name is not None else target_code

    ctx.jinja_context = {
        "tenant_name": tp.tenant_name,
        "country_name": tp.country_name,
        "company_name": tp.company_name,
        "department_name": tp.department_name,
        "position_name": tp.position_name,
        "service_name": tp.service_name,
        "service_tone": tp.service_tone,
        "service_target_audience": tp.service_target_audience,
        "source_lang_code": source_code,
        "source_lang_name": source_name,
        "target_lang_code": target_code,
        "target_lang_name": target_name,
        "glossary_terms": list(ctx.selected_glossary),
        "style_examples": list(ctx.selected_examples),
        "text": ctx.normalized_text,
    }

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="build_jinja_context",
        status="ok",
        source_lang_name=source_name,
        target_lang_name=target_name,
        glossary_count=len(ctx.selected_glossary),
    )


# ---- 5. build_prompt -------------------------------------------------------


async def build_prompt(ctx: PipelineContext, template_env: Environment) -> None:
    """Render the Jinja translate template into ``ctx.rendered_prompt``.

    Sub-proyek K: uses the flat ``ctx.jinja_context`` dict built by
    ``build_jinja_context``. No more deep ``tenant.company.company_name``
    access — relationships are gone (migration 006 denormalization).
    """
    assert ctx.jinja_context is not None, "build_jinja_context must run before build_prompt"
    start = time.perf_counter()

    template = template_env.get_template("translate.jinja")
    ctx.rendered_prompt = template.render(**ctx.jinja_context)

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="build_prompt",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        prompt_length=len(ctx.rendered_prompt),
    )


# ---- 6. translate (provider call) -----------------------------------------


async def translate(ctx: PipelineContext, provider: TranslationProvider) -> None:
    """Hand the rendered prompt to the provider and capture the result."""
    start = time.perf_counter()
    request = TranslationRequest(
        text=ctx.normalized_text,
        source_lang=ctx.request.source_lang or AUTO_LANG_SENTINEL,
        target_lang=ctx.request.target_lang,
        profile={"profile_id": ctx.request.profile_id},
        options=TranslationOptions(
            temperature=ctx.request.options.temperature,
            max_tokens=ctx.request.options.max_tokens,
            system_prompt_override=ctx.rendered_prompt,
        ),
    )
    ctx.translation_result = await provider.translate(request)

    log.info(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="translate",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        provider=ctx.translation_result.provider,
        model=ctx.translation_result.model,
        tokens_input=ctx.translation_result.tokens_input,
        tokens_output=ctx.translation_result.tokens_output,
        cost_usd=str(ctx.translation_result.cost_usd),
    )


# ---- 7. postprocess_and_verify --------------------------------------------


async def postprocess_and_verify(ctx: PipelineContext) -> None:
    """Compute glossary compliance and log violations as warnings.

    We do NOT refuse the translation when compliance is low - by design.
    The score becomes a quality signal callers can use to gate on without
    breaking flows.
    """
    assert ctx.translation_result is not None
    start = time.perf_counter()

    # Adapt the new ORM rows to the shape compute_glossary_compliance expects:
    # source_term, target_term, is_forbidden attributes (already match).
    ctx.compliance_score, ctx.compliance_violations = compute_glossary_compliance(
        translation=ctx.translation_result.translation,
        source_text=ctx.normalized_text,
        glossary_terms=ctx.selected_glossary,
    )

    if ctx.compliance_violations:
        log.warning(
            "pipeline.glossary_violations",
            trace_id=ctx.trace_id,
            score=ctx.compliance_score,
            violations=[
                {
                    "source": v.source_term,
                    "expected": v.expected_target,
                    "is_forbidden": v.is_forbidden,
                    "found": v.found_in_translation,
                }
                for v in ctx.compliance_violations
            ],
        )

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="postprocess_and_verify",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        compliance=ctx.compliance_score,
    )


# ---- 8. cache_write -------------------------------------------------------


async def cache_write(ctx: PipelineContext, result: PipelineResult, cache: CacheBackend) -> None:
    """Persist the final ``PipelineResult`` so the next identical request hits."""
    assert ctx.cache_key is not None, "cache_lookup must have run to set the key"
    start = time.perf_counter()

    payload: dict[str, Any] = result.model_dump(mode="json")
    await cache.set(ctx.cache_key, payload)

    log.debug(
        "pipeline.stage",
        trace_id=ctx.trace_id,
        stage="cache_write",
        duration_ms=(time.perf_counter() - start) * 1000.0,
        status="ok",
        cache_key=ctx.cache_key,
    )


# ---- 9. record_log -------------------------------------------------------


async def record_log(
    ctx: PipelineContext,
    repo: TranslationLogRepository,
    *,
    model_id: str,
) -> None:
    """Persist one ``translation_logs`` row from the context.

    This function MUST NEVER raise: it runs in the pipeline's ``finally``
    block, and a raise here would mask the original exception (if any).
    All exceptions are caught and logged as warnings; ``ctx.log_id`` stays
    ``None`` when the write fails so the response signals "log not persisted"
    (per ADR-013 / ADR-027).
    """
    start = time.perf_counter()
    try:
        payload = _build_log_payload(ctx, model_id=model_id)
        if payload is None:
            log.debug(
                "pipeline.stage",
                trace_id=ctx.trace_id,
                stage="record_log",
                status="skipped",
                reason="incomplete_context",
            )
            return
        ctx.log_id = await repo.create(payload)
        log.debug(
            "pipeline.stage",
            trace_id=ctx.trace_id,
            stage="record_log",
            duration_ms=(time.perf_counter() - start) * 1000.0,
            status="ok",
            log_id=str(ctx.log_id),
        )
    except Exception as exc:
        log.warning(
            "translation_log.write_failed",
            trace_id=ctx.trace_id,
            error=str(exc)[:500],
            error_type=type(exc).__name__,
        )


def _build_log_payload(
    ctx: PipelineContext,
    *,
    model_id: str,
) -> TranslationLogCreate | None:
    """Project the PipelineContext into a TranslationLogCreate payload.

    Returns ``None`` when the context is fundamentally too incomplete to
    form a valid payload. Returning instead of raising means the ``finally``
    block can gracefully skip the write.
    """
    if ctx.completed_at is None:
        return None

    cache_hit = ctx.cached_result is not None
    if cache_hit:
        translated_text = ctx.cached_result.translation if ctx.cached_result else None
        input_tokens = None
        output_tokens = None
        cost_usd = None
        rendered_prompt = (
            ctx.cached_result.prompt_applied
            if ctx.cached_result and ctx.cached_result.prompt_applied
            else None
        )
    else:
        translated_text = ctx.translation_result.translation if ctx.translation_result else None
        input_tokens = ctx.translation_result.tokens_input if ctx.translation_result else None
        output_tokens = ctx.translation_result.tokens_output if ctx.translation_result else None
        cost_usd = Decimal(str(ctx.translation_result.cost_usd)) if ctx.translation_result else None
        rendered_prompt = ctx.rendered_prompt or None

    latency_ms: Decimal | None = None
    if ctx.duration_ms is not None:
        latency_ms = Decimal(ctx.duration_ms)

    profile_id = (
        ctx.resolved_tenant_profile.profile_id if ctx.resolved_tenant_profile is not None else None
    )

    # trace_id is a hex string on the context; serialise it as UUID for the row.
    trace_uuid: uuid.UUID | None
    try:
        trace_uuid = uuid.UUID(ctx.trace_id)
    except (ValueError, AttributeError):
        trace_uuid = None

    return TranslationLogCreate(
        trace_id=trace_uuid,
        batch_id=ctx.request.batch_id,
        batch_index=ctx.request.batch_index,
        tenant_id=ctx.request.tenant_id if ctx.request.tenant_id else None,
        profile_id=profile_id,
        source_lang=ctx.request.source_lang,
        target_lang=ctx.request.target_lang,
        source_text=ctx.normalized_text or ctx.request.text,
        translated_text=translated_text,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        status=ctx.status,  # type: ignore[arg-type]
        cached=cache_hit,
        # compute_cache_key returns "translation:{hex}"; strip the namespace
        # prefix so we stay within the column's max width and only store the
        # entropy-bearing portion.
        cache_key=ctx.cache_key.split(":", 1)[-1] if ctx.cache_key else None,
        latency_ms=latency_ms,
        error_code=ctx.error_code,
        error_detail=sanitize_error(ctx.error_detail) if ctx.error_detail else None,
        rendered_prompt=rendered_prompt,
        detected_source_lang=ctx.detected_source_lang,
        detected_output_lang=ctx.detected_output_lang,
        source_lang_mismatch=ctx.source_lang_mismatch,
        output_lang_mismatch=ctx.output_lang_mismatch,
        agentic_activities=(
            [act.model_dump(mode="json") for act in ctx.agentic_activities]
            if ctx.agentic_activities
            else None
        ),
        request_metadata=ctx.request.request_metadata,
        started_at=ctx.started_at,
        completed_at=ctx.completed_at,
    )


# ---- Back-compat alias ----------------------------------------------------

# Some older callers/tests may still reference ``load_resolved_profile``.
# Provide an alias so existing imports don't have to be rewritten in lockstep.
load_resolved_profile = load_resolved_tenant_profile
