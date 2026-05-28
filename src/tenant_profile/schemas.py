"""Pydantic schemas for tenant_profile (sub-proyek K denormalized form)."""

from __future__ import annotations

from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

# Tuple (not list) + `Final` so the module-level constant is immutable —
# accidental mutation by a caller can't corrupt validation for the rest of
# the process. Compared via `tuple(value) != EXPECTED_PROMPT_APPLIED_ORDER`.
EXPECTED_PROMPT_APPLIED_ORDER: Final[tuple[str, ...]] = (
    "lang_detect_input",
    "translate",
    "lang_detect_output",
)


def _validate_prompt_applied(value: list[str]) -> list[str]:
    """prompt_applied is `[lang_detect_input, translate, lang_detect_output]` exactly.

    DB-level CHECK enforces length 3 (migration 006). The ordering rule lives
    here because Postgres CHECK can't express ordered-element equality without
    a stored procedure — Pydantic is the cleanest place to enforce it.
    """
    if len(value) != 3:
        raise ValueError(f"prompt_applied must have length 3, got {len(value)}")
    if tuple(value) != EXPECTED_PROMPT_APPLIED_ORDER:
        raise ValueError(
            f"prompt_applied must be in order {list(EXPECTED_PROMPT_APPLIED_ORDER)}, got {value}"
        )
    return value


class TenantProfileCreate(BaseModel):
    tenant_name: str
    service_name: str
    position_name: str
    allowed_language: list[str] | None = None
    prompt_applied: list[str]

    @field_validator("prompt_applied")
    @classmethod
    def check_prompt_applied(cls, v: list[str]) -> list[str]:
        return _validate_prompt_applied(v)


class TenantProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile_id: str
    tenant_name: str
    service_name: str
    position_name: str
    allowed_language: list[str] | None
    prompt_applied: list[str]
    created_at: datetime
