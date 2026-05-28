"""Redact sensitive patterns from error messages before persisting them.

Per ADR-028 we keep this minimal: two regex rules cover the patterns
Anthropic SDK has been observed echoing back. Add more reactively as we
encounter new ones — preempting every possible token format is bikeshedding.
"""

from __future__ import annotations

import re

# Anthropic API keys: "sk-ant-" prefix followed by URL-safe characters.
# Trailing punctuation kept out of the match so error messages remain readable
# ("sk-ant-abc123. Token expired." → "***REDACTED***. Token expired.").
_ANTHROPIC_KEY = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")

# Bearer tokens: case-sensitive scheme name, whitespace, then the token value.
# JWT-shaped tokens contain dots; we accept dots inside the value.
_BEARER_TOKEN = re.compile(r"Bearer\s+[A-Za-z0-9._\-]+")

# Hard cap on stored error_detail length. 2000 chars is plenty for a typical
# stack frame + exception message; longer messages are almost always
# auto-generated noise (HTML pages, full DOM dumps, etc.).
_MAX_LEN = 2000


def sanitize_error(text: str) -> str:
    """Return ``text`` with known secrets redacted and length capped.

    The function is deliberately stateless and fast (single regex pass each).
    """
    if not text:
        return text
    redacted = _ANTHROPIC_KEY.sub("***REDACTED***", text)
    redacted = _BEARER_TOKEN.sub("***REDACTED***", redacted)
    return redacted[:_MAX_LEN]
