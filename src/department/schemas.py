"""Pydantic schemas for department."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DepartmentCreate(BaseModel):
    department_name: str


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    department_id: str
    department_name: str
    created_at: datetime
