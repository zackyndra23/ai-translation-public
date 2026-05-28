"""Health endpoint tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "timestamp" in body


async def test_deep_health_lists_dependencies(api_client: AsyncClient) -> None:
    response = await api_client.get("/health/deep")
    assert response.status_code == 200
    body = response.json()
    # Three dependency rows: postgres, redis, anthropic — names pinned so
    # observability dashboards keying off them don't break silently.
    names = {d["name"] for d in body["dependencies"]}
    assert names == {"postgres", "redis", "anthropic"}
    assert body["status"] in {"ok", "degraded"}
