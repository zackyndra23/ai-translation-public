"""TranslateAgent — wraps the main LLM translate call as an Agent.

Unlike LangDetectAgent, this agent propagates provider errors (primary value
of the pipeline — failures must surface). The orchestrator's _safe_run
wraps both kinds: for translation agent_type, it captures the activity and
re-raises after the group completes.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.pipeline.agents.base import AgenticActivity
from src.providers.base import (
    TranslationOptions,
    TranslationProvider,
    TranslationRequest,
)

if TYPE_CHECKING:
    from src.pipeline.stages import PipelineContext


class TranslateAgent:
    """Main translation agent. Sonnet-backed. Errors propagate.

    Reads ctx.normalized_text, ctx.rendered_prompt (from existing
    build_prompt stage), ctx.request (for source_lang/target_lang options),
    and emits an AgenticActivity with the translation result.

    Also mirrors the result into ctx.translation_result so legacy stages
    (postprocess_and_verify, cache_write) that still reference that field
    continue to work without modification.
    """

    agent_type = "translation"

    def __init__(
        self,
        *,
        name: str,
        group_index: int,
        provider: TranslationProvider,
        model_id: str,
    ) -> None:
        self.name = name
        self.group_index = group_index
        self._provider = provider
        self._model_id = model_id

    async def run(self, ctx: PipelineContext) -> AgenticActivity:
        # Deferred import avoids a circular: stages.py imports from agents/base,
        # so importing stages at module level here would form a cycle.
        from src.pipeline.stages import AUTO_LANG_SENTINEL

        started = datetime.now(UTC)
        perf_start = time.perf_counter()

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
        # No try/except — primary value, errors propagate per ADR-031.
        # The orchestrator catches, records, and re-raises so the pipeline
        # can still log the failure context cleanly.
        result = await self._provider.translate(request)

        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0

        # Mirror into ctx.translation_result for legacy stages (postprocess,
        # cache_write) that still reference it.
        ctx.translation_result = result

        return AgenticActivity(
            name=self.name,
            agent_type=self.agent_type,
            group_index=self.group_index,
            model_id=self._model_id,
            prompt_applied=ctx.rendered_prompt,
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
            cost_usd=Decimal(str(result.cost_usd)),
            latency_ms=latency_ms,
            status="success",
            started_at=started,
            completed_at=completed,
            result={
                "translation": result.translation,
                "stop_reason": result.metadata.get("stop_reason"),
            },
        )
