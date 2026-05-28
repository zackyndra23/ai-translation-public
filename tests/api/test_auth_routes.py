"""Tests for POST /auth/refresh-jwt (sub-proyek I, refactored for sub-proyek K denormalized schema)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.hashing import generate_api_key, hash_api_key
from src.db.models import Tenant


async def test_refresh_jwt_returns_token_for_valid_api_key(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Refresh-JWT roundtrip — tenant rows now carry denormalized snapshots
    (no FK columns) and the audit ``alembic_version_at_create`` stamp per
    ADR-053/054. The reference catalog rows (country/company/department) are
    no longer required by tenant insert — name strings are stored directly.
    """
    plaintext = generate_api_key()
    tenant = Tenant(
        tenant_id="tenant-test1234-abcd",
        tenant_name="TestCorp — TestDept (Testland)",
        country_name="Testland",
        company_name="TestCorp",
        department_name="TestDept",
        alembic_version_at_create="test_fixture",
        api_key_hash=hash_api_key(plaintext),
    )
    db_session.add(tenant)
    await db_session.flush()

    resp = await api_client.post(
        "/auth/refresh-jwt",
        headers={"X-Tenant-API-Key": plaintext},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "tenant-test1234-abcd"
    assert "jwt_active_token" in body
    assert body["expires_in"] == 86_400


async def test_refresh_jwt_rejects_invalid_key(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/auth/refresh-jwt",
        headers={"X-Tenant-API-Key": "aitkey_definitely_invalid"},
    )
    assert resp.status_code == 401


async def test_refresh_jwt_requires_header(api_client: AsyncClient) -> None:
    resp = await api_client.post("/auth/refresh-jwt")
    assert resp.status_code == 401
