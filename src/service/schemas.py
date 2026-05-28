"""Pydantic schemas for service."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ServiceCreate(BaseModel):
    service_name: str
    description: str | None = None
    domain: str | None = None
    tone: str | None = None
    target_audience: str | None = None


class ServiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_id: str
    service_name: str
    description: str | None
    domain: str | None
    tone: str | None
    target_audience: str | None
    created_at: datetime
