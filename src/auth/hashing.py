"""argon2 hashing for tenant API keys.

argon2 chosen per ADR-045 for resistance to GPU/ASIC attacks. The plaintext
key is generated once at tenant creation and returned to the operator;
only the hash is persisted.
"""

from __future__ import annotations

import secrets

from passlib.context import CryptContext  # type: ignore[import-untyped]

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def generate_api_key() -> str:
    """Generate a new plaintext API key for a tenant.

    Format: ``aitkey_<urlsafe-base64 of 32 bytes>``. Returned ONCE; not stored
    in plaintext anywhere — only the argon2 hash via :func:`hash_api_key`.
    """
    return f"aitkey_{secrets.token_urlsafe(32)}"


def hash_api_key(plaintext: str) -> str:
    """Return an argon2 hash of the plaintext API key."""
    digest: str = _pwd_context.hash(plaintext)
    return digest


def verify_api_key(plaintext: str, hashed: str) -> bool:
    """Constant-time-ish verify (argon2's own bcrypt-compare semantics)."""
    ok: bool = _pwd_context.verify(plaintext, hashed)
    return ok
