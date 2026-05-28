"""Tests for argon2 API-key hashing."""

from __future__ import annotations

from src.auth.hashing import generate_api_key, hash_api_key, verify_api_key


def test_generate_api_key_format() -> None:
    key = generate_api_key()
    assert key.startswith("aitkey_")
    assert len(key) > 30  # base64-urlsafe 32 bytes is ~43 chars


def test_hash_and_verify_roundtrip() -> None:
    plaintext = "aitkey_abc123"
    hashed = hash_api_key(plaintext)
    assert hashed != plaintext  # not stored raw
    assert verify_api_key(plaintext, hashed) is True


def test_verify_rejects_wrong_key() -> None:
    hashed = hash_api_key("aitkey_correct")
    assert verify_api_key("aitkey_wrong", hashed) is False


def test_hash_is_argon2() -> None:
    hashed = hash_api_key("aitkey_test")
    assert hashed.startswith("$argon2")
