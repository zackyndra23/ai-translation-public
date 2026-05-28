"""Async repository for translation log persistence.

Constructor takes a session, ``create()`` inserts one row and returns the
generated ``log_id``. The repo never commits — the API layer owns
transaction boundaries.

Read methods are stubs because a future dashboard sub-proyek owns them.
Locking the interface here means we don't have to revisit when it lands.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import TranslationLog
from src.translation_logs.schemas import TranslationLogCreate, TranslationLogRead

# Per-session flush serialisation. SQLAlchemy AsyncSession does not allow
# concurrent flush calls; ``asyncio.gather`` over /translate/batch can fire
# many concurrent ``record_log`` writes against one request-scoped session.
# We key locks by id(session) so each session has its own; the dict is
# bounded by the number of in-flight requests (negligible memory).
_SESSION_LOCKS: dict[int, asyncio.Lock] = {}


def _get_session_lock(session: AsyncSession) -> asyncio.Lock:
    session_id = id(session)
    if session_id not in _SESSION_LOCKS:
        _SESSION_LOCKS[session_id] = asyncio.Lock()
    return _SESSION_LOCKS[session_id]


class TranslationLogRepository:
    """All persistence operations against the ``translation_logs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, payload: TranslationLogCreate) -> uuid.UUID:
        """Insert one log row and return its server-generated ``log_id``."""
        lock = _get_session_lock(self._session)
        async with lock:
            row = TranslationLog(**payload.model_dump())
            self._session.add(row)
            await self._session.flush()
            log_id: uuid.UUID = row.log_id
            return log_id

    # ---- Read methods - stubs for future dashboard sub-proyek ----------------

    async def recent(self, *, tenant_id: str, limit: int = 50) -> list[TranslationLogRead]:
        raise NotImplementedError("recent() is implemented by a future dashboard sub-proyek")

    async def by_profile(
        self, *, tenant_id: str, profile_id: str, limit: int = 50
    ) -> list[TranslationLogRead]:
        raise NotImplementedError("by_profile() is implemented by a future dashboard sub-proyek")

    async def aggregate_cost(self, *, tenant_id: str) -> dict[str, object]:
        raise NotImplementedError(
            "aggregate_cost() is implemented by a future dashboard sub-proyek"
        )
