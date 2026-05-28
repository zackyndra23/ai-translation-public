"""Shared pytest fixtures.

Two groups of fixtures live here:

1. ``client`` — async test client wired to the FastAPI app via ASGITransport
   (no real socket, no port collisions).

2. ``test_engine`` + ``db_session`` — fixtures for tests that touch the
   real Postgres container. We use a separate test database
   (``aitrans_test``) so dev data isn't disturbed; the session-scoped engine
   creates the schema once, and a per-test transaction is rolled back so
   each test sees a clean slate without paying the cost of recreating tables.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from src.api.main import app
from src.config.settings import get_settings
from src.db.session import Base

TEST_DB_NAME = "aitrans_test"


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Async test client wired directly to the ASGI app (no real socket)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _ensure_test_database_exists() -> None:
    """Create ``aitrans_test`` if it doesn't exist yet.

    ``CREATE DATABASE`` can't run inside a transaction, so we use asyncpg
    directly (it executes outside SQLAlchemy's connection-pool transaction
    machinery). Connects to the ``postgres`` admin DB to do the check.
    """
    url = make_url(get_settings().database_url)
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port,
        user=url.username,
        password=url.password,
        database="postgres",
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            # Quote the identifier to be safe — we control the constant but
            # this keeps the pattern correct if it ever becomes parameterised.
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """Session-scoped engine pointing at the test database.

    Schema is created up front via ``Base.metadata.create_all`` rather than
    running Alembic — the tables we want are exactly what the ORM declares,
    and skipping Alembic decouples tests from migration ordering.
    """
    await _ensure_test_database_exists()

    test_url = make_url(get_settings().database_url).set(database=TEST_DB_NAME)
    # ``NullPool`` matters here: pytest-asyncio creates a fresh event loop per
    # test, but a pooled asyncpg connection carries event-loop affinity. Reusing
    # a pooled connection across loops triggers "another operation is in
    # progress" or "unknown protocol state" errors. NullPool opens a new
    # connection per session and closes it on session exit — slower, but
    # robust across loops.
    engine = create_async_engine(test_url, poolclass=NullPool)

    # Importing src.db.models registers tables on Base.metadata via side effect.
    # We import inside the fixture so the import error surfaces here (not at
    # collection time) if something is broken upstream.
    from src.db import models as _models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.drop_all
        )  # idempotent — drop leftovers from a prior aborted run
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Don't drop tables on teardown: leaving the schema in place means a
    # subsequent test run gets the drop+create above and starts fresh without
    # paying the connection-tear-down cost twice.
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test session that rolls back on teardown.

    Each test gets its own session. We deliberately never call
    ``session.commit()`` in tests — every change therefore lives only in the
    session's transaction, and the ``rollback()`` in the teardown removes
    it. This gives clean isolation between tests without the complexity of
    bind-to-connection + outer-transaction patterns (which conflicted with
    asyncpg's single-statement-at-a-time discipline).
    """
    async with AsyncSession(bind=test_engine, expire_on_commit=False) as session:
        try:
            yield session
        finally:
            await session.rollback()
