"""Health endpoint contract.

The /health endpoint is consumed by Kubernetes liveness probes, the SDK's
connectivity check, and any uptime monitor we point at the service. The shape it
returns is therefore a public contract — these assertions are deliberately strict.
"""

from __future__ import annotations

from datetime import datetime

from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_response_shape(client: AsyncClient) -> None:
    response = await client.get("/health")
    body = response.json()

    assert body["status"] == "ok"
    assert "timestamp" in body
    # The timestamp must be a parseable ISO-8601 string. We don't pin the exact
    # value (clock skew between test and server) — just that it's well-formed.
    datetime.fromisoformat(body["timestamp"])
