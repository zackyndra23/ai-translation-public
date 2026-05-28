"""TenantProfileRepository tests for sub-proyek K denormalized form.

Verifies the Batch B refactor: ``create`` writes denormalized name columns,
``list_by_tenant_name`` filters by ``tenant_name`` (and optional
``position_name``), and ``get_orm_by_id`` returns the RAW ORM row (no
Pydantic wrap) for downstream pipeline use.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.tenant_profile.repository import TenantProfileRepository
from src.tenant_profile.schemas import TenantProfileCreate

pytestmark = pytest.mark.asyncio


async def test_create_persists_denormalized_names(db_session: AsyncSession) -> None:
    repo = TenantProfileRepository(db_session)
    profile = await repo.create(
        TenantProfileCreate(
            tenant_name="PT Test — Sales (Indonesia)",
            service_name="general",
            position_name="Sales Executive",
            allowed_language=["id", "en"],
            prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        )
    )
    assert profile.tenant_name == "PT Test — Sales (Indonesia)"
    assert profile.service_name == "general"
    assert profile.position_name == "Sales Executive"
    assert profile.allowed_language == ["id", "en"]
    assert profile.prompt_applied == [
        "lang_detect_input",
        "translate",
        "lang_detect_output",
    ]


async def test_list_by_tenant_name(db_session: AsyncSession) -> None:
    repo = TenantProfileRepository(db_session)
    await repo.create(
        TenantProfileCreate(
            tenant_name="PT Test — Sales (Indonesia)",
            service_name="general",
            position_name="Sales Executive",
            allowed_language=None,
            prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        )
    )
    profiles = await repo.list_by_tenant_name("PT Test — Sales (Indonesia)")
    assert len(profiles) == 1
    assert profiles[0].position_name == "Sales Executive"


async def test_get_orm_by_id_returns_orm_row(db_session: AsyncSession) -> None:
    """``get_orm_by_id`` returns the raw ORM row (not Pydantic Read) for pipeline use."""
    repo = TenantProfileRepository(db_session)
    created = await repo.create(
        TenantProfileCreate(
            tenant_name="PT Test — Sales (Indonesia)",
            service_name="general",
            position_name="Sales Executive",
            allowed_language=["id", "en"],
            prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        )
    )
    row = await repo.get_orm_by_id(created.profile_id)
    assert row is not None
    assert row.tenant_name == "PT Test — Sales (Indonesia)"
    assert row.service_name == "general"
    assert row.position_name == "Sales Executive"
