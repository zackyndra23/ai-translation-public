"""IsoLanguageRepository - module-level cache."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import IsoLanguage
from src.iso_languages.schemas import IsoLanguageRead

_catalog_cache: dict[str, IsoLanguageRead] = {}


def clear_catalog_cache() -> None:
    _catalog_cache.clear()


class IsoLanguageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[IsoLanguageRead]:
        if _catalog_cache:
            return list(_catalog_cache.values())
        result = await self._session.execute(select(IsoLanguage).order_by(IsoLanguage.name))
        rows = list(result.scalars().all())
        _catalog_cache.update({r.code: IsoLanguageRead.model_validate(r) for r in rows})
        return list(_catalog_cache.values())

    async def get_name(self, code: str) -> str | None:
        if not _catalog_cache:
            await self.list()
        entry = _catalog_cache.get(code)
        return entry.name if entry else None
