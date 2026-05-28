"""FastAPI auth middleware for sub-proyek I.

Two paths: Bearer JWT (cheap) or X-Tenant-API-Key (always valid until rotated).
Some endpoints are public (PUBLIC_PATHS) — those skip the check entirely.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.jwt import decode_jwt
from src.config.settings import Settings, get_settings
from src.db.session import SessionLocal
from src.tenant.repository import TenantRepository

# Paths that skip auth — used by Streamlit cascade pre-tenant-selection
PUBLIC_PATHS = {
    "/health",
    "/health/deep",
    "/countries",
    "/companies",
    "/departments",
    "/iso-languages",
    "/auth/refresh-jwt",  # uses API key only, handled inside the route
    "/openapi.json",
    "/docs",
    "/redoc",
}


def _is_public(path: str) -> bool:
    # Match exact path OR /{public_prefix}/... or /{public_prefix}?... (e.g. /companies?country=X)
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p + "/") or path.startswith(p + "?") for p in PUBLIC_PATHS)


class TenantAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if _is_public(request.url.path):
            return await call_next(request)

        settings = get_settings()
        tenant_id = await self._extract_tenant_id(request, settings)
        if tenant_id is None:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error_code": "missing_credentials",
                    "detail": "Provide Bearer JWT or X-Tenant-API-Key header",
                    "trace_id": getattr(request.state, "trace_id", None),
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.tenant_id = tenant_id
        return await call_next(request)

    async def _extract_tenant_id(self, request: Request, settings: Settings) -> str | None:
        # 1. Try Bearer JWT
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            try:
                payload = decode_jwt(token, secret=settings.jwt_secret)
                # Cross-check that this token is the active one for the tenant.
                # We store exactly one active JWT per tenant (ADR-046) so a
                # rotated-away token is rejected even if its signature is valid.
                async with SessionLocal() as session:
                    repo = TenantRepository(session)
                    active = await repo.get_active_jwt(payload["sub"])
                    if active and active == token:
                        return payload["sub"]  # type: ignore[no-any-return]
            except ValueError:
                pass

        # 2. Try API key header
        api_key = request.headers.get("x-tenant-api-key")
        if api_key:
            # Master key bypass (dev / admin) — never stored in DB.
            if api_key == settings.api_key_master:
                return "tenant-master"
            async with SessionLocal() as session:
                repo = TenantRepository(session)
                tenant_id = await repo.verify_api_key(api_key)
                if tenant_id:
                    return tenant_id

        return None


def install_auth_middleware(app: FastAPI) -> None:
    """Register TenantAuthMiddleware on an existing FastAPI application.

    Call this in main.py before the app starts accepting traffic so that every
    non-public route is protected from the first request.
    """
    app.add_middleware(TenantAuthMiddleware)
