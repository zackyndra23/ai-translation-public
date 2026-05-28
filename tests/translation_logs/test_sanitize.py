"""Tests for sanitize_error: regex redact + truncate.

Per ADR-028, sanitization is intentionally minimal — two regex patterns
plus a hard truncate. We expand reactively when new sensitive-pattern
classes show up in real error logs.
"""

from __future__ import annotations

from src.translation_logs.sanitize import sanitize_error


def test_sanitize_strips_anthropic_api_key() -> None:
    given = "Auth failed: sk-ant-abc123xyz_DEF456 is expired"
    result = sanitize_error(given)
    assert "sk-ant-abc123xyz_DEF456" not in result
    assert "***REDACTED***" in result


def test_sanitize_strips_bearer_token() -> None:
    given = "Header: Authorization: Bearer eyJhbGc.eyJzdWI.signature"
    result = sanitize_error(given)
    assert "eyJhbGc.eyJzdWI.signature" not in result
    assert "***REDACTED***" in result


def test_sanitize_truncates_to_2000_chars() -> None:
    given = "x" * 5000
    result = sanitize_error(given)
    assert len(result) == 2000


def test_sanitize_preserves_short_innocent_text() -> None:
    given = "Profile 'asuransi' not found"
    result = sanitize_error(given)
    assert result == given


def test_sanitize_handles_empty_string() -> None:
    assert sanitize_error("") == ""


def test_sanitize_handles_multiple_secrets_in_one_string() -> None:
    given = "sk-ant-abc and Bearer xyz both present"
    result = sanitize_error(given)
    assert "sk-ant-abc" not in result
    assert "Bearer xyz" not in result
    assert result.count("***REDACTED***") == 2


def test_sanitize_truncates_after_redact_to_lock_in_ordering() -> None:
    """Redact first, then truncate. Otherwise a token straddling the cap could
    leak into the stored detail. This test fails if someone swaps the order."""
    # Innocent prefix that nearly fills the cap, plus a secret token that
    # spans past the cap. After redaction the string grows beyond _MAX_LEN,
    # so the final truncation must still cut at 2000 — and the redaction
    # must have happened before the cut, otherwise the leaked key fragment
    # would survive.
    prefix = "x" * 1990
    given = prefix + "sk-ant-leakedkey_DEF456"
    result = sanitize_error(given)
    assert len(result) == 2000
    assert "sk-ant-leakedkey" not in result
