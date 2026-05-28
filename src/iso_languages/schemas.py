"""Pydantic schemas for iso_languages."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IsoLanguageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    native_name: str | None
