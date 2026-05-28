"""JWT encode/decode using HS256 (per ADR-046).

Lightweight — we store the active JWT per tenant in
``tenant.jwt_active_token``. A token failing decode here OR not matching
the tenant's active token (string equality, checked by middleware) is
rejected. Daily refresh is operator-driven via ``POST /auth/refresh-jwt``.
"""

from __future__ import annotations

import time
from typing import Any

import jwt as pyjwt

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h


def encode_jwt(*, tenant_id: str, secret: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Issue a new JWT for a tenant.

    Payload: ``{sub: tenant_id, iat: <unix>, exp: <unix + ttl>}``. HS256.
    """
    now = int(time.time())
    payload = {"sub": tenant_id, "iat": now, "exp": now + ttl_seconds}
    return pyjwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, *, secret: str) -> dict[str, Any]:
    """Decode + verify a JWT. Raises ValueError on any failure."""
    try:
        return pyjwt.decode(token, secret, algorithms=["HS256"])
    except pyjwt.PyJWTError as e:
        raise ValueError(f"Invalid JWT: {e}") from e
