"""POST /auth/refresh-jwt — issues a new JWT for the API-key-authenticated tenant."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.auth.jwt import encode_jwt
from src.config.settings import get_settings
from src.tenant.repository import TenantRepository

router = APIRouter(tags=["auth"])


class JwtRefreshResponse(BaseModel):
    jwt_active_token: str
    tenant_id: str
    expires_in: int  # seconds


@router.post("/auth/refresh-jwt", response_model=JwtRefreshResponse)
async def refresh_jwt(
    db: AsyncSession = Depends(get_db),
    x_tenant_api_key: str | None = Header(default=None),
) -> JwtRefreshResponse:
    if not x_tenant_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide X-Tenant-API-Key header",
        )
    settings = get_settings()
    repo = TenantRepository(db)
    tenant_id = await repo.verify_api_key(x_tenant_api_key)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    token = encode_jwt(tenant_id=tenant_id, secret=settings.jwt_secret)
    await repo.set_active_jwt(tenant_id, token)
    return JwtRefreshResponse(
        jwt_active_token=token,
        tenant_id=tenant_id,
        expires_in=86_400,
    )
