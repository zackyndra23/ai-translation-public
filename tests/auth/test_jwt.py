"""Tests for JWT encode/decode."""

from __future__ import annotations

import pytest
from src.auth.jwt import decode_jwt, encode_jwt


def test_encode_decode_roundtrip() -> None:
    token = encode_jwt(tenant_id="tenant-abc12345-6789", secret="test-secret-min-16-chars")
    payload = decode_jwt(token, secret="test-secret-min-16-chars")
    assert payload["sub"] == "tenant-abc12345-6789"
    assert "iat" in payload
    assert "exp" in payload


def test_decode_rejects_tampered_signature() -> None:
    token = encode_jwt(tenant_id="t1", secret="test-secret-min-16-chars")
    tampered = token[:-3] + "XYZ"  # mess with signature
    with pytest.raises(ValueError, match="Invalid JWT"):
        decode_jwt(tampered, secret="test-secret-min-16-chars")


def test_decode_rejects_wrong_secret() -> None:
    token = encode_jwt(tenant_id="t1", secret="secret-A-min-16-chars-long")
    with pytest.raises(ValueError, match="Invalid JWT"):
        decode_jwt(token, secret="secret-B-min-16-chars-long")
