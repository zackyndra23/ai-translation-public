"""TenantRepository tests for sub-proyek K denormalized form.

Verifies the Batch B refactor: create composes ``tenant_name`` auto-formatted,
stamps the injected ``alembic_version``, and the new ``get_by_name`` +
name-based ``resolve_by_ccd`` lookups return the right row.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.tenant.repository import TenantRepository
from src.tenant.schemas import TenantCreate

pytestmark = pytest.mark.asyncio


async def test_create_persists_denormalized_names_and_alembic_version(
    db_session: AsyncSession,
) -> None:
    """Create stores tenant_name + *_name snapshots + alembic_version_at_create."""
    repo = TenantRepository(db_session)
    response = await repo.create(
        TenantCreate(
            country_name="Indonesia",
            company_name="PT Test",
            department_name="Sales",
        ),
        alembic_version="006_schema_cleanup",
    )
    assert response.country_name == "Indonesia"
    assert response.company_name == "PT Test"
    assert response.department_name == "Sales"
    assert response.tenant_name == "PT Test — Sales (Indonesia)"
    assert response.alembic_version_at_create == "006_schema_cleanup"
    assert response.api_key_plaintext.startswith("aitkey_")


async def test_get_by_name(db_session: AsyncSession) -> None:
    """Lookup by tenant_name returns the row; missing returns None."""
    repo = TenantRepository(db_session)
    await repo.create(
        TenantCreate(
            country_name="Indonesia",
            company_name="PT Test",
            department_name="Sales",
        ),
        alembic_version="006",
    )
    found = await repo.get_by_name("PT Test — Sales (Indonesia)")
    assert found is not None
    assert found.country_name == "Indonesia"

    missing = await repo.get_by_name("Nonexistent")
    assert missing is None


async def test_resolve_by_ccd_uses_names(db_session: AsyncSession) -> None:
    """resolve_by_ccd takes names (not IDs) after sub-proyek K refactor."""
    repo = TenantRepository(db_session)
    await repo.create(
        TenantCreate(
            country_name="Indonesia",
            company_name="PT Test",
            department_name="Sales",
        ),
        alembic_version="006",
    )
    found = await repo.resolve_by_ccd(
        country_name="Indonesia",
        company_name="PT Test",
        department_name="Sales",
    )
    assert found is not None
    assert found.tenant_name == "PT Test — Sales (Indonesia)"
