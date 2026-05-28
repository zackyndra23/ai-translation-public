"""CountryRepository — minimal CRUD for the country reference table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.country.schemas import CountryCreate, CountryRead
from src.db.ids import make_id
from src.db.models import Country


class CountryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[CountryRead]:
        result = await self._session.execute(select(Country).order_by(Country.country_name))
        return [CountryRead.model_validate(c) for c in result.scalars().all()]

    async def get_by_id(self, country_id: str) -> CountryRead | None:
        row = await self._session.get(Country, country_id)
        return CountryRead.model_validate(row) if row else None

    async def get_by_name(self, country_name: str) -> CountryRead | None:
        result = await self._session.execute(
            select(Country).where(Country.country_name == country_name)
        )
        row = result.scalar_one_or_none()
        return CountryRead.model_validate(row) if row else None

    async def create(self, payload: CountryCreate) -> CountryRead:
        row = Country(country_id=make_id("country"), country_name=payload.country_name)
        self._session.add(row)
        await self._session.flush()
        return CountryRead.model_validate(row)
