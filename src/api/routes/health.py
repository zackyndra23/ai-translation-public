"""Health endpoints.

Two endpoints, two different audiences:

- ``GET /health`` — liveness. Hit by k8s every few seconds; must NEVER touch
  the DB or cache, because a transient blip in either shouldn't get the pod
  killed. Returns 200 as long as the process is alive enough to answer.

- ``GET /health/deep`` — readiness. Probes each dependency and reports a
  per-dep status. The aggregate ``status`` is ``"ok"`` only when every
  component is up; otherwise it's ``"degraded"``. We always return 200 so
  the *caller* (k8s readiness controller, ops dashboard) can decide what
  "degraded" means for its purposes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_cache, get_db
from src.api.schemas import DeepHealthResponse, DependencyHealth, HealthResponse
from src.cache.base import CacheBackend
from src.config.logging import get_logger
from src.config.settings import get_settings

router = APIRouter(tags=["meta"])
log = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe — no external I/O."""
    return HealthResponse(status="ok", timestamp=datetime.now(UTC).isoformat())


@router.get("/health/deep", response_model=DeepHealthResponse)
async def deep_health(
    db: AsyncSession = Depends(get_db),
    cache: CacheBackend = Depends(get_cache),
) -> DeepHealthResponse:
    """Readiness probe — checks DB + Redis + provider configuration."""
    settings = get_settings()
    deps: list[DependencyHealth] = []

    # ---- DB ----
    try:
        await db.execute(text("SELECT 1"))
        deps.append(DependencyHealth(name="postgres", status="ok"))
    except Exception as e:
        log.warning("health.deep.db_failed", error=str(e))
        deps.append(DependencyHealth(name="postgres", status="down", detail=str(e)))

    # ---- Redis ----
    if await cache.health_check():
        deps.append(DependencyHealth(name="redis", status="ok"))
    else:
        deps.append(
            DependencyHealth(
                name="redis",
                status="degraded",
                detail="ping failed — cache will fall through to provider",
            )
        )

    # ---- Provider config ----
    # We deliberately don't make a real Anthropic call from a health probe —
    # that would cost real money per check. The cheapest meaningful signal is
    # "an API key is configured and is not the placeholder."
    if "placeholder" in settings.anthropic_api_key:
        deps.append(
            DependencyHealth(
                name="anthropic",
                status="down",
                detail="ANTHROPIC_API_KEY is still the placeholder value",
            )
        )
    else:
        deps.append(
            DependencyHealth(
                name="anthropic",
                status="ok",
                detail=f"model={settings.anthropic_model}",
            )
        )

    aggregate = "ok" if all(d.status == "ok" for d in deps) else "degraded"
    return DeepHealthResponse(
        status=aggregate,
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=deps,
    )
