"""Tests for the validate_target_language pipeline stage."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from src.pipeline.errors import LanguageNotAllowedError
from src.pipeline.schemas import PipelineRequest
from src.pipeline.stages import PipelineContext, validate_target_language
from src.tenant_profile.resolver import ResolvedTenantProfile

pytestmark = pytest.mark.asyncio


def _make_ctx(target_lang: str, allowed: list[str] | None) -> PipelineContext:
    ctx = PipelineContext(
        request=PipelineRequest(
            text="hello",
            target_lang=target_lang,
            profile_id="profile-x",
            tenant_id="tenant-x",
        ),
        trace_id=uuid.uuid4().hex,
        started_at_perf=time.perf_counter(),
        started_at=datetime.now(UTC),
    )
    ctx.resolved_tenant_profile = ResolvedTenantProfile(
        profile_id="profile-x",
        tenant_id="tenant-x",
        tenant_name="x",
        country_name="x",
        company_name="x",
        department_name="x",
        position_name="x",
        service_name="general",
        service_id=None,
        service_tone=None,
        service_target_audience=None,
        allowed_language=allowed,
        prompt_applied=["lang_detect_input", "translate", "lang_detect_output"],
    )
    return ctx


async def test_null_allowed_language_passes() -> None:
    ctx = _make_ctx(target_lang="ja", allowed=None)
    await validate_target_language(ctx)  # should not raise


async def test_target_in_allowed_passes() -> None:
    ctx = _make_ctx(target_lang="id", allowed=["id", "en"])
    await validate_target_language(ctx)


async def test_target_not_in_allowed_raises() -> None:
    ctx = _make_ctx(target_lang="ja", allowed=["id", "en"])
    with pytest.raises(LanguageNotAllowedError) as exc_info:
        await validate_target_language(ctx)
    assert exc_info.value.target_lang == "ja"
    assert exc_info.value.allowed == ["id", "en"]


async def test_empty_allowed_list_rejects_all() -> None:
    """allowed_language=[] (vs None) means no language is allowed."""
    ctx = _make_ctx(target_lang="en", allowed=[])
    with pytest.raises(LanguageNotAllowedError):
        await validate_target_language(ctx)
