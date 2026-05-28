"""Pipeline resolver — load tenant_profile + tenant + service for prompt rendering.

Sub-proyek K refactor: returns a flat ``ResolvedTenantProfile`` frozen
dataclass instead of a joinedload-loaded ORM blob. Fields are sourced from
denormalized columns + by-name lookups on the catalog repositories. The
old ``TenantProfile.tenant.country.country_name``-style access is gone —
relationships were dropped in migration 006.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.service.repository import ServiceRepository
from src.tenant.repository import TenantRepository
from src.tenant_profile.repository import TenantProfileRepository


class TenantProfileNotFound(Exception):
    """Raised when ``resolve`` cannot find the target profile (or its tenant)."""

    pass


@dataclass(frozen=True)
class ResolvedTenantProfile:
    """All the fields the pipeline + Jinja context need, flattened.

    Replaces the joinedload ORM blob from sub-proyek I. Fields are sourced
    from three queries: ``tenant_profile`` (denormalized cols give us
    ``profile_id``, ``tenant_name``, ``service_name``, ``position_name``,
    ``allowed_language``, ``prompt_applied``); ``tenant`` by-name lookup
    (``tenant_id``, ``country_name``, ``company_name``, ``department_name``);
    and ``service`` by-name lookup (``service_id`` + ``service_tone`` +
    ``service_target_audience``). Service is optional — a profile may
    reference a deleted service and we still want to render a prompt.
    Frozen so the pipeline can pass it across stages without anyone
    accidentally mutating it.
    """

    profile_id: str
    tenant_id: str
    tenant_name: str
    country_name: str
    company_name: str
    department_name: str
    position_name: str
    service_name: str
    service_id: str | None
    service_tone: str | None
    service_target_audience: str | None
    allowed_language: list[str] | None
    prompt_applied: list[str]


class TenantProfileResolver:
    """Loads + flattens ``tenant_profile`` + ``tenant`` + ``service`` for pipeline use."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._tp_repo = TenantProfileRepository(session)
        self._tenant_repo = TenantRepository(session)
        self._service_repo = ServiceRepository(session)

    async def resolve(self, profile_id: str) -> ResolvedTenantProfile:
        """Three-query resolution: profile → tenant by name → service by name.

        Missing tenant is fatal (a profile MUST point at a real tenant —
        catalog can't have rot like that without us noticing). Missing
        service is tolerated: we surface ``service_id``/``service_tone``/
        ``service_target_audience`` as ``None`` so prompt rendering still
        works for catalog drift / future tenant-only profiles.
        """
        tp = await self._tp_repo.get_orm_by_id(profile_id)
        if tp is None:
            raise TenantProfileNotFound(f"tenant_profile {profile_id!r} not found")

        tenant = await self._tenant_repo.get_by_name(tp.tenant_name)
        if tenant is None:
            raise TenantProfileNotFound(
                f"tenant_profile {profile_id!r} references unknown tenant_name {tp.tenant_name!r}"
            )

        service = await self._service_repo.get_by_name(tp.service_name)
        service_id = service.service_id if service else None
        service_tone = service.tone if service else None
        service_audience = service.target_audience if service else None

        return ResolvedTenantProfile(
            profile_id=tp.profile_id,
            tenant_id=tenant.tenant_id,
            tenant_name=tp.tenant_name,
            country_name=tenant.country_name,
            company_name=tenant.company_name,
            department_name=tenant.department_name,
            position_name=tp.position_name,
            service_name=tp.service_name,
            service_id=service_id,
            service_tone=service_tone,
            service_target_audience=service_audience,
            allowed_language=tp.allowed_language,
            prompt_applied=list(tp.prompt_applied),
        )
