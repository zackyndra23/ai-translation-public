"""Schema validation for sub-proyek K denormalized tenant_profile."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from src.tenant_profile.schemas import TenantProfileCreate


def test_create_accepts_three_prompt_applied_in_order() -> None:
    payload = TenantProfileCreate(
        tenant_name="PT Test — Sales (Indonesia)",
        service_name="general",
        position_name="Sales Executive",
        allowed_language=["id", "en"],
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    assert payload.prompt_applied == [
        "lang_detect_input",
        "translate",
        "lang_detect_output",
    ]


def test_create_rejects_wrong_length_prompt_applied() -> None:
    with pytest.raises(ValidationError, match="length 3"):
        TenantProfileCreate(
            tenant_name="x",
            service_name="general",
            position_name="x",
            prompt_applied=["lang_detect_input", "translate"],  # length 2
        )


def test_create_rejects_wrong_order_prompt_applied() -> None:
    with pytest.raises(ValidationError, match="order"):
        TenantProfileCreate(
            tenant_name="x",
            service_name="general",
            position_name="x",
            prompt_applied=["translate", "lang_detect_input", "lang_detect_output"],
        )


def test_create_allows_null_allowed_language() -> None:
    payload = TenantProfileCreate(
        tenant_name="x",
        service_name="general",
        position_name="x",
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
        allowed_language=None,
    )
    assert payload.allowed_language is None
