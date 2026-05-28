"""FastAPI dependencies - wiring between HTTP layer and domain objects.

Per-process singletons: cache, provider, template env (each carries an
expensive resource like a connection pool or SDK client).

Per-request: DB session and everything that depends on it (repositories,
resolvers, the pipeline). Tests override via ``app.dependency_overrides``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from fastapi import Depends
from jinja2 import Environment
from sqlalchemy.ext.asyncio import AsyncSession

from src.cache.base import CacheBackend
from src.cache.redis_cache import RedisCache
from src.config.settings import get_settings
from src.db.session import get_session
from src.iso_languages.repository import IsoLanguageRepository
from src.pipeline.pipeline import TranslationPipeline, build_template_env
from src.providers.base import TranslationProvider
from src.providers.factory import get_provider as build_provider
from src.service.repository import ServiceRepository
from src.tenant_profile.resolver import TenantProfileResolver
from src.translation_logs.repository import TranslationLogRepository

# ---- process-wide singletons ----------------------------------------------


@lru_cache(maxsize=1)
def _build_cache() -> CacheBackend:
    return RedisCache(redis_url=get_settings().redis_url)


@lru_cache(maxsize=1)
def _build_provider() -> TranslationProvider:
    return build_provider("claude-sonnet")


@lru_cache(maxsize=1)
def _build_haiku_provider() -> TranslationProvider:
    """Haiku-default provider for lang_detect agents."""
    settings = get_settings()
    return build_provider("claude-sonnet", model_id_override=settings.anthropic_haiku_model)


@lru_cache(maxsize=1)
def _build_template_env() -> Environment:
    return build_template_env()


def get_cache() -> CacheBackend:
    return _build_cache()


def get_provider() -> TranslationProvider:
    return _build_provider()


def get_haiku_provider() -> TranslationProvider:
    return _build_haiku_provider()


def get_template_env() -> Environment:
    return _build_template_env()


# ---- per-request dependencies ---------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:  # pragma: no cover - re-export
    """Alias for the canonical session generator."""
    async for session in get_session():
        yield session


async def get_tenant_profile_resolver(
    db: AsyncSession = Depends(get_db),
) -> TenantProfileResolver:
    return TenantProfileResolver(db)


async def get_service_repository(
    db: AsyncSession = Depends(get_db),
) -> ServiceRepository:
    return ServiceRepository(db)


async def get_iso_repository(
    db: AsyncSession = Depends(get_db),
) -> IsoLanguageRepository:
    """Per-request repository used by the pipeline's build_jinja_context stage.

    Heavy lifting (the in-memory catalog dict) lives in module-level state
    inside ``IsoLanguageRepository``; the per-request wrapper is essentially
    free, so we keep the same DI pattern as the other repositories.
    """
    return IsoLanguageRepository(db)


async def get_log_repository(
    db: AsyncSession = Depends(get_db),
) -> TranslationLogRepository:
    return TranslationLogRepository(db)


async def get_pipeline(
    provider: TranslationProvider = Depends(get_provider),
    haiku_provider: TranslationProvider = Depends(get_haiku_provider),
    cache: CacheBackend = Depends(get_cache),
    resolver: TenantProfileResolver = Depends(get_tenant_profile_resolver),
    service_repo: ServiceRepository = Depends(get_service_repository),
    iso_repo: IsoLanguageRepository = Depends(get_iso_repository),
    template_env: Environment = Depends(get_template_env),
    log_repo: TranslationLogRepository = Depends(get_log_repository),
) -> TranslationPipeline:
    """Build the pipeline per request.

    Pipeline construction is cheap; the expensive parts (SDK client,
    Redis pool, Jinja env) live behind the cached singletons above.
    Building per-request keeps the per-request resolver + repos wired
    to the request-scoped DB session.
    """
    settings = get_settings()
    return TranslationPipeline(
        provider=provider,
        haiku_provider=haiku_provider,
        cache=cache,
        resolver=resolver,
        service_repo=service_repo,
        iso_repo=iso_repo,
        template_env=template_env,
        model_id=settings.anthropic_model,
        haiku_model_id=settings.anthropic_haiku_model,
        log_repo=log_repo,
    )
