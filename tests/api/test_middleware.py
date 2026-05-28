"""Tests for TenantAuthMiddleware (sub-proyek I)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_protected_endpoint_rejects_without_credentials(
    api_client: AsyncClient,
) -> None:
    """A POST to /translate without credentials must 401."""
    resp = await api_client.post(
        "/translate",
        json={
            "text": "hello",
            "target_lang": "id",
            "profile_id": "profile-xxxxxxxx-xxxx",
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body.get("error_code") == "missing_credentials"


async def test_master_api_key_bypasses_per_tenant_lookup(
    api_client: AsyncClient,
) -> None:
    """The master key is for dev / admin; public endpoints accept it harmlessly."""
    resp = await api_client.get(
        "/countries",
        headers={"X-Tenant-API-Key": "aitkey_master_dev"},
    )
    assert resp.status_code == 200


async def test_health_is_public(api_client: AsyncClient) -> None:
    resp = await api_client.get("/health")
    assert resp.status_code == 200
