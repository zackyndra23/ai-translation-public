"""Pydantic schemas for tenant (sub-proyek K denormalized form).

NEVER include api_key_hash or jwt_active_token in any response Read schema.
TenantCreatedResponse is the one exception — it carries the plaintext API
key (returned ONCE at creation time per ADR-045).

Sub-proyek K: drop country_id/company_id/department_id FK references;
denormalize to *_name string snapshots populated at insert time.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantCreate(BaseModel):
    country_name: str
    company_name: str
    department_name: str


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: str
    tenant_name: str
    country_name: str
    company_name: str
    department_name: str
    alembic_version_at_create: str
    created_at: datetime


class TenantCreatedResponse(TenantRead):
    """Includes plaintext API key — returned ONCE on creation."""

    api_key_plaintext: str
