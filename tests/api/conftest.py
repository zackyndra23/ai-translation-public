"""Fixtures for API tests (sub-proyek I).

The dependency overrides swap the DB to the transaction-rollback session,
the LLM providers to AsyncMocks, and the cache to fakeredis. ``session.commit``
is neutralised to a flush so route-level commits don't leak past the per-test
rollback (ADR-018).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.api import dependencies as api_deps
from src.api.main import app
from src.cache.base import CacheBackend
from src.cache.redis_cache import RedisCache
from src.providers.base import TranslationProvider, TranslationResult


@pytest_asyncio.fixture
async def mock_provider() -> TranslationProvider:
    provider = MagicMock()
    provider.translate = AsyncMock(
        return_value=TranslationResult(
            translation="halo dunia",
            provider="claude",
            model="claude-sonnet-4-6",
            tokens_input=10,
            tokens_output=4,
            cost_usd=Decimal("0.0001"),
            latency_ms=100.0,
            metadata={"stop_reason": "end_turn"},
        )
    )
    return provider


@pytest_asyncio.fixture
async def fake_cache() -> CacheBackend:
    return RedisCache(client=fakeredis.aioredis.FakeRedis(decode_responses=False))


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    mock_provider: TranslationProvider,
    fake_cache: CacheBackend,
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client with all dependencies overridden for tests."""

    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _override_provider() -> TranslationProvider:
        return mock_provider

    def _override_cache() -> CacheBackend:
        return fake_cache

    def _override_haiku_provider() -> TranslationProvider:
        haiku = MagicMock()
        haiku.translate = AsyncMock(
            return_value=TranslationResult(
                translation="en",
                provider="claude",
                model="claude-haiku-4-5",
                tokens_input=50,
                tokens_output=12,
                cost_usd=Decimal("0.00006"),
                latency_ms=400.0,
                metadata={"stop_reason": "end_turn"},
            )
        )
        return haiku

    app.dependency_overrides[api_deps.get_db] = _override_db
    app.dependency_overrides[api_deps.get_provider] = _override_provider
    app.dependency_overrides[api_deps.get_cache] = _override_cache
    app.dependency_overrides[api_deps.get_haiku_provider] = _override_haiku_provider

    original_commit = db_session.commit

    async def _no_commit() -> None:
        await db_session.flush()

    db_session.commit = _no_commit  # type: ignore[method-assign]

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        db_session.commit = original_commit  # type: ignore[method-assign]
        app.dependency_overrides.clear()


def expect_ok(response: Any, *, status_code: int = 200) -> dict:
    assert (
        response.status_code == status_code
    ), f"Expected {status_code}, got {response.status_code}: {response.text}"
    return response.json()
