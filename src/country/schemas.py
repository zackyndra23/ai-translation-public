"""Pydantic schemas for country."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CountryCreate(BaseModel):
    country_name: str


class CountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    country_id: str
    country_name: str
    created_at: datetime
