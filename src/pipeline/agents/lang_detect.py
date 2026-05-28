"""LangDetectAgent — single class, reusable for input + output direction.

Calls Claude Haiku with a tight system prompt that returns just the
ISO 639-1 code. The result.detected_lang field is what the pipeline post-
processes to compute source_lang_mismatch and output_lang_mismatch.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, cast

from src.pipeline.agents.base import AgenticActivity
from src.providers.base import (
    TranslationOptions,
    TranslationProvider,
    TranslationRequest,
)
from src.translation_logs.sanitize import sanitize_error

if TYPE_CHECKING:
    from src.pipeline.stages import PipelineContext

_DETECT_SYSTEM_PROMPT = (
    "You are a language identifier. Reply with ONLY the ISO 639-1 code of "
    "the language of the input text. Examples: 'en' for English, 'id' for "
    "Indonesian, 'fr' for French, 'ja' for Japanese. No quotes, no "
    "explanation, just the 2-letter lowercase code."
)


class LangDetectAgent:
    """Agent that detects the language of either the input source text or the
    translated output text, depending on ``text_source``.

    Soft-fail (ADR-031): any exception captured as status='failed' activity.
    The agent never raises — it returns an AgenticActivity with
    status='failed' so the orchestrator's group can continue running.
    """

    agent_type = "language_detection"

    def __init__(
        self,
        *,
        name: str,
        group_index: int,
        text_source: Literal["input", "output"],
        provider: TranslationProvider,
        model_id: str,
    ) -> None:
        self.name = name
        self.group_index = group_index
        self.text_source = text_source
        self._provider = provider
        self._model_id = model_id

    async def run(self, ctx: PipelineContext) -> AgenticActivity:
        text = self._resolve_text(ctx)
        if not text:
            return self._skipped(reason="text_unavailable")

        started = datetime.now(UTC)
        perf_start = time.perf_counter()
        try:
            request = TranslationRequest(
                text=text,
                source_lang="auto",
                target_lang="en",  # placeholder; system prompt drives detection
                options=TranslationOptions(
                    temperature=0.0,
                    max_tokens=8,
                    system_prompt_override=_DETECT_SYSTEM_PROMPT,
                ),
            )
            result = await self._provider.translate(request)
        except Exception as exc:
            completed = datetime.now(UTC)
            latency_ms = (time.perf_counter() - perf_start) * 1000.0
            return AgenticActivity(
                name=self.name,
                agent_type=self.agent_type,
                group_index=self.group_index,
                model_id=self._model_id,
                prompt_applied=_DETECT_SYSTEM_PROMPT,
                latency_ms=latency_ms,
                status="failed",
                started_at=started,
                completed_at=completed,
                error_code=getattr(exc, "error_code", None) or type(exc).__name__,
                error_detail=sanitize_error(str(exc)),
            )

        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0
        detected = result.translation.strip().lower()[:5]
        return AgenticActivity(
            name=self.name,
            agent_type=self.agent_type,
            group_index=self.group_index,
            model_id=self._model_id,
            prompt_applied=_DETECT_SYSTEM_PROMPT,
            input_tokens=result.tokens_input,
            output_tokens=result.tokens_output,
            cost_usd=Decimal(str(result.cost_usd)),
            latency_ms=latency_ms,
            status="success",
            started_at=started,
            completed_at=completed,
            result={"detected_lang": detected},
        )

    def _resolve_text(self, ctx: PipelineContext) -> str | None:
        if self.text_source == "input":
            return ctx.normalized_text or None
        # For output direction, look for a completed translate activity whose
        # result carries the translated text. The TranslateAgent stores it
        # under result["translation"].
        for activity in ctx.agentic_activities:
            if (
                activity.agent_type == "translation"
                and activity.status == "success"
                and activity.result
                and "translation" in activity.result
            ):
                return cast(str, activity.result["translation"])
        return None

    def _skipped(self, *, reason: str) -> AgenticActivity:
        now = datetime.now(UTC)
        return AgenticActivity(
            name=self.name,
            agent_type=self.agent_type,
            group_index=self.group_index,
            latency_ms=0.0,
            status="skipped",
            started_at=now,
            completed_at=now,
            result={"reason": reason},
        )
