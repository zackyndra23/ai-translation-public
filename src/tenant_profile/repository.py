"""TenantProfileRepository — sub-proyek K denormalized form.

Drops joinedload (the FK relationships were removed in migration 006) and
exposes denormalized name-based lookups. ``get_orm_by_id`` returns the raw
ORM row for pipeline stages that need direct attribute access; everything
else stays Pydantic-flavoured.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import TenantProfile
from src.tenant_profile.schemas import TenantProfileCreate, TenantProfileRead


class TenantProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_tenant_name(
        self, tenant_name: str, position_name: str | None = None
    ) -> list[TenantProfileRead]:
        """List profiles for a tenant by name; optionally filter by ``position_name``.

        Replaces sub-proyek I's ``list_by_tenant(tenant_id, position_id)``.
        Snapshot names are the new join key.
        """
        query = select(TenantProfile).where(TenantProfile.tenant_name == tenant_name)
        if position_name:
            query = query.where(TenantProfile.position_name == position_name)
        result = await self._session.execute(query)
        return [TenantProfileRead.model_validate(p) for p in result.scalars().all()]

    async def get_by_id(self, profile_id: str) -> TenantProfileRead | None:
        row = await self._session.get(TenantProfile, profile_id)
        return TenantProfileRead.model_validate(row) if row else None

    async def get_orm_by_id(self, profile_id: str) -> TenantProfile | None:
        """Return the raw ORM row (no Pydantic wrap) for pipeline stages.

        The pipeline resolver reads denormalized fields directly off this row.
        No joinedload needed since there are no relationships to load — all
        fields are local columns now. Pydantic wrap would just round-trip
        the data needlessly.
        """
        return await self._session.get(TenantProfile, profile_id)

    async def create(self, payload: TenantProfileCreate) -> TenantProfileRead:
        row = TenantProfile(
            profile_id=make_id("profile"),
            tenant_name=payload.tenant_name,
            service_name=payload.service_name,
            position_name=payload.position_name,
            allowed_language=payload.allowed_language,
            prompt_applied=payload.prompt_applied,
        )
        self._session.add(row)
        await self._session.flush()
        return TenantProfileRead.model_validate(row)
