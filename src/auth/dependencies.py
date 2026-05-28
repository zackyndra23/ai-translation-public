"""FastAPI dependency to expose the authenticated tenant_id."""

from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_current_tenant_id(request: Request) -> str:
    """Extract the tenant_id stamped by TenantAuthMiddleware.

    Using request.state rather than a token arg keeps route signatures clean —
    routes declare ``tenant_id: str = Depends(get_current_tenant_id)`` and
    don't need to know whether it came from JWT or API key.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth middleware did not set tenant_id",
        )
    return tenant_id  # type: ignore[no-any-return]
