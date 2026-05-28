"""ServiceRepository — CRUD + glossary fetch."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import GlossaryTerm, Service, StyleExample
from src.service.schemas import ServiceCreate, ServiceRead


class ServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[ServiceRead]:
        result = await self._session.execute(select(Service).order_by(Service.service_name))
        return [ServiceRead.model_validate(s) for s in result.scalars().all()]

    async def get_by_id(self, service_id: str) -> ServiceRead | None:
        row = await self._session.get(Service, service_id)
        return ServiceRead.model_validate(row) if row else None

    async def get_by_name(self, name: str) -> ServiceRead | None:
        result = await self._session.execute(select(Service).where(Service.service_name == name))
        row = result.scalar_one_or_none()
        return ServiceRead.model_validate(row) if row else None

    # mypy resolves bare `list` to the method on this class (not the builtin)
    # under PEP 563; we suppress the false positive on the affected lines and
    # use list comprehensions in bodies to avoid the same name collision.
    async def list_glossary_for_service(
        self, service_id: str, source_lang: str, target_lang: str
    ) -> list[GlossaryTerm]:  # type: ignore[valid-type]
        result = await self._session.execute(
            select(GlossaryTerm)
            .where(
                GlossaryTerm.service_id == service_id,
                GlossaryTerm.source_lang == source_lang,
                GlossaryTerm.target_lang == target_lang,
            )
            .order_by(GlossaryTerm.priority.desc())
        )
        return [row for row in result.scalars().all()]

    async def list_examples_for_service(
        self, service_id: str, source_lang: str, target_lang: str
    ) -> list[StyleExample]:  # type: ignore[valid-type]
        result = await self._session.execute(
            select(StyleExample).where(
                StyleExample.service_id == service_id,
                StyleExample.source_lang == source_lang,
                StyleExample.target_lang == target_lang,
            )
        )
        return [row for row in result.scalars().all()]

    async def create(self, payload: ServiceCreate) -> ServiceRead:
        row = Service(
            service_id=make_id("service"),
            service_name=payload.service_name,
            description=payload.description,
            domain=payload.domain,
            tone=payload.tone,
            target_audience=payload.target_audience,
        )
        self._session.add(row)
        await self._session.flush()
        return ServiceRead.model_validate(row)
