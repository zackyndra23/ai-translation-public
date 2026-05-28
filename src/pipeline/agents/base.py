"""Agent Protocol + AgenticActivity Pydantic.

Per ADR-031, agents soft-fail (don't block primary translate). Per ADR-032,
``AgenticActivity.result`` is ``dict[str, Any]`` not typed per agent — shape
varies, JSONB serialization-friendly, future agents extend without schema
migration.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from src.pipeline.stages import PipelineContext


class AgenticActivity(BaseModel):
    """One agent's execution record — captured per-request, propagated to
    response + log (JSONB) + Redis cache.

    All LLM-call fields (model_id, prompt_applied, input_tokens,
    output_tokens, cost_usd) are nullable so future non-LLM agents (e.g.,
    regex-based glossary enforcer) can emit activities without bogus zeros.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    agent_type: str  # "language_detection" | "translation"
    group_index: int

    model_id: str | None = None
    prompt_applied: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: Decimal | None = None

    latency_ms: float
    status: Literal["success", "failed", "skipped"]
    started_at: datetime
    completed_at: datetime

    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_detail: str | None = None


@runtime_checkable
class Agent(Protocol):
    """Protocol every agent implements.

    Non-translate agents must catch their own exceptions and emit an
    AgenticActivity with status='failed'. The TranslateAgent is allowed to
    propagate exceptions — the orchestrator's ``_safe_run`` wrapper captures
    them so the rest of the group still runs.
    """

    name: str
    agent_type: str
    group_index: int

    async def run(self, ctx: PipelineContext) -> AgenticActivity: ...
