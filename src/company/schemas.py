"""Pydantic schemas for company."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    company_name: str
    company_country: str


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: str
    company_name: str
    company_country: str
    created_at: datetime
