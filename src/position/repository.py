"""PositionRepository — CRUD + filter by department."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import Department, Position
from src.position.schemas import PositionCreate, PositionRead


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_department(self, department_id: str) -> list[PositionRead]:
        result = await self._session.execute(
            select(Position)
            .where(Position.department_id == department_id)
            .order_by(Position.position_name)
        )
        return [PositionRead.model_validate(p) for p in result.scalars().all()]

    async def get_by_id(self, position_id: str) -> PositionRead | None:
        row = await self._session.get(Position, position_id)
        return PositionRead.model_validate(row) if row else None

    async def get_by_name_and_dept(self, name: str, department_id: str) -> PositionRead | None:
        result = await self._session.execute(
            select(Position).where(
                Position.position_name == name,
                Position.department_id == department_id,
            )
        )
        row = result.scalar_one_or_none()
        return PositionRead.model_validate(row) if row else None

    async def get_by_name_and_department(
        self, position_name: str, department_name: str
    ) -> PositionRead | None:
        """Composite lookup by (position_name, department_name) — used by the
        pipeline to resolve a Position from denormalized snapshots.

        Position name isn't globally unique (e.g. "Analyst" appears in many
        departments), so the lookup joins ``Department`` to disambiguate.
        Returns the raw ``PositionRead`` (no ORM relationship traversal).
        """
        result = await self._session.execute(
            select(Position)
            .join(Department, Position.department_id == Department.department_id)
            .where(
                Position.position_name == position_name,
                Department.department_name == department_name,
            )
        )
        row = result.scalar_one_or_none()
        return PositionRead.model_validate(row) if row else None

    async def create(self, payload: PositionCreate) -> PositionRead:
        row = Position(
            position_id=make_id("position"),
            position_name=payload.position_name,
            department_id=payload.department_id,
        )
        self._session.add(row)
        await self._session.flush()
        return PositionRead.model_validate(row)
