"""Group-by + asyncio.gather orchestration with cancellation safety.

Per spec §4.3: agents organized into integer-indexed groups; within a group
they run in parallel via asyncio.gather; groups run sequentially.

The translate agent (agent_type='translation') is allowed to propagate
provider errors. ``_safe_run`` wraps every agent so siblings in the same
group are NOT cancelled by a translate failure mid-flight — the exception
is captured along with all sibling activities, then re-raised after the
group completes (so the pipeline's record_log finally block sees a
complete activities list).
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.pipeline.agents.base import Agent, AgenticActivity
from src.translation_logs.sanitize import sanitize_error

if TYPE_CHECKING:
    from src.pipeline.stages import PipelineContext
    from src.providers.base import TranslationProvider


async def run_agents(
    ctx: PipelineContext,
    agents: list[Agent],
) -> list[AgenticActivity]:
    """Run agents grouped by group_index, return all captured activities.

    Re-raises the translate agent's exception (if any) after recording every
    activity in the failing group, so partial results land in
    ctx.agentic_activities AND the log row.
    """
    activities: list[AgenticActivity] = []
    grouped: dict[int, list[Agent]] = {}
    for agent in agents:
        grouped.setdefault(agent.group_index, []).append(agent)

    pending_raise: BaseException | None = None
    for group_index in sorted(grouped):
        group_agents = grouped[group_index]
        gather_results = await asyncio.gather(
            *(_safe_run(agent, ctx) for agent in group_agents),
            return_exceptions=False,  # _safe_run never raises
        )
        for activity, raised in gather_results:
            activities.append(activity)
            ctx.agentic_activities.append(activity)
            if raised is not None and activity.agent_type == "translation":
                pending_raise = raised

    if pending_raise is not None:
        raise pending_raise
    return activities


async def _safe_run(
    agent: Agent,
    ctx: PipelineContext,
) -> tuple[AgenticActivity, BaseException | None]:
    """Run an agent and capture (activity, exception). Never raises.

    Non-translate agents: agent.run() catches its own errors and emits a
    status='failed' activity; raised is None.

    TranslateAgent: agent.run() propagates errors. _safe_run captures the
    exception, synthesizes a status='failed' activity, returns both.
    """
    started = datetime.now(UTC)
    perf_start = time.perf_counter()
    try:
        activity = await agent.run(ctx)
        return activity, None
    except Exception as exc:
        completed = datetime.now(UTC)
        latency_ms = (time.perf_counter() - perf_start) * 1000.0
        activity = AgenticActivity(
            name=agent.name,
            agent_type=agent.agent_type,
            group_index=agent.group_index,
            latency_ms=latency_ms,
            status="failed",
            started_at=started,
            completed_at=completed,
            error_code=getattr(exc, "error_code", None) or type(exc).__name__,
            error_detail=sanitize_error(str(exc)),
        )
        return activity, exc


def build_agents(
    ctx: PipelineContext,  # present for future agents needing ctx config
    *,
    provider: TranslationProvider,
    haiku_provider: TranslationProvider,
    sonnet_model_id: str,
    haiku_model_id: str,
) -> list[Agent]:
    """Configure the 3 agents for one /translate request.

    Two provider instances: one configured with sonnet default (for translate),
    one with haiku default (for lang detect). Both wrap the same underlying
    Anthropic SDK client class but use different model_id defaults.
    """
    from src.pipeline.agents.lang_detect import LangDetectAgent
    from src.pipeline.agents.translate import TranslateAgent

    return [
        LangDetectAgent(
            name="lang_detect_input",
            group_index=1,
            text_source="input",
            provider=haiku_provider,
            model_id=haiku_model_id,
        ),
        TranslateAgent(
            name="translate",
            group_index=1,
            provider=provider,
            model_id=sonnet_model_id,
        ),
        LangDetectAgent(
            name="lang_detect_output",
            group_index=2,
            text_source="output",
            provider=haiku_provider,
            model_id=haiku_model_id,
        ),
    ]
