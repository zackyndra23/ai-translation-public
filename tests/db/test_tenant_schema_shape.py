"""Assert the ORM shape for `tenant` + `tenant_profile` matches migration 006.

This file does NOT replay migration 006 against a scratch DB. The test DB
(`aitrans_test`) is built by `Base.metadata.create_all` in
`tests/conftest.py::test_engine`, NEVER by `alembic upgrade`. So these tests
verify that the ORM declarations in `src/db/models.py` produce the expected
post-006 shape (denormalized columns present, FK columns absent) — they do
NOT verify that the migration script itself executes correctly against a
real populated database. Migration replay is exercised manually via
`alembic upgrade head` against a Postgres instance; CI relies on the ORM
shape being the source of truth.

Also verifies `downgrade()` raises NotImplementedError per ADR-053 precedent
(migration is irreversible by design).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine


async def _table_columns(async_engine: AsyncEngine, table_name: str) -> set[str]:
    async with async_engine.connect() as conn:
        result = await conn.run_sync(
            lambda sync_conn: {col["name"] for col in inspect(sync_conn).get_columns(table_name)}
        )
    return result


async def test_tenant_schema_has_denormalized_columns(
    test_engine: AsyncEngine,
) -> None:
    """Tenant ORM matches migration 006: snapshot columns present, FK columns absent."""
    tenant_cols = await _table_columns(test_engine, "tenant")
    assert "tenant_name" in tenant_cols
    assert "country_name" in tenant_cols
    assert "company_name" in tenant_cols
    assert "department_name" in tenant_cols
    assert "alembic_version_at_create" in tenant_cols
    assert "country_id" not in tenant_cols
    assert "company_id" not in tenant_cols
    assert "department_id" not in tenant_cols


async def test_tenant_profile_schema_has_denormalized_columns(
    test_engine: AsyncEngine,
) -> None:
    """TenantProfile ORM matches migration 006: snapshot columns present, FK columns absent."""
    cols = await _table_columns(test_engine, "tenant_profile")
    assert "tenant_name" in cols
    assert "service_name" in cols
    assert "position_name" in cols
    assert "tenant_id" not in cols
    assert "position_id" not in cols
    assert "service_id" not in cols


def test_migration_006_downgrade_raises() -> None:
    """Loading the migration module + calling downgrade() raises.

    `alembic/versions/` is not a Python package (no __init__.py), so we use
    importlib.util.spec_from_file_location to load the migration file
    directly without trying to import it as a regular module.
    """
    migration_path = (
        Path(__file__).parent.parent.parent
        / "alembic"
        / "versions"
        / "006_schema_cleanup_iso_plumbing.py"
    )
    spec = importlib.util.spec_from_file_location("migration_006", str(migration_path))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(NotImplementedError, match="irreversible"):
        module.downgrade()
