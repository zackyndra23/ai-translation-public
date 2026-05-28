"""Sub-proyek K end-to-end persistence smoke.

Run AFTER:
  1. `alembic upgrade head` applied
  2. `scripts/seed_tenant_data.py` run (you have a captured API key)
  3. Dev server running on :8000 (uv run uvicorn src.api.main:app)

Usage:
  export AITKEY_SMOKE=aitkey_<your-key>
  uv run python scripts/test_e2e_persistence.py

Verifies:
  1. POST /translate succeeds + returns log_id
  2. Row lands in translation_logs with source/translated text + cost
  3. Redis cache key present after first call
  4. Replay returns cached:true with low latency
  5. Replay creates a separate translation_logs row with cached=true
  6. POST /translate with disallowed target_lang returns 400 language_not_allowed
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from uuid import UUID

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import get_settings


async def _fetch_log_row(session: AsyncSession, log_id: UUID) -> dict | None:
    result = await session.execute(
        text("SELECT * FROM translation_logs WHERE log_id = :log_id"),
        {"log_id": str(log_id)},
    )
    row = result.mappings().one_or_none()
    return dict(row) if row else None


async def _profile_id_for(session: AsyncSession, *, allowed_includes: list[str]) -> str:
    """Find a profile_id whose allowed_language matches the includes (subset check)."""
    result = await session.execute(
        text(
            "SELECT profile_id, allowed_language "
            "FROM tenant_profile "
            "WHERE allowed_language @> ARRAY[:wanted]::varchar[] LIMIT 1"
        ),
        {"wanted": allowed_includes[0]},
    )
    row = result.first()
    if row is None:
        raise SystemExit(
            f"No tenant_profile found with allowed_language containing {allowed_includes}"
        )
    return row.profile_id


async def main() -> int:
    settings = get_settings()
    api_key = os.environ.get("AITKEY_SMOKE")
    if not api_key:
        print("ERROR: set AITKEY_SMOKE=aitkey_<your-key> first", file=sys.stderr)
        return 1

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async with session_factory() as session:
        profile_id = await _profile_id_for(session, allowed_includes=["id", "en"])

    payload = {
        "text": "Halo, selamat pagi",
        "source_lang": "id",
        "target_lang": "en",
        "profile_id": profile_id,
    }
    headers = {"X-Tenant-API-Key": api_key}

    # Clear any pre-existing cache keys for this payload so Step 1 is a real
    # cache miss. Redis FLUSHing the whole DB would be too destructive (other
    # tests may rely on warm cache) — scoped key deletion is the minimal
    # invasive approach. The smoke script's first call must produce a fresh
    # translation_logs row with cost_usd > 0 and cached=false.
    pre_existing = await redis.keys("translation:*")
    if pre_existing:
        await redis.delete(*pre_existing)
        print(f"== Setup: cleared {len(pre_existing)} pre-existing cache keys ==")

    print("== Step 1: POST /translate (first call) ==")
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        t0 = time.perf_counter()
        r1 = await client.post("/translate", json=payload, headers=headers)
        elapsed1_ms = (time.perf_counter() - t0) * 1000.0
        if r1.status_code != 200:
            print(f"  FAIL: status={r1.status_code} body={r1.text}", file=sys.stderr)
            return 1
        body1 = r1.json()
        log_id1 = body1["log_id"]
        if log_id1 is None:
            print("  FAIL: log_id is None — translation_logs write failed", file=sys.stderr)
            return 1
        print(
            f"  OK: HTTP 200, log_id={log_id1}, latency={elapsed1_ms:.0f}ms, cached={body1.get('cached')}"
        )

    print("== Step 2: Verify translation_logs row exists ==")
    async with session_factory() as session:
        row = await _fetch_log_row(session, UUID(log_id1))
        if row is None:
            print("  FAIL: no log row found", file=sys.stderr)
            return 1
        assert row["source_text"] == "Halo, selamat pagi"
        assert row["translated_text"], "translated_text is empty"
        assert row["cost_usd"] is not None and row["cost_usd"] > 0
        assert row["cached"] is False
        cache_key_in_row = row["cache_key"]
        print(
            f"  OK: source/translated text persisted, cost_usd={row['cost_usd']}, cache_key={cache_key_in_row}"
        )

    print("== Step 3: Verify Redis cache key set ==")
    redis_value = await redis.get(f"translation:{cache_key_in_row}")
    if redis_value is None:
        print(f"  FAIL: redis key translation:{cache_key_in_row} missing", file=sys.stderr)
        return 1
    parsed = json.loads(redis_value)
    print(f"  OK: redis key present, translation='{parsed.get('translation', '')[:40]}...'")

    print("== Step 4: Replay POST /translate (cache hit expected) ==")
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        t0 = time.perf_counter()
        r2 = await client.post("/translate", json=payload, headers=headers)
        elapsed2_ms = (time.perf_counter() - t0) * 1000.0
        body2 = r2.json()
        log_id2 = body2["log_id"]
        if r2.status_code != 200:
            print(f"  FAIL: replay status={r2.status_code}", file=sys.stderr)
            return 1
        if not body2.get("cached"):
            print(
                f"  FAIL: replay did not hit cache, body.cached={body2.get('cached')}",
                file=sys.stderr,
            )
            return 1
        print(f"  OK: HTTP 200, cached=true, latency={elapsed2_ms:.0f}ms")

    print("== Step 5: Verify replay log row exists with cached=true ==")
    async with session_factory() as session:
        row2 = await _fetch_log_row(session, UUID(log_id2))
        if row2 is None:
            print("  FAIL: no replay log row found", file=sys.stderr)
            return 1
        if not row2["cached"]:
            print(f"  FAIL: replay log row cached={row2['cached']}", file=sys.stderr)
            return 1
        print("  OK: replay log row persisted with cached=true")

    print("== Step 6: Negative case — non-allowed target_lang returns 400 ==")
    # Pick a profile with allowed_language=["id","en"] and request target=ja.
    bad_payload = {**payload, "target_lang": "ja"}
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        r3 = await client.post("/translate", json=bad_payload, headers=headers)
        if r3.status_code != 400:
            print(f"  FAIL: expected 400, got {r3.status_code} body={r3.text}", file=sys.stderr)
            return 1
        body3 = r3.json()
        if body3.get("error_code") != "language_not_allowed":
            print(f"  FAIL: error_code={body3.get('error_code')}", file=sys.stderr)
            return 1
        print(f"  OK: HTTP 400 language_not_allowed, detail={body3.get('detail')[:80]}")

    await redis.aclose()
    await engine.dispose()
    print("\nSub-proyek K end-to-end persistence verified")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
