"""SQLAlchemy async engine + session factory.

Phase 1 has no models yet — this module exists so later phases (and Alembic env.py)
can import a single, shared engine instead of constructing their own. Keeping the
engine global is fine because SQLAlchemy's connection pool is itself a singleton-
shaped resource and we want pooled connections, not per-request ones.

Design notes:
- ``expire_on_commit=False`` because we frequently return ORM objects to FastAPI
  response handlers AFTER commit. The default expires attributes and would force
  a re-fetch (or a DetachedInstanceError when the session closes).
- ``echo`` is wired to LOG_LEVEL=DEBUG so we don't dump every SQL statement in
  production logs by default.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config.settings import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models. Alembic's target_metadata points here."""


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=(_settings.log_level == "DEBUG"),
    # pool_pre_ping pings the connection before handing it out — cheap insurance
    # against stale connections after the DB has been restarted out from under us.
    pool_pre_ping=True,
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields a session; commits on success, rolls back on error.

    Auto-commit-on-success is what makes routes like ``/translate`` work
    without each route having to remember to call ``session.commit()``. Before
    sub-proyek B that wasn't a problem because the translate route didn't
    write anything — but ``record_log`` now writes one row per call in the
    pipeline's ``finally`` block, and without a commit the transaction rolls
    back when the session closes and the row vanishes. ADR-018 documented the
    "routes commit explicitly" pattern; this generalises it so a missing
    explicit commit no longer silently drops audit rows.

    Routes that already call ``session.commit()`` explicitly (the profile
    CRUD routes) continue to work — the trailing commit here becomes a no-op
    when there's nothing pending. In tests the per-request fixture patches
    ``commit`` to be a flush (ADR-018) so this trailing call still respects
    rollback discipline.

    Usage::

        @app.get("/things")
        async def list_things(session: AsyncSession = Depends(get_session)) -> ...:
            ...
    """
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
