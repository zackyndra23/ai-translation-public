"""TenantPromptRepository - read tenant_prompts rows keyed by agent_type.

PK is ``prompt_id`` but lookups use the unique ``agent_type`` column.
Reads are process-cached because templates change rarely. Tests reset
via :func:`clear_template_cache`.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TenantPrompt

AgentType = Literal["lang_detect_input", "lang_detect_output", "translate"]

_template_cache: dict[str, str] = {}


def clear_template_cache() -> None:
    _template_cache.clear()


class TenantPromptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, agent_type: AgentType) -> str:
        if agent_type in _template_cache:
            return _template_cache[agent_type]
        result = await self._session.execute(
            select(TenantPrompt.template).where(TenantPrompt.agent_type == agent_type)
        )
        template = result.scalar_one_or_none()
        if template is None:
            raise RuntimeError(
                f"No tenant_prompts row for agent_type={agent_type!r}. "
                "Run scripts/seed_tenant_data.py."
            )
        _template_cache[agent_type] = template
        return template
