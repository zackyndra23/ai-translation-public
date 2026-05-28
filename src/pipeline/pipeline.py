"""TranslationPipeline - orchestrates provider call + profile resolution.

The class stays thin on purpose: every meaningful step is a stage in
:mod:`src.pipeline.stages`. The orchestrator wires them together, generates
a trace id, and assembles the final :class:`PipelineResult`.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader

from src.cache.base import CacheBackend
from src.config.logging import get_logger
from src.pipeline import stages
from src.pipeline.schemas import PipelineRequest, PipelineResult
from src.providers.base import TranslationProvider
from src.translation_logs.repository import TranslationLogRepository

if TYPE_CHECKING:
    from src.iso_languages.repository import IsoLanguageRepository
    from src.service.repository import ServiceRepository
    from src.tenant_profile.resolver import TenantProfileResolver

log = get_logger(__name__)

# Default template directory - sits next to this file so the path resolves
# the same way whether we're running from the repo root, a tests directory,
# or an installed wheel.
_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def build_template_env(template_dir: Path | None = None) -> Environment:
    """Construct the Jinja2 ``Environment`` the pipeline uses."""
    return Environment(
        loader=FileSystemLoader(template_dir or _DEFAULT_TEMPLATE_DIR),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _populate_mismatch_flags(ctx: stages.PipelineContext) -> None:
    """Read detection results from ctx.agentic_activities and write mismatch flags."""
    for activity in ctx.agentic_activities:
        if activity.agent_type != "language_detection":
            continue
        if activity.status != "success" or not activity.result:
            continue
        detected = activity.result.get("detected_lang")
        if not detected:
            continue
        if activity.name == "lang_detect_input":
            ctx.detected_source_lang = detected
            claimed = ctx.request.source_lang
            ctx.source_lang_mismatch = None if claimed is None else (detected != claimed)
        elif activity.name == "lang_detect_output":
            ctx.detected_output_lang = detected
            ctx.output_lang_mismatch = detected != ctx.request.target_lang


class TranslationPipeline:
    """High-level translation entrypoint."""

    def __init__(
        self,
        *,
        provider: TranslationProvider,
        haiku_provider: TranslationProvider,
        cache: CacheBackend,
        resolver: TenantProfileResolver,
        service_repo: ServiceRepository,
        iso_repo: IsoLanguageRepository,
        template_env: Environment | None = None,
        model_id: str,
        haiku_model_id: str,
        log_repo: TranslationLogRepository | None = None,
    ) -> None:
        self._provider = provider
        self._haiku_provider = haiku_provider
        self._cache = cache
        self._resolver = resolver
        self._service_repo = service_repo
        # Sub-proyek K: needed by build_jinja_context to resolve language codes
        # to human-readable names for prompt grammaticality.
        self._iso_repo = iso_repo
        self._template_env = template_env or build_template_env()
        self._model_id = model_id
        self._haiku_model_id = haiku_model_id
        self._log_repo = log_repo

    async def translate(self, request: PipelineRequest) -> PipelineResult:
        """Run the request through every stage and return the final result."""
        trace_id = uuid.uuid4().hex
        started_at_wall = datetime.now(UTC)
        ctx = stages.PipelineContext(
            request=request,
            trace_id=trace_id,
            started_at_perf=time.perf_counter(),
            started_at=started_at_wall,
        )

        log.info(
            "pipeline.start",
            trace_id=trace_id,
            tenant_id=str(request.tenant_id),
            profile_id=request.profile_id,
            target_lang=request.target_lang,
            source_lang=request.source_lang,
            text_length=len(request.text),
        )

        base_result: PipelineResult | None = None
        try:
            await stages.validate_and_normalize(ctx)
            await stages.load_resolved_tenant_profile(ctx, self._resolver)
            # Sub-proyek K: enforce allowed_language gate BEFORE cache lookup
            # so a disallowed target_lang fails fast (no cache write either).
            await stages.validate_target_language(ctx)

            if await stages.cache_lookup(ctx, self._cache, self._model_id):
                assert ctx.cached_result is not None
                base_result = ctx.cached_result
                self._log_end(ctx, status="cache_hit")
            else:
                from src.pipeline.agents.orchestrator import build_agents, run_agents

                await stages.preprocess(ctx, self._service_repo)
                # Sub-proyek K: build the flat Jinja context BEFORE rendering;
                # build_prompt now consumes the dict, not the ORM blob.
                await stages.build_jinja_context(ctx, self._iso_repo)
                await stages.build_prompt(ctx, self._template_env)

                agents = build_agents(
                    ctx,
                    provider=self._provider,
                    haiku_provider=self._haiku_provider,
                    sonnet_model_id=self._model_id,
                    haiku_model_id=self._haiku_model_id,
                )
                provider_start = time.perf_counter()
                await run_agents(ctx, agents)
                ctx.provider_duration_ms = int((time.perf_counter() - provider_start) * 1000.0)

                _populate_mismatch_flags(ctx)

                await stages.postprocess_and_verify(ctx)

                base_result = self._build_result(ctx)
                await stages.cache_write(ctx, base_result, self._cache)

                self._log_end(ctx, status="ok")

            ctx.status = "success"
        except Exception as e:
            ctx.status = "failed"
            ctx.error_code = getattr(e, "error_code", None) or type(e).__name__
            ctx.error_detail = str(e)
            log.error(
                "pipeline.failed",
                trace_id=trace_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
        finally:
            ctx.completed_at = datetime.now(UTC)
            ctx.duration_ms = int((time.perf_counter() - ctx.started_at_perf) * 1000.0)
            if self._log_repo is not None:
                await stages.record_log(ctx, self._log_repo, model_id=self._model_id)

        assert base_result is not None
        return base_result.model_copy(update={"log_id": ctx.log_id})

    # ---- internal helpers ---------------------------------------------------

    def _build_result(self, ctx: stages.PipelineContext) -> PipelineResult:
        assert ctx.translation_result is not None
        assert ctx.resolved_tenant_profile is not None
        total_latency_ms = (time.perf_counter() - ctx.started_at_perf) * 1000.0

        resolved_source = ctx.request.source_lang or stages.AUTO_LANG_SENTINEL

        return PipelineResult(
            translation=ctx.translation_result.translation,
            source_lang=resolved_source,
            target_lang=ctx.request.target_lang,
            cached=False,
            provider=ctx.translation_result.provider,
            model=ctx.translation_result.model,
            latency_ms=total_latency_ms,
            cost_usd=Decimal(ctx.translation_result.cost_usd),
            glossary_compliance=ctx.compliance_score,
            metadata={
                "trace_id": ctx.trace_id,
                "profile_id": ctx.resolved_tenant_profile.profile_id,
                # Sub-proyek K: ResolvedTenantProfile.service_id is Optional —
                # a profile may reference a deleted service (catalog drift).
                # None is acceptable in the metadata dict; downstream tooling
                # treats it as "service unavailable at translation time".
                "service_id": ctx.resolved_tenant_profile.service_id,
                "tokens_input": ctx.translation_result.tokens_input,
                "tokens_output": ctx.translation_result.tokens_output,
                "glossary_violations": len(ctx.compliance_violations),
                "stop_reason": ctx.translation_result.metadata.get("stop_reason"),
            },
            prompt_applied=ctx.rendered_prompt or None,
            agentic_activities=list(ctx.agentic_activities),
            detected_source_lang=ctx.detected_source_lang,
            detected_output_lang=ctx.detected_output_lang,
            source_lang_mismatch=ctx.source_lang_mismatch,
            output_lang_mismatch=ctx.output_lang_mismatch,
        )

    def _log_end(self, ctx: stages.PipelineContext, *, status: str) -> None:
        log.info(
            "pipeline.end",
            trace_id=ctx.trace_id,
            status=status,
            total_latency_ms=(time.perf_counter() - ctx.started_at_perf) * 1000.0,
        )
