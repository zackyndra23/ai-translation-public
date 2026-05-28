"""DepartmentRepository — CRUD for global department list."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.ids import make_id
from src.db.models import Department
from src.department.schemas import DepartmentCreate, DepartmentRead


class DepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[DepartmentRead]:
        result = await self._session.execute(
            select(Department).order_by(Department.department_name)
        )
        return [DepartmentRead.model_validate(d) for d in result.scalars().all()]

    async def get_by_id(self, department_id: str) -> DepartmentRead | None:
        row = await self._session.get(Department, department_id)
        return DepartmentRead.model_validate(row) if row else None

    async def get_by_name(self, name: str) -> DepartmentRead | None:
        result = await self._session.execute(
            select(Department).where(Department.department_name == name)
        )
        row = result.scalar_one_or_none()
        return DepartmentRead.model_validate(row) if row else None

    async def create(self, payload: DepartmentCreate) -> DepartmentRead:
        row = Department(
            department_id=make_id("department"), department_name=payload.department_name
        )
        self._session.add(row)
        await self._session.flush()
        return DepartmentRead.model_validate(row)
