"""CompanyRepository — CRUD + filter by country."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.company.schemas import CompanyCreate, CompanyRead
from src.db.ids import make_id
from src.db.models import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[CompanyRead]:
        result = await self._session.execute(select(Company).order_by(Company.company_name))
        return [CompanyRead.model_validate(c) for c in result.scalars().all()]

    # mypy resolves bare `list` to the method `list` on this class (not the
    # builtin) under PEP 563, so we suppress the false positive on the next line.
    async def list_by_country(self, country_name: str) -> list[CompanyRead]:  # type: ignore[valid-type]
        result = await self._session.execute(
            select(Company)
            .where(Company.company_country == country_name)
            .order_by(Company.company_name)
        )
        return [CompanyRead.model_validate(c) for c in result.scalars().all()]

    async def get_by_id(self, company_id: str) -> CompanyRead | None:
        row = await self._session.get(Company, company_id)
        return CompanyRead.model_validate(row) if row else None

    async def get_by_name(self, name: str) -> CompanyRead | None:
        """Look up a company by its display name. Used by the pipeline's
        build_jinja_context stage to resolve company metadata from a
        denormalized ``company_name`` snapshot on ``tenant``.
        """
        result = await self._session.execute(select(Company).where(Company.company_name == name))
        row = result.scalar_one_or_none()
        return CompanyRead.model_validate(row) if row else None

    async def create(self, payload: CompanyCreate) -> CompanyRead:
        row = Company(
            company_id=make_id("company"),
            company_name=payload.company_name,
            company_country=payload.company_country,
        )
        self._session.add(row)
        await self._session.flush()
        return CompanyRead.model_validate(row)
