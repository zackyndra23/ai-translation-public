"""Custom ID generator: `{prefix}-{8hex}-{4hex}`.

Reads first 12 hex chars of a fresh UUID4 split 8+4. 48 bits entropy —
collision-safe for MVP scale (per ADR-040), more readable than full
UUID for log greps + admin operations.
"""

from __future__ import annotations

import uuid


def make_id(prefix: str) -> str:
    """Generate a new prefixed ID.

    Format: ``f"{prefix}-{8hex}-{4hex}"`` (e.g. ``"tenant-3f2504e0-4f89"``).
    Use whenever inserting a row into a table whose PK uses the custom format.
    """
    if not prefix:
        raise ValueError("ID prefix is required")
    hex_chars = uuid.uuid4().hex
    return f"{prefix}-{hex_chars[:8]}-{hex_chars[8:12]}"
