"""Pydantic schemas for position."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PositionCreate(BaseModel):
    position_name: str
    department_id: str


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_id: str
    position_name: str
    department_id: str
    created_at: datetime
